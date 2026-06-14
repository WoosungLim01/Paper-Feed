import os
import shutil
from datetime import datetime, timezone
from typing import List

from app.store import (
    append_ndjson,
    read_existing_ids,
    read_ndjson,
    write_json,
)


def publish(
    accepted: List[dict],
    rejected: List[dict],
    run_record: dict,
    config_dict: dict,
    data_dir: str,
    site_dir: str,
) -> None:
    """Publish pipeline results to data/ and mirror to site/data/."""

    papers_path = os.path.join(data_dir, "papers.ndjson")
    rejects_path = os.path.join(data_dir, "rejects.ndjson")
    history_path = os.path.join(data_dir, "run_history.ndjson")
    changelog_path = os.path.join(data_dir, "changelog.md")
    config_path = os.path.join(data_dir, "survey_config.json")
    status_path = os.path.join(data_dir, "system_status.json")

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

    # 5. Append run_record to data/run_history.ndjson (with paper_ids for history view)
    run_record["paper_ids"] = [p["paper_id"] for p in new_papers if p.get("paper_id")]
    run_record["new_count"] = len(new_papers)
    append_ndjson(history_path, [run_record])

    # 6. Append changelog section to data/changelog.md
    timestamp = run_record.get("timestamp", datetime.now(tz=timezone.utc).isoformat())
    run_id = run_record.get("run_id", "unknown")
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

    # 7. Write system_status.json to data/
    write_json(status_path, {"status": "idle", "last_run": timestamp})

    # 8. Mirror to site/data/
    all_papers = read_ndjson(papers_path)
    write_json(os.path.join(site_data_dir, "papers.json"), all_papers)

    all_history = read_ndjson(history_path)
    write_json(os.path.join(site_data_dir, "run_history.json"), all_history)

    all_rejects = read_ndjson(rejects_path)
    write_json(os.path.join(site_data_dir, "rejects.json"), all_rejects)

    if os.path.exists(changelog_path):
        shutil.copy2(changelog_path, os.path.join(site_data_dir, "changelog.md"))

    if os.path.exists(config_path):
        shutil.copy2(config_path, os.path.join(site_data_dir, "survey_config.json"))

    write_json(
        os.path.join(site_data_dir, "system_status.json"),
        {"status": "idle", "last_run": timestamp},
    )
