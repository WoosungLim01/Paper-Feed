"""
PaperFeed CLI entrypoint.

Usage:
  python -m app.run                    # run pipeline (TF-IDF + SBERT run simultaneously)
  python -m app.run --topic "robotics" # override topic for one run
  python -m app.run --days-back 14     # override days_back
  python -m app.run --dry-run          # run pipeline but skip file writes
  python -m app.run --reset-cache      # delete SBERT embedding cache
"""
import argparse
import asyncio
import logging
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Load .env from project root if present
_env_path = Path(__file__).resolve().parent.parent / ".env"
if _env_path.exists():
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())

from app import config as _cfg
from app.config import load_config
from app.deduplicator import deduplicate
from app.fetcher import build_queries, fetch_all
from app.publisher import publish
from app.scorer import score_papers
from app.store import write_json

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def _write_status(
    data_dir: str,
    site_dir: str,
    status: str,
    last_run: str | None = None,
    dry_run: bool = False,
) -> None:
    """Write system_status.json to both data/ and site/data/."""
    payload: dict = {"status": status, "last_run": last_run, "scorer": "dual"}
    if not dry_run:
        write_json(os.path.join(data_dir, "system_status.json"), payload)
        site_data = os.path.join(site_dir, "data")
        os.makedirs(site_data, exist_ok=True)
        write_json(os.path.join(site_data, "system_status.json"), payload)


def _print_summary(
    sources_crawled: int,
    raw_count: int,
    dedup_count: int,
    accepted_count: int,
    rejected_count: int,
    site_updated: bool,
    cache_status: str,
) -> None:
    w = 36
    line = "─" * w
    print(f"┌{line}┐")
    print(f"│ {'PaperFeed Run Summary':<{w-1}}│")
    print(f"├{line}┤")
    print(f"│ {'Sources crawled':<22}: {sources_crawled:<{w-25}}│")
    print(f"│ {'Raw candidates':<22}: {raw_count:<{w-25}}│")
    print(f"│ {'After dedup':<22}: {dedup_count:<{w-25}}│")
    print(f"│ {'Accepted':<22}: {accepted_count:<{w-25}}│")
    print(f"│ {'Rejected':<22}: {rejected_count:<{w-25}}│")
    print(f"│ {'Site updated':<22}: {'Yes' if site_updated else 'No':<{w-25}}│")
    print(f"│ {'Scorer':<22}: {'TF-IDF + SBERT (dual)':<{w-25}}│")
    print(f"│ {'Cache':<22}: {cache_status:<{w-25}}│")
    print(f"└{line}┘")


def main() -> None:
    parser = argparse.ArgumentParser(description="PaperFeed pipeline")
    parser.add_argument("--topic", type=str, default=None,
                        help="Override topic_overview")
    parser.add_argument("--days-back", type=int, default=None,
                        help="Override DAYS_BACK")
    parser.add_argument("--dry-run", action="store_true",
                        help="Skip file writes")
    parser.add_argument(
        "--reset-cache",
        action="store_true",
        help="Reset SBERT embedding cache and re-run",
    )
    args = parser.parse_args()

    data_dir = _cfg.DATA_DIR
    site_dir = _cfg.SITE_DIR
    days_back = args.days_back if args.days_back is not None else _cfg.DAYS_BACK
    dry_run = args.dry_run

    # ── Reset cache (if requested) ───────────────────────────────────────────
    if args.reset_cache:
        from app.cache import reset_cache
        reset_cache()
        print("[Cache] Reset complete")

    # 1. Load config
    config = load_config(data_dir)
    if args.topic:
        config.topic_overview = args.topic
        logger.info("Topic overridden to: %s", config.topic_overview)

    # 2. Write status: crawling
    _write_status(data_dir, site_dir, "crawling", dry_run=dry_run)

    # 3. Build queries and log
    queries = build_queries(config)
    logger.info("Queries (%d):", len(queries))
    for q in queries:
        logger.info("  • %s", q)

    # 4. Fetch candidates
    raw_candidates = asyncio.run(fetch_all(config))
    raw_count = len(raw_candidates)

    source_counts = {
        "arxiv": sum(1 for c in raw_candidates if c.get("source") == "arxiv"),
        "semantic_scholar": sum(1 for c in raw_candidates if c.get("source") == "semantic_scholar"),
        "openalex": sum(1 for c in raw_candidates if c.get("source") == "openalex"),
    }
    logger.info("Source counts: arxiv=%d, s2=%d, openalex=%d",
                source_counts["arxiv"], source_counts["semantic_scholar"], source_counts["openalex"])

    # 5. Status: deduplicating
    _write_status(data_dir, site_dir, "deduplicating", dry_run=dry_run)

    # 6. Deduplicate
    candidates = deduplicate(raw_candidates)
    dedup_count = len(candidates)
    logger.info("Dedup: %d raw → %d unique", raw_count, dedup_count)

    # 7. Status: scoring
    _write_status(data_dir, site_dir, "scoring", dry_run=dry_run)

    # 8. Score: TF-IDF + SBERT run simultaneously
    logger.info("Scoring: TF-IDF + SBERT (dual)")
    candidates = score_papers(candidates, config)

    # 9. Status: filtering
    _write_status(data_dir, site_dir, "filtering", dry_run=dry_run)

    # 10. Filter: accepted / rejected
    accepted = []
    rejected = []

    for c in candidates:
        score = c.get("score", 0.0)
        year = c.get("year") or 0
        title = c.get("title", "").strip()
        url = c.get("url", "")

        if not title or not url:
            c["reject_reason"] = "missing_metadata"
            rejected.append(c)
        elif score < config.min_relevance_score:
            c["reject_reason"] = "below_threshold"
            rejected.append(c)
        elif not (config.timeline_from_year <= year <= config.timeline_to_year):
            c["reject_reason"] = "outside_timeline"
            rejected.append(c)
        else:
            accepted.append(c)

    logger.info("Filter: %d accepted, %d rejected", len(accepted), len(rejected))

    # 11. Status: publishing
    _write_status(data_dir, site_dir, "publishing", dry_run=dry_run)

    # 12. Build run_record
    timestamp = datetime.now(tz=timezone.utc).isoformat()
    run_id = uuid.uuid4().hex
    run_record = {
        "run_id": run_id,
        "timestamp": timestamp,
        "architecture": "baseline",
        "scorer": "dual",
        "topic": config.topic_overview,
        "queries": queries,
        "source_counts": source_counts,
        "raw_count": raw_count,
        "dedup_count": dedup_count,
        "accepted_count": len(accepted),
        "rejected_count": len(rejected),
        "errors": [],
    }

    # 13. Publish (unless dry-run)
    site_updated = False
    if not dry_run:
        config_dict = {
            "topic_overview": config.topic_overview,
            "research_questions": config.research_questions,
            "question_context": config.question_context,
            "query_hints": config.query_hints,
            "timeline_from_year": config.timeline_from_year,
            "timeline_to_year": config.timeline_to_year,
            "min_relevance_score": config.min_relevance_score,
        }
        publish(accepted, rejected, run_record, config_dict, data_dir, site_dir, config)
        site_updated = True
    else:
        logger.info("Dry-run mode: skipping file writes.")

    # 14. Final status: idle
    _write_status(data_dir, site_dir, "idle", last_run=timestamp, dry_run=dry_run)

    # 15. Cache info
    from app.cache import cache_info
    info = cache_info()
    cache_status = f"{info['count']} cached ({info['size_kb']} KB)" if info.get("exists") else "No cache"

    # 16. Print summary
    _print_summary(
        sources_crawled=3,
        raw_count=raw_count,
        dedup_count=dedup_count,
        accepted_count=len(accepted),
        rejected_count=len(rejected),
        site_updated=site_updated,
        cache_status=cache_status,
    )


if __name__ == "__main__":
    main()
