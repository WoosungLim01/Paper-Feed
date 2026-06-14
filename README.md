# PaperFeed

An automated academic paper discovery and ranking system.

Fetches papers from three sources — arXiv, Semantic Scholar, and OpenAlex — scores them using TF-IDF cosine similarity against your research topic, and serves the results as a static site.

## Project Structure

```
paper-discovery/
├── app/
│   ├── run.py              # CLI entrypoint
│   ├── config.py           # Config loader + environment variables
│   ├── fetcher.py          # arXiv / Semantic Scholar / OpenAlex crawlers
│   ├── deduplicator.py     # Priority-based ID deduplication
│   ├── scorer.py           # TF-IDF cosine similarity scoring
│   ├── store.py            # ndjson read/write helpers
│   └── publisher.py        # Static site data publisher
├── data/
│   ├── survey_config.json  # Topic, research questions, date range, thresholds
│   ├── papers.ndjson       # Accepted papers (append-only)
│   ├── rejects.ndjson      # Rejected papers with reasons
│   └── run_history.ndjson  # Per-run metadata
├── site/
│   ├── index.html          # Static frontend (no server required)
│   ├── app.js              # React client logic
│   ├── styles.css          # Custom styles
│   └── data/               # JSON data mirrored for the frontend
└── requirements.txt
```

## Installation

```bash
pip install -r requirements.txt
```

## Usage

```bash
# Run pipeline with defaults (uses data/survey_config.json)
python -m app.run

# Override topic for a single run
python -m app.run --topic "robotics"

# Fetch papers from the last 14 days
python -m app.run --days-back 14

# Dry run — no file writes
python -m app.run --dry-run
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATA_DIR` | `data` | Data directory path |
| `SITE_DIR` | `site` | Site directory path |
| `DAYS_BACK` | `7` | How many days back to fetch papers |
| `MAX_PER_SOURCE` | `50` | Max results per source per query |
| `REQUEST_TIMEOUT` | `15` | HTTP request timeout in seconds |
| `S2_API_KEY` | *(none)* | Semantic Scholar API key (optional, avoids rate limits) |

## Serving the Site

```bash
cd site && python -m http.server 8080
# Open http://localhost:8080 in your browser
```

## Configuration (`data/survey_config.json`)

Edit this file to customize what papers get collected and ranked:

```json
{
  "topic_overview": "artificial intelligence",
  "research_questions": [
    "What methods are used to make AI systems explainable?",
    "How are large language models being applied in practice?",
    "What are recent advances in deep learning architectures?"
  ],
  "question_context": "Prioritize papers with practical methods and reproducible experiments.",
  "query_hints": [
    "machine learning",
    "neural networks",
    "AI applications"
  ],
  "timeline_from_year": 2023,
  "timeline_to_year": 2026,
  "min_relevance_score": 0.05
}
```

## Pipeline

1. **Fetch** — Parallel requests to arXiv XML API, Semantic Scholar Graph API, and OpenAlex REST API
2. **Deduplicate** — Merges duplicates by priority: DOI > arXiv ID > OpenAlex ID > S2 ID > title fingerprint hash
3. **Score** — TF-IDF (1–2-gram, max 8,000 features) + cosine similarity; query text built from topic + questions + context + hints
4. **Filter** — Papers below `min_relevance_score`, outside the date range, or missing required metadata are rejected
5. **Publish** — Appends to ndjson stores and mirrors to `site/data/` for the frontend

## Features

- **No LLM required** — fully deterministic, reproducible scoring
- **Multi-source** — papers found in multiple sources are marked and surfaced
- **Star & hide** — browser-local starring and hiding of individual papers
- **Dark mode** — persistent dark/light toggle
- **Run history** — browse papers discovered in each pipeline run

## References

- [arxiv-sanity](https://github.com/karpathy/arxiv-sanity-preserver) by Karpathy
- [Scholar Inbox](https://arxiv.org/abs/2504.08385)
