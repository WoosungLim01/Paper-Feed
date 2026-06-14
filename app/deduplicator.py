import hashlib
import re
from typing import List


def normalize_title(title: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", "", title.lower())).strip()


def make_fingerprint(candidate: dict) -> str:
    title_norm = normalize_title(candidate.get("title") or "")
    year = str(candidate.get("year") or "")
    authors = candidate.get("authors") or []
    first_author = authors[0].split()[-1].lower() if authors else ""
    return title_norm + "|" + year + "|" + first_author


def _get_identity_key(candidate: dict):
    """Return (priority_level, key) for the candidate's best identity."""
    if candidate.get("doi"):
        return (1, "doi:" + candidate["doi"])
    if candidate.get("arxiv_id"):
        return (2, "arxiv:" + candidate["arxiv_id"])
    if candidate.get("openalex_id"):
        return (3, "openalex:" + candidate["openalex_id"])
    if candidate.get("semantic_scholar_id"):
        return (4, "s2:" + candidate["semantic_scholar_id"])
    fp = make_fingerprint(candidate)
    fp_hash = hashlib.md5(fp.encode()).hexdigest()
    return (5, "fp:" + fp_hash)


def _assign_paper_id(candidate: dict) -> str:
    """Assign stable paper_id using priority: doi > arxiv > openalex > s2 > fingerprint hash."""
    if candidate.get("doi"):
        return "doi:" + candidate["doi"]
    if candidate.get("arxiv_id"):
        return "arxiv:" + candidate["arxiv_id"]
    if candidate.get("openalex_id"):
        return "openalex:" + candidate["openalex_id"].split("/")[-1]
    if candidate.get("semantic_scholar_id"):
        return "s2:" + candidate["semantic_scholar_id"]
    fp = make_fingerprint(candidate)
    return "fp:" + hashlib.md5(fp.encode()).hexdigest()


def _completeness_score(candidate: dict) -> int:
    """Count non-None, non-empty fields to prefer the most complete record."""
    fields = ["title", "abstract", "authors", "year", "url", "doi", "arxiv_id",
              "openalex_id", "semantic_scholar_id", "pdf_url"]
    score = 0
    for f in fields:
        val = candidate.get(f)
        if val is not None and val != "" and val != []:
            score += 1
    return score


def deduplicate(candidates: List[dict]) -> List[dict]:
    """
    Deduplicate paper candidates using stable identity priority.
    Merge source_hits when duplicates found. Keep most complete record as base.
    """
    # Map from identity key → best candidate
    seen: dict[str, dict] = {}

    for candidate in candidates:
        _, key = _get_identity_key(candidate)

        if key not in seen:
            seen[key] = candidate
        else:
            existing = seen[key]
            # Merge source_hits
            merged_hits = list(dict.fromkeys(
                existing.get("source_hits", []) + candidate.get("source_hits", [])
            ))
            # Keep the more complete record as base
            if _completeness_score(candidate) > _completeness_score(existing):
                base = dict(candidate)
                base["source_hits"] = merged_hits
                # Carry over any IDs from the other record
                for id_field in ["doi", "arxiv_id", "openalex_id", "semantic_scholar_id"]:
                    if not base.get(id_field) and existing.get(id_field):
                        base[id_field] = existing[id_field]
                seen[key] = base
            else:
                existing["source_hits"] = merged_hits
                for id_field in ["doi", "arxiv_id", "openalex_id", "semantic_scholar_id"]:
                    if not existing.get(id_field) and candidate.get(id_field):
                        existing[id_field] = candidate[id_field]

    result = []
    for candidate in seen.values():
        candidate["paper_id"] = _assign_paper_id(candidate)
        result.append(candidate)

    return result
