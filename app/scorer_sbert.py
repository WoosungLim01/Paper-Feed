"""
SBERT + FAISS semantic similarity scoring module.

Key differences from TF-IDF:
- TF-IDF: word-frequency based → good for exact keyword matching, cannot handle synonyms
- SBERT:  semantic embedding based → understands "deep learning" ≈ "neural network"

Scoring flow:
  paper text  → SBERT encoding → 384-dimensional vector
  query text  → SBERT encoding → 384-dimensional vector
  FAISS IndexFlatIP → L2-normalized inner product = cosine similarity
  → score in range 0.0 ~ 1.0
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.config import SurveyConfig

logger = logging.getLogger(__name__)

# SBERT model: ~80MB, 384-dimensional embeddings, excellent balance of speed and quality
MODEL_NAME = "all-MiniLM-L6-v2"


def score_papers_sbert(papers: list[dict], config: "SurveyConfig") -> list[dict]:
    """
    SBERT + FAISS semantic similarity scoring.

    Args:
        papers: list of candidate papers (already deduplicated)
        config: survey config (topic, questions, keywords, minimum score)

    Returns:
        Paper list with sbert_score field added.
        Only papers with sbert_score >= config.min_relevance_score are returned (sorted descending).

    Side effects:
        Adds sbert_score field in-place to every item in the papers list.
        Even papers not included in the return list will have the sbert_score field set.
    """
    import faiss
    import numpy as np
    from sentence_transformers import SentenceTransformer

    from app.cache import (
        align_embeddings,
        compute_embeddings,
        filter_new_papers,
        load_cache,
        update_cache,
    )

    # ── Step 1: Load SBERT model ──────────────────────────────────────────────
    # Downloads ~80MB model file on first run (reused from HuggingFace cache afterward)
    logger.info("[SBERT] Loading model: %s", MODEL_NAME)
    model = SentenceTransformer(MODEL_NAME)

    # ── Step 2: Load embedding cache (auto-reset if model changed) ───────────
    cached_embs, cached_ids = load_cache(MODEL_NAME)

    # ── Step 3: Compute embeddings only for new papers (cache hits are skipped) ─
    new_papers = filter_new_papers(papers, cached_ids)
    if new_papers:
        # SBERT-encode only papers not in cache → GPU/MPS acceleration applied
        new_embs = compute_embeddings(new_papers, model)
        new_ids  = [p.get("paper_id") or p.get("candidate_id") or "" for p in new_papers]
        # Append new embeddings to existing cache and save to file
        all_embs, all_ids = update_cache(cached_embs, cached_ids, new_embs, new_ids, MODEL_NAME)
    else:
        # All papers are already cached → reuse from file without network
        logger.info("[SBERT] All papers are cached — skipping computation")
        all_embs, all_ids = cached_embs, cached_ids

    # ── Step 4: Align embeddings to match paper order ────────────────────────
    # FAISS indexes by add() order → must match the papers list order
    paper_embs = align_embeddings(papers, all_embs, all_ids)

    # ── Step 5: Build FAISS index (in-memory, cosine similarity) ─────────────
    # IndexFlatIP = inner product brute-force index (100% accuracy)
    # Inner product of L2-normalized unit vectors = cosine similarity (mathematically equivalent)
    dimension  = paper_embs.shape[1]           # 384 (for all-MiniLM-L6-v2)
    index      = faiss.IndexFlatIP(dimension)
    normalized = paper_embs.copy().astype("float32")
    faiss.normalize_L2(normalized)             # convert each vector to a unit vector
    index.add(normalized)                      # add paper vectors to index

    # ── Step 6: Generate query embedding ─────────────────────────────────────
    # Combine topic + research questions + context + hint keywords into one query text
    # Richer query text → more accurate similarity measurement
    query_text = " ".join([
        config.topic_overview,
        " ".join(config.research_questions),
        config.question_context,
        " ".join(config.query_hints),
    ])
    query_emb = model.encode([query_text], convert_to_numpy=True).astype("float32")
    faiss.normalize_L2(query_emb)              # convert query to unit vector as well

    # ── Step 7: FAISS search — compute similarity scores for all papers ───────
    # k=len(papers) → return top-K results = rankings and scores for all papers
    # scores[0]: array of similarity scores sorted in descending order
    # indices[0]: FAISS indices of those scores (based on add() order)
    scores, indices = index.search(query_emb, k=len(papers))
    # Convert FAISS results to original index → score mapping
    score_map = {
        int(indices[0][i]): float(scores[0][i])
        for i in range(len(papers))
    }

    # ── Step 8: Attach sbert_score + score fields to each paper (in-place) ──
    # i from enumerate(papers) = FAISS add() order = score_map key
    # Also set score field → because run.py filter operates on score
    for i, paper in enumerate(papers):
        paper["sbert_score"] = round(score_map.get(i, 0.0), 4)
        paper["score"] = paper["sbert_score"]  # backward compat: used by run.py filter

    # ── Step 9: Filter by minimum score then sort descending ─────────────────
    min_score = config.min_relevance_score
    result = [p for p in papers if p["sbert_score"] >= min_score]
    result.sort(key=lambda x: x["sbert_score"], reverse=True)

    # Log score distribution (for debugging and threshold tuning reference)
    all_scores = [p["sbert_score"] for p in papers]
    if all_scores:
        logger.info(
            "[SBERT+FAISS] Score distribution — min: %.4f, max: %.4f, mean: %.4f",
            min(all_scores),
            max(all_scores),
            sum(all_scores) / len(all_scores),
        )

    print(f"[SBERT+FAISS] {len(papers)} papers → {len(result)} after filtering")
    return result
