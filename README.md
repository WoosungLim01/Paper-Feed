# PaperFeed

An automated academic paper discovery and ranking pipeline.

Fetches papers from three sources — **arXiv**, **Semantic Scholar**, and **OpenAlex** — scores them using dual **TF-IDF + SBERT** relevance scoring against your research topic, and serves the results as a static website.

> For a full visual walkthrough of the pipeline, open [`pipeline_overview.html`](./pipeline_overview.html) in your browser.

---

## How It Works

```
survey_config.json
       │
       ▼
  FETCHER (async, paginated)
  ├── arXiv        — up to 300/query × 7 keywords
  ├── Semantic Scholar — up to 200/query × 7 keywords
  └── OpenAlex     — up to 3 pages × 200 per query
       │
       ▼  ~3,400 raw papers
  DEDUPLICATOR  (DOI → arXiv ID → title hash)
       │
       ▼  ~2,500 unique papers
  SCORER  (TF-IDF + SBERT averaged)
       │
       ▼
  FILTER  (score · date range · metadata)
       │
       ▼  ~1,680 accepted papers
  PUBLISHER  → site/data/*.json  →  Static site
```

---

## Project Structure

```
paper-discovery/
├── app/
│   ├── run.py              # CLI entrypoint
│   ├── config.py           # Config loader + environment variables
│   ├── fetcher.py          # arXiv / Semantic Scholar / OpenAlex crawlers
│   ├── deduplicator.py     # Duplicate removal (DOI · arxiv_id · title hash)
│   ├── scorer.py           # TF-IDF cosine similarity scoring
│   ├── scorer_sbert.py     # SBERT semantic embedding scoring
│   ├── cache.py            # SBERT embedding cache (.npy)
│   ├── validator.py        # Date gap detection · source distribution check
│   ├── publisher.py        # Static site data publisher
│   └── store.py            # NDJSON read/write helpers
├── data/
│   ├── survey_config.json  # Topic, keywords, date range, thresholds
│   ├── papers.ndjson       # Accepted papers (append-only)
│   ├── rejects.ndjson      # Rejected papers with reasons
│   └── run_history.ndjson  # Per-run metadata
├── site/
│   ├── index.html          # Static frontend (no server required)
│   ├── app.js              # Data loading · rendering · search · filter
│   ├── styles.css          # Styles
│   └── data/               # JSON files mirrored for the frontend
├── pipeline_overview.html  # Visual pipeline documentation
└── requirements.txt
```

---

## Installation

```bash
pip install -r requirements.txt
```

> **Note (conda users):** If you're on Python 3.11+, install faiss and regex via conda to avoid binary incompatibilities:
> ```bash
> conda install -c conda-forge faiss-cpu "regex>=2025.10.22"
> ```

---

## Usage

```bash
# Run pipeline with defaults (reads data/survey_config.json)
python -m app.run

# Fetch papers from the last 14 days
python -m app.run --days-back 14

# Override topic for a single run
python -m app.run --topic "robotics"

# Dry run — scores and filters but skips all file writes
python -m app.run --dry-run

# Reset SBERT embedding cache and re-run
python -m app.run --reset-cache
```

---

## Serving the Frontend

```bash
python -m http.server 8080 --directory site
# Open http://localhost:8080
```

---

## Configuration (`data/survey_config.json`)

| Field | Description |
|-------|-------------|
| `topic_overview` | Main research topic (used for SBERT scoring) |
| `search_keywords` | Short keywords sent as API queries (7 recommended) |
| `research_questions` | Questions used as SBERT scoring reference |
| `question_context` | Additional scoring context |
| `timeline_from_year` / `timeline_to_year` | Accepted year range |
| `min_relevance_score` | Minimum score to pass filter (default `0.05`) |

```json
{
  "topic_overview": "artificial intelligence",
  "search_keywords": [
    "artificial intelligence", "machine learning", "deep learning",
    "neural network", "large language model",
    "transformer architecture", "reinforcement learning"
  ],
  "research_questions": [
    "What methods are used to make AI systems explainable?",
    "How are large language models being applied in practice?",
    "What are recent advances in deep learning architectures?"
  ],
  "question_context": "Prioritize papers with practical methods and reproducible experiments.",
  "timeline_from_year": 2023,
  "timeline_to_year": 2026,
  "min_relevance_score": 0.05
}
```

---

## Scoring

Each paper receives a relevance score between 0 and 1, computed as the average of two methods:

| Method | How it works | Strength |
|--------|-------------|----------|
| **TF-IDF** | Keyword frequency + cosine similarity against topic text | Fast, keyword-sensitive |
| **SBERT** | Sentence embedding cosine similarity (`all-MiniLM-L6-v2`) | Context-aware, cached |

SBERT embeddings are cached to disk (`data/embeddings_cache.npy`) so re-runs only encode new papers.

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATA_DIR` | `data` | Data directory path |
| `SITE_DIR` | `site` | Site output directory |
| `DAYS_BACK` | `7` | Days of papers to fetch (+ 2-day buffer applied automatically) |
| `REQUEST_TIMEOUT` | `15` | HTTP timeout in seconds |
| `S2_API_KEY` | *(none)* | Semantic Scholar API key (optional, reduces rate limiting) |

---

## Features

- **Dual scoring** — TF-IDF + SBERT run simultaneously, averaged for the final score
- **Async fetching** — 3 sources crawled concurrently via `asyncio`
- **Pagination** — loop-based page requests with per-query caps
- **Rate limit handling** — 429 → 60s wait; timeout → retry logic
- **Fetch validation** — date gap detection and source distribution report after each run
- **Embedding cache** — SBERT vectors stored in `.npy` to avoid recomputation
- **No LLM required** — fully deterministic, reproducible
- **Static frontend** — no backend server; browser reads JSON files directly
- **Star & hide** — browser-local starring and hiding of papers
- **Run history** — browse papers discovered in each pipeline run

---

## References

- [arxiv-sanity](https://github.com/karpathy/arxiv-sanity-preserver) by Karpathy
- [Scholar Inbox](https://arxiv.org/abs/2504.08385)
