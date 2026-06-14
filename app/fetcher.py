import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import List

import feedparser
import httpx

from app.config import SurveyConfig, DAYS_BACK, MAX_PER_SOURCE, REQUEST_TIMEOUT

logger = logging.getLogger(__name__)


def _empty_candidate() -> dict:
    return {
        "candidate_id": "",
        "title": "",
        "authors": [],
        "year": None,
        "abstract": None,
        "url": None,
        "pdf_url": None,
        "doi": None,
        "arxiv_id": None,
        "openalex_id": None,
        "semantic_scholar_id": None,
        "source": "",
        "source_hits": [],
        "score": 0.0,
        "raw": {},
    }


def _reconstruct_abstract(inverted_index: dict) -> str:
    """Reconstruct abstract from OpenAlex abstract_inverted_index."""
    if not inverted_index:
        return ""
    positions = {}
    for word, pos_list in inverted_index.items():
        for pos in pos_list:
            positions[pos] = word
    return " ".join(positions[i] for i in sorted(positions))


async def fetch_arxiv(
    queries: List[str],
    days_back: int = DAYS_BACK,
    max_results: int = MAX_PER_SOURCE,
) -> List[dict]:
    """Fetch papers from arXiv API."""
    results = []
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=days_back)

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        for query in queries:
            try:
                params = {
                    "search_query": "all:" + query,
                    "sortBy": "submittedDate",
                    "sortOrder": "descending",
                    "max_results": max_results,
                }
                resp = await client.get(
                    "https://export.arxiv.org/api/query", params=params
                )
                resp.raise_for_status()
                feed = feedparser.parse(resp.text)

                for entry in feed.entries:
                    # Parse published date
                    published_str = getattr(entry, "published", None)
                    pub_date = None
                    if published_str:
                        try:
                            pub_date = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                        except Exception:
                            pass

                    if pub_date and pub_date < cutoff:
                        continue

                    arxiv_id = None
                    entry_id = getattr(entry, "id", "") or ""
                    if "/abs/" in entry_id:
                        arxiv_id = entry_id.split("/abs/")[-1]
                    elif entry_id:
                        arxiv_id = entry_id.split("/")[-1]

                    candidate = _empty_candidate()
                    candidate.update(
                        {
                            "candidate_id": "arxiv:" + (arxiv_id or entry_id),
                            "title": getattr(entry, "title", "").replace("\n", " ").strip(),
                            "authors": [
                                a.get("name", "") for a in getattr(entry, "authors", [])
                            ],
                            "year": pub_date.year if pub_date else None,
                            "abstract": getattr(entry, "summary", "").replace("\n", " ").strip(),
                            "url": f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else entry_id,
                            "pdf_url": f"https://arxiv.org/pdf/{arxiv_id}" if arxiv_id else None,
                            "arxiv_id": arxiv_id,
                            "source": "arxiv",
                            "source_hits": ["arxiv"],
                            "raw": dict(entry),
                        }
                    )
                    results.append(candidate)
                    logger.debug("arXiv: %s", candidate["title"][:60])

            except Exception as e:
                logger.warning("arXiv query '%s' failed: %s", query, e)

    logger.info("arXiv: fetched %d candidates", len(results))
    return results


async def fetch_semantic_scholar(
    queries: List[str],
    days_back: int = DAYS_BACK,
    max_results: int = MAX_PER_SOURCE,
) -> List[dict]:
    """Fetch papers from Semantic Scholar API."""
    results = []
    cutoff = (datetime.now(tz=timezone.utc) - timedelta(days=days_back)).date()

    headers = {}
    api_key = os.environ.get("S2_API_KEY")
    if api_key:
        headers["x-api-key"] = api_key
        logger.info("Semantic Scholar: using API key")
    else:
        logger.warning("Semantic Scholar: no API key set (S2_API_KEY), rate limits may apply")

    # Server-side year filter: e.g. "2023-2026"
    from_year = cutoff.year
    to_year = datetime.now(tz=timezone.utc).year
    year_filter = f"{from_year}-{to_year}"

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, headers=headers) as client:
        # S2 rate limit: 1 req/sec — cap to 4 most important queries
        s2_queries = queries[:4]
        for i, query in enumerate(s2_queries):
            if i > 0:
                await asyncio.sleep(2.0)
            try:
                params = {
                    "query": query,
                    "fields": "paperId,title,abstract,year,publicationDate,authors,url,externalIds",
                    "limit": max_results,
                    "year": year_filter,       # server-side year filter
                    "sort": "citationCount",   # most cited first = higher quality
                }
                # Retry up to 3 times on 429
                data = None
                for attempt in range(3):
                    resp = await client.get(
                        "https://api.semanticscholar.org/graph/v1/paper/search",
                        params=params,
                    )
                    if resp.status_code == 429:
                        wait = 2 ** attempt * 2  # 2s, 4s, 8s
                        logger.warning("Semantic Scholar 429 on '%s', retrying in %ds (attempt %d/3)", query[:40], wait, attempt + 1)
                        await asyncio.sleep(wait)
                        continue
                    resp.raise_for_status()
                    data = resp.json()
                    break
                if data is None:
                    logger.warning("Semantic Scholar query '%s' failed after retries", query[:40])
                    continue

                for paper in data.get("data", []):
                    pub_date_str = paper.get("publicationDate")

                    paper_id = paper.get("paperId", "")
                    external_ids = paper.get("externalIds", {}) or {}
                    doi = external_ids.get("DOI")
                    arxiv_id = external_ids.get("ArXiv")

                    year = paper.get("year")
                    if not year and pub_date_str:
                        try:
                            year = int(pub_date_str[:4])
                        except Exception:
                            pass

                    candidate = _empty_candidate()
                    candidate.update(
                        {
                            "candidate_id": "s2:" + paper_id,
                            "title": (paper.get("title") or "").replace("\n", " ").strip(),
                            "authors": [
                                a.get("name", "") for a in paper.get("authors", [])
                            ],
                            "year": year,
                            "abstract": (paper.get("abstract") or "").replace("\n", " ").strip(),
                            "url": paper.get("url"),
                            "doi": doi,
                            "arxiv_id": arxiv_id,
                            "semantic_scholar_id": paper_id,
                            "source": "semantic_scholar",
                            "source_hits": ["semantic_scholar"],
                            "raw": paper,
                        }
                    )
                    results.append(candidate)

            except Exception as e:
                logger.warning("Semantic Scholar query '%s' failed: %s", query, e)

    logger.info("Semantic Scholar: fetched %d candidates", len(results))
    return results


async def fetch_openalex(
    queries: List[str],
    days_back: int = DAYS_BACK,
    max_results: int = MAX_PER_SOURCE,
) -> List[dict]:
    """Fetch papers from OpenAlex API."""
    results = []
    from_date = (datetime.now(tz=timezone.utc) - timedelta(days=days_back)).strftime("%Y-%m-%d")

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        for query in queries:
            try:
                clean_query = _sanitize_query(query)
                if not clean_query:
                    continue
                params = {
                    "search": clean_query,
                    "filter": f"from_publication_date:{from_date}",
                    "sort": "publication_date:desc",
                    "per_page": max_results,
                    "select": "id,title,authorships,publication_year,publication_date,abstract_inverted_index,primary_location,doi,ids",
                }
                resp = await client.get(
                    "https://api.openalex.org/works", params=params
                )
                resp.raise_for_status()
                data = resp.json()

                for work in data.get("results", []):
                    work_id = work.get("id", "")
                    openalex_id = work_id
                    candidate_id = "openalex:" + work_id.split("/")[-1]

                    doi_raw = work.get("doi", "") or ""
                    doi = doi_raw.replace("https://doi.org/", "") if doi_raw else None
                    if doi == "":
                        doi = None

                    ids = work.get("ids", {}) or {}
                    arxiv_raw = ids.get("arxiv", "") or ""
                    arxiv_id = arxiv_raw.replace("https://arxiv.org/abs/", "") if arxiv_raw else None
                    if arxiv_id == "":
                        arxiv_id = None

                    abstract = _reconstruct_abstract(
                        work.get("abstract_inverted_index") or {}
                    )

                    authors = [
                        a["author"]["display_name"]
                        for a in work.get("authorships", [])
                        if a.get("author") and a["author"].get("display_name")
                    ]

                    primary_loc = work.get("primary_location") or {}
                    url = primary_loc.get("landing_page_url")

                    year = work.get("publication_year")

                    candidate = _empty_candidate()
                    candidate.update(
                        {
                            "candidate_id": candidate_id,
                            "title": (work.get("title") or "").replace("\n", " ").strip(),
                            "authors": authors,
                            "year": year,
                            "abstract": abstract,
                            "url": url,
                            "doi": doi,
                            "arxiv_id": arxiv_id,
                            "openalex_id": openalex_id,
                            "source": "openalex",
                            "source_hits": ["openalex"],
                            "raw": {k: v for k, v in work.items() if k != "abstract_inverted_index"},
                        }
                    )
                    results.append(candidate)

            except Exception as e:
                logger.warning("OpenAlex query '%s' failed: %s", query, e)

    logger.info("OpenAlex: fetched %d candidates", len(results))
    return results


def _sanitize_query(q: str) -> str:
    """Remove characters that break API query strings."""
    import re
    return re.sub(r"[?!.,;:()\[\]{}\"'\\]", " ", q).strip()


def build_queries(config: SurveyConfig) -> List[str]:
    """Build deterministic query list from config."""
    queries = []
    queries.append(config.topic_overview)
    for rq in config.research_questions:
        queries.append(rq)
    for hint in config.query_hints:
        queries.append(hint)
    combined = config.topic_overview + " " + " ".join(config.query_hints)
    queries.append(combined)
    return list(dict.fromkeys(queries))  # deduplicate while preserving order


async def fetch_all(config: SurveyConfig) -> List[dict]:
    """Fetch from all three sources concurrently."""
    queries = build_queries(config)

    results = await asyncio.gather(
        fetch_arxiv(queries, DAYS_BACK, MAX_PER_SOURCE),
        fetch_semantic_scholar(queries, DAYS_BACK, MAX_PER_SOURCE),
        fetch_openalex(queries, DAYS_BACK, MAX_PER_SOURCE),
        return_exceptions=True,
    )

    all_candidates = []
    source_names = ["arxiv", "semantic_scholar", "openalex"]
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error("Source %s failed: %s", source_names[i], result)
        else:
            logger.info("Source %s: %d papers", source_names[i], len(result))
            all_candidates.extend(result)

    return all_candidates
