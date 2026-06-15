import os
import shutil
from datetime import datetime, timezone
from typing import TYPE_CHECKING, List, Optional

from app.store import (
    append_ndjson,
    read_existing_ids,
    read_ndjson,
    write_json,
    write_ndjson,
)

if TYPE_CHECKING:
    from app.config import SurveyConfig

# List of all possible score fields (missing → normalized to null)
_SCORE_FIELDS = ["score", "tfidf_score", "sbert_score", "ensemble_score"]


def _normalize_scores(papers: List[dict]) -> List[dict]:
    """
    Fill missing score fields with null so the frontend can handle them consistently.
    Legacy papers.ndjson entries lack tfidf_score/sbert_score fields,
    so None is assigned explicitly.
    """
    for p in papers:
        for field in _SCORE_FIELDS:
            if field not in p:
                p[field] = None
    return papers


def _rescore_existing(papers: List[dict], config: "SurveyConfig") -> bool:
    """
    Retroactively re-score already-stored papers that are missing tfidf_score or sbert_score.

    Returns:
        True if any paper was updated (caller should rewrite ndjson).
    """
    missing_tfidf = [p for p in papers if p.get("tfidf_score") is None]
    missing_sbert = [p for p in papers if p.get("sbert_score") is None]

    if not missing_tfidf and not missing_sbert:
        return False

    import logging
    logger = logging.getLogger(__name__)

    if missing_tfidf:
        logger.info("[Publisher] Retroactively scoring %d existing papers with TF-IDF...", len(missing_tfidf))
        from app.scorer import score_papers_tfidf
        score_papers_tfidf(missing_tfidf, config)
        # Restore score field so it is not overwritten by tfidf_score
        for p in missing_tfidf:
            if p.get("sbert_score") is not None:
                p["score"] = p["sbert_score"]

    if missing_sbert:
        logger.info("[Publisher] Retroactively scoring %d existing papers with SBERT...", len(missing_sbert))
        from app.scorer_sbert import score_papers_sbert
        orig_min = config.min_relevance_score
        config.min_relevance_score = -1.0
        score_papers_sbert(missing_sbert, config)
        config.min_relevance_score = orig_min
        # Unify score field to sbert_score
        for p in missing_sbert:
            p["score"] = p.get("sbert_score", p.get("score", 0.0))

    return True


def publish(
    accepted: List[dict],
    rejected: List[dict],
    run_record: dict,
    config_dict: dict,
    data_dir: str,
    site_dir: str,
    config: Optional["SurveyConfig"] = None,
) -> None:
    """Publish pipeline results to data/ and mirror to site/data/."""

    papers_path   = os.path.join(data_dir, "papers.ndjson")
    rejects_path  = os.path.join(data_dir, "rejects.ndjson")
    history_path  = os.path.join(data_dir, "run_history.ndjson")
    changelog_path = os.path.join(data_dir, "changelog.md")
    config_path   = os.path.join(data_dir, "survey_config.json")
    status_path   = os.path.join(data_dir, "system_status.json")

    site_data_dir = os.path.join(site_dir, "data")
    os.makedirs(site_data_dir, exist_ok=True)

    # 1. Read existing paper IDs
    existing_ids = read_existing_ids(papers_path)

    # 2. Filter accepted to only NEW papers, stamp with run_id
    run_id = run_record.get("run_id", "unknown")
    new_papers = []
    for p in accepted:
        if p.get("paper_id") not in existing_ids:
            p["run_id"] = run_id
            new_papers.append(p)

    # 3. Append new papers to data/papers.ndjson
    if new_papers:
        append_ndjson(papers_path, new_papers)

    # 4. Append rejected to data/rejects.ndjson
    if rejected:
        append_ndjson(rejects_path, rejected)

    # 5. Append run_record to data/run_history.ndjson
    run_record["paper_ids"] = [p["paper_id"] for p in new_papers if p.get("paper_id")]
    run_record["new_count"] = len(new_papers)
    append_ndjson(history_path, [run_record])

    # 6. Append changelog section to data/changelog.md
    timestamp = run_record.get("timestamp", datetime.now(tz=timezone.utc).isoformat())
    topic = run_record.get("topic", "")
    changelog_lines = [
        f"\n## Run {run_id} — {timestamp}\n",
        f"Added {len(new_papers)} papers on topic: {topic}\n",
    ]
    for p in new_papers:
        title = p.get("title", "(no title)")
        url = p.get("url", "")
        if url:
            changelog_lines.append(f"- [{title}]({url})\n")
        else:
            changelog_lines.append(f"- {title}\n")

    with open(changelog_path, "a", encoding="utf-8") as f:
        f.writelines(changelog_lines)

    # 7. Build status payload
    status_payload: dict = {"status": "idle", "last_run": timestamp, "scorer": "dual"}

    # 8. Write system_status.json to data/
    write_json(status_path, status_payload)

    # 9. Retroactively score existing papers (fill in missing tfidf/sbert scores)
    all_papers = read_ndjson(papers_path)
    if config is not None and _rescore_existing(all_papers, config):
        write_ndjson(papers_path, all_papers)

    # 10. Mirror to site/data/ (serialize after normalizing score fields)
    all_papers = _normalize_scores(all_papers)
    write_json(os.path.join(site_data_dir, "papers.json"), all_papers)

    all_history = read_ndjson(history_path)
    write_json(os.path.join(site_data_dir, "run_history.json"), all_history)

    all_rejects = _normalize_scores(read_ndjson(rejects_path))
    write_json(os.path.join(site_data_dir, "rejects.json"), all_rejects)

    if os.path.exists(changelog_path):
        shutil.copy2(changelog_path, os.path.join(site_data_dir, "changelog.md"))

    if os.path.exists(config_path):
        shutil.copy2(config_path, os.path.join(site_data_dir, "survey_config.json"))

    write_json(
        os.path.join(site_data_dir, "system_status.json"),
        status_payload,
    )
