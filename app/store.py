import json
import os
from typing import Any, List, Set


def read_ndjson(path: str) -> List[dict]:
    """Read file line by line, parse each line as JSON, return list."""
    if not os.path.exists(path):
        return []
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return records


def append_ndjson(path: str, records: List[dict]) -> None:
    """Append records to file, one JSON line per record. Create if not exists."""
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def write_json(path: str, data: Any) -> None:
    """Write data as pretty-printed JSON to path. Create parent dirs if needed."""
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def read_existing_ids(path: str) -> Set[str]:
    """Read papers.ndjson, return set of all paper_id values."""
    records = read_ndjson(path)
    return {r["paper_id"] for r in records if "paper_id" in r}
