import asyncio
import logging
import os
from datetime import date, datetime, timedelta, timezone
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


def _parse_date(date_str: str):
    """날짜 문자열을 datetime 객체로 파싱."""
    if not date_str:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d", "%Y"):
        try:
            return datetime.strptime(date_str[:len(fmt.replace("%Y", "0000").replace("%m", "00").replace("%d", "00").replace("%H", "00").replace("%M", "00").replace("%S", "00").replace("%z", ""))], fmt).replace(tzinfo=timezone.utc)
        except Exception:
            continue
    return None


def _normalize_arxiv(entry) -> dict:
    """arXiv feedparser entry → 표준 candidate dict."""
    pub_date = None
    published_str = getattr(entry, "published", None)
    if published_str:
        try:
            pub_date = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
        except Exception:
            pass

    entry_id = getattr(entry, "id", "") or ""
    arxiv_id = None
    if "/abs/" in entry_id:
        arxiv_id = entry_id.split("/abs/")[-1]
    elif entry_id:
        arxiv_id = entry_id.split("/")[-1]

    candidate = _empty_candidate()
    candidate.update({
        "candidate_id": "arxiv:" + (arxiv_id or entry_id),
        "title": getattr(entry, "title", "").replace("\n", " ").strip(),
        "authors": [a.get("name", "") for a in getattr(entry, "authors", [])],
        "year": pub_date.year if pub_date else None,
        "date": pub_date.date().isoformat() if pub_date else None,
        "abstract": getattr(entry, "summary", "").replace("\n", " ").strip(),
        "url": f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else entry_id,
        "pdf_url": f"https://arxiv.org/pdf/{arxiv_id}" if arxiv_id else None,
        "arxiv_id": arxiv_id,
        "source": "arxiv",
        "source_hits": ["arxiv"],
        "raw": dict(entry),
    })
    return candidate


def _normalize_s2(paper: dict) -> dict:
    """Semantic Scholar paper dict → 표준 candidate dict."""
    pub_date_str = paper.get("publicationDate", "")
    paper_id = paper.get("paperId", "")
    external_ids = paper.get("externalIds", {}) or {}
    doi = external_ids.get("DOI")
    arxiv_id = external_ids.get("ArXiv")

    year = paper.get("year")
    pub_date_obj = None
    if pub_date_str:
        try:
            pub_date_obj = datetime.strptime(pub_date_str[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
            if not year:
                year = pub_date_obj.year
        except Exception:
            pass

    candidate = _empty_candidate()
    candidate.update({
        "candidate_id": "s2:" + paper_id,
        "title": (paper.get("title") or "").replace("\n", " ").strip(),
        "authors": [a.get("name", "") for a in paper.get("authors", [])],
        "year": year,
        "date": pub_date_obj.date().isoformat() if pub_date_obj else None,
        "abstract": (paper.get("abstract") or "").replace("\n", " ").strip(),
        "url": paper.get("url"),
        "doi": doi,
        "arxiv_id": arxiv_id,
        "semantic_scholar_id": paper_id,
        "source": "semantic_scholar",
        "source_hits": ["semantic_scholar"],
        "raw": paper,
    })
    return candidate


def _normalize_openalex(work: dict) -> dict | None:
    """OpenAlex work dict → 표준 candidate dict."""
    work_id = work.get("id", "")
    if not work_id:
        return None

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

    abstract = _reconstruct_abstract(work.get("abstract_inverted_index") or {})

    authors = [
        a["author"]["display_name"]
        for a in work.get("authorships", [])
        if a.get("author") and a["author"].get("display_name")
    ]

    primary_loc = work.get("primary_location") or {}
    url = primary_loc.get("landing_page_url")
    year = work.get("publication_year")
    pub_date_str = work.get("publication_date", "")

    candidate = _empty_candidate()
    candidate.update({
        "candidate_id": candidate_id,
        "title": (work.get("title") or "").replace("\n", " ").strip(),
        "authors": authors,
        "year": year,
        "date": pub_date_str[:10] if pub_date_str else None,
        "abstract": abstract,
        "url": url,
        "doi": doi,
        "arxiv_id": arxiv_id,
        "openalex_id": work_id,
        "source": "openalex",
        "source_hits": ["openalex"],
        "raw": {k: v for k, v in work.items() if k != "abstract_inverted_index"},
    })
    return candidate


def build_queries(config: SurveyConfig) -> List[str]:
    """
    API 검색용 쿼리 생성.
    search_keywords 사용 (짧고 명확한 키워드).
    research_questions 는 자연어라 API 검색에 부적합 → 사용 안 함.
    조합 쿼리 제외: 중복 노이즈 발생 원인.
    """
    keywords = config.search_keywords if config.search_keywords else config.query_hints

    # 개별 키워드만 사용, 중복 제거·순서 유지
    return list(dict.fromkeys(keywords))


async def fetch_arxiv(
    queries: List[str],
    days_back: int = DAYS_BACK,
    max_per_query: int = 300,
) -> List[dict]:
    """
    arXiv API 페이지네이션 적용.
    날짜 범위 벗어난 논문 만나면 해당 쿼리 중단.
    쿼리당 최대 300개 상한 (노이즈 방지).
    rate limit: 요청 사이 3초 대기.
    """
    today = date.today()
    date_from = today - timedelta(days=days_back + 2)  # 2일 버퍼

    all_results = []

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, follow_redirects=True) as client:
        for query in queries:
            start = 0
            query_results = []

            while True:
                params = {
                    "search_query": f"all:{query}",
                    "sortBy": "submittedDate",
                    "sortOrder": "descending",
                    "start": start,
                    "max_results": 100,
                }

                try:
                    resp = await client.get(
                        "https://export.arxiv.org/api/query",
                        params=params,
                    )
                    feed = feedparser.parse(resp.text)
                    entries = feed.entries

                    if not entries:
                        break

                    hit_old = False
                    for entry in entries:
                        pub_date = None
                        published_str = getattr(entry, "published", None)
                        if published_str:
                            try:
                                pub_date = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                            except Exception:
                                pass
                        if pub_date and pub_date.date() < date_from:
                            hit_old = True
                            break
                        if pub_date:
                            query_results.append(_normalize_arxiv(entry))

                    if hit_old or len(entries) < 100:
                        break

                    start += 100
                    if start >= max_per_query:  # 쿼리당 상한 도달
                        break
                    await asyncio.sleep(3)

                except Exception as e:
                    print(f"[arXiv] 오류 ({query}): {e}")
                    break

            print(f"[arXiv] '{query}' → {len(query_results)}개")
            all_results.extend(query_results)
            await asyncio.sleep(3)

    return all_results


async def fetch_semantic_scholar(
    queries: List[str],
    days_back: int = DAYS_BACK,
    max_per_query: int = 200,
) -> List[dict]:
    """
    Semantic Scholar API 페이지네이션.
    API 키 환경변수: S2_API_KEY 또는 SEMANTIC_SCHOLAR_API_KEY.
    429 에러 시 60초 대기 후 재시도.
    최대 200개까지 수집 (rate limit 과부하 방지).
    """
    today = date.today()
    date_from = today - timedelta(days=days_back + 2)

    api_key = os.getenv("S2_API_KEY", os.getenv("SEMANTIC_SCHOLAR_API_KEY", ""))
    headers = {"x-api-key": api_key} if api_key else {}

    all_results = []

    async with httpx.AsyncClient(headers=headers, timeout=REQUEST_TIMEOUT) as client:
        for query in queries:
            offset = 0
            query_results = []

            while True:
                params = {
                    "query": query,
                    "fields": (
                        "paperId,title,abstract,year,publicationDate,"
                        "authors,url,externalIds,citationCount"
                    ),
                    "limit": 100,
                    "offset": offset,
                }

                try:
                    resp = await client.get(
                        "https://api.semanticscholar.org/graph/v1/paper/search",
                        params=params,
                    )

                    if resp.status_code == 429:
                        print("[S2] Rate limit → 60초 대기")
                        await asyncio.sleep(60)
                        continue

                    if resp.status_code != 200:
                        print(f"[S2] 오류 {resp.status_code} ({query})")
                        break

                    data = resp.json()
                    papers = data.get("data", [])
                    total = data.get("total", 0)

                    if not papers:
                        break

                    for p in papers:
                        pub_date = None
                        pub_date_str = p.get("publicationDate", "")
                        if pub_date_str:
                            try:
                                pub_date = datetime.strptime(pub_date_str[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
                            except Exception:
                                pass
                        # publicationDate 없는 논문은 날짜 불명 → 포함 (year 필터는 scorer 단계)
                        if pub_date is None or pub_date.date() >= date_from:
                            query_results.append(_normalize_s2(p))

                    offset += len(papers)
                    if offset >= min(total, max_per_query) or len(papers) < 100:
                        break

                    await asyncio.sleep(1.5)

                except Exception as e:
                    print(f"[S2] 오류 ({query}): {e}")
                    break

            print(f"[S2] '{query}' → {len(query_results)}개")
            all_results.extend(query_results)
            await asyncio.sleep(2)

    return all_results


async def fetch_openalex(
    queries: List[str],
    days_back: int = DAYS_BACK,
    max_per_query: int = 200,
) -> List[dict]:
    """
    OpenAlex API 페이지네이션.
    날짜 범위를 API 파라미터로 직접 전달 (가장 정확).
    최대 3페이지(600개)까지 수집 (타임아웃·rate limit 방지).
    abstract_inverted_index 없는 논문도 수집 (제목만으로 유사도 계산 가능).
    """
    today = date.today()
    date_from = today - timedelta(days=days_back + 2)
    date_filter = (
        f"from_publication_date:{date_from.isoformat()},"
        f"to_publication_date:{today.isoformat()}"
    )

    all_results = []

    oa_timeout = httpx.Timeout(30.0)  # OpenAlex는 30초 타임아웃 적용
    async with httpx.AsyncClient(timeout=oa_timeout) as client:
        for query in queries:
            page = 1
            query_results = []

            while True:
                params = {
                    "search": query,
                    "filter": date_filter,
                    "sort": "publication_date:desc",
                    "per_page": 200,
                    "page": page,
                    "select": (
                        "id,title,authorships,publication_year,"
                        "publication_date,abstract_inverted_index,"
                        "primary_location,doi,ids"
                    ),
                }

                try:
                    resp = await client.get(
                        "https://api.openalex.org/works",
                        params=params,
                        headers={"User-Agent": "PaperFeed/1.0 (research project)"},
                    )

                    if resp.status_code == 429:
                        print(f"[OpenAlex] Rate limit → 30초 대기")
                        await asyncio.sleep(30)
                        continue

                    if resp.status_code != 200:
                        print(f"[OpenAlex] 오류 {resp.status_code} ({query})")
                        break

                    data = resp.json()
                    works = data.get("results", [])
                    meta = data.get("meta", {})

                    if not works:
                        break

                    for w in works:
                        normalized = _normalize_openalex(w)
                        if normalized:
                            query_results.append(normalized)

                    total_count = meta.get("count", 0)
                    total_pages = (total_count // 200) + 1

                    if page >= total_pages or page >= 3:
                        break

                    page += 1
                    await asyncio.sleep(1)

                except httpx.ReadTimeout:
                    print(f"[OpenAlex] Timeout ({query}) → 15초 대기 후 재시도")
                    await asyncio.sleep(15)
                    # 타임아웃은 1회 재시도 후 중단
                    try:
                        resp = await client.get(
                            "https://api.openalex.org/works",
                            params=params,
                            headers={"User-Agent": "PaperFeed/1.0 (research project)"},
                        )
                        if resp.status_code == 200:
                            data = resp.json()
                            for w in data.get("results", []):
                                normalized = _normalize_openalex(w)
                                if normalized:
                                    query_results.append(normalized)
                    except Exception:
                        pass
                    break
                except Exception as e:
                    print(f"[OpenAlex] 오류 ({query}): {e}")
                    break

            print(f"[OpenAlex] '{query}' → {len(query_results)}개")
            all_results.extend(query_results)
            await asyncio.sleep(1)

    return all_results


def _sanitize_query(q: str) -> str:
    """Remove characters that break API query strings."""
    import re
    return re.sub(r"[?!.,;:()\[\]{}\"'\\]", " ", q).strip()


async def fetch_all(config: SurveyConfig, days_back: int = DAYS_BACK) -> List[dict]:
    """세 소스 동시 수집 + 소스별 통계 출력"""
    queries = build_queries(config)
    print(f"\n[수집] 쿼리 {len(queries)}개:")
    for q in queries:
        print(f"  - {q}")

    results = await asyncio.gather(
        fetch_arxiv(queries, days_back),
        fetch_semantic_scholar(queries, days_back),
        fetch_openalex(queries, days_back),
        return_exceptions=True,
    )

    arxiv_papers = results[0] if not isinstance(results[0], Exception) else []
    s2_papers    = results[1] if not isinstance(results[1], Exception) else []
    oa_papers    = results[2] if not isinstance(results[2], Exception) else []

    if isinstance(results[0], Exception):
        print(f"[arXiv] 실패: {results[0]}")
    if isinstance(results[1], Exception):
        print(f"[S2] 실패: {results[1]}")
    if isinstance(results[2], Exception):
        print(f"[OpenAlex] 실패: {results[2]}")

    print(f"\n[수집 결과]")
    print(f"  arXiv     : {len(arxiv_papers)}개")
    print(f"  S2        : {len(s2_papers)}개")
    print(f"  OpenAlex  : {len(oa_papers)}개")

    all_papers = arxiv_papers + s2_papers + oa_papers
    print(f"  합계      : {len(all_papers)}개 (중복 제거 전)\n")

    return all_papers
