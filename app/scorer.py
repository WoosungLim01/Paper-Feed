"""
Paper similarity scoring module.

Computes and stores both TF-IDF and SBERT scores on every run.
- tfidf_score: keyword-based cosine similarity
- sbert_score: semantic embedding-based cosine similarity
- score: filtering threshold value (= sbert_score)
"""
import logging
from typing import List

from app.config import SurveyConfig

logger = logging.getLogger(__name__)


def score_papers_tfidf(candidates: List[dict], config: SurveyConfig) -> List[dict]:
    """
    TF-IDF cosine similarity scoring.
    No LLM — deterministic, reproducible for same inputs.

    Side effects:
        Adds tfidf_score field in-place to each item in the candidates list.
    """
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity

    query_text = " ".join([
        config.topic_overview,
        " ".join(config.research_questions),
        config.question_context,
        " ".join(config.query_hints),
    ])

    corpus = [
        (c.get("title") or "") + " " + (c.get("abstract") or "")
        for c in candidates
    ]
    corpus.append(query_text)

    if len(corpus) < 2:
        logger.warning("Not enough documents to score (need at least 1 candidate).")
        return candidates

    vectorizer = TfidfVectorizer(
        max_features=8000,
        stop_words="english",
        ngram_range=(1, 2),
    )
    tfidf_matrix = vectorizer.fit_transform(corpus)
    similarities = cosine_similarity(tfidf_matrix[-1], tfidf_matrix[:-1]).flatten()

    for i, c in enumerate(candidates):
        c["tfidf_score"] = round(float(similarities[i]), 4)

    scores = [c["tfidf_score"] for c in candidates]
    if scores:
        logger.info(
            "[TF-IDF] Score distribution — min: %.4f, max: %.4f, mean: %.4f",
            min(scores), max(scores), sum(scores) / len(scores),
        )

    return candidates


def score_papers(papers: List[dict], config: SurveyConfig) -> List[dict]:
    """
    Compute both TF-IDF and SBERT scores and store them on each paper.

    Stored fields:
        tfidf_score — TF-IDF cosine similarity
        sbert_score — SBERT + FAISS cosine similarity
        score       — filtering reference value (= sbert_score)

    Returns:
        Paper list with both scores added.
        Filtering criterion: sbert_score >= config.min_relevance_score, sorted descending.
    """
    from app.scorer_sbert import score_papers_sbert

    # Step 1: TF-IDF → tfidf_score (compute scores for all papers without filtering)
    score_papers_tfidf(papers, config)

    # Step 2: SBERT → sbert_score (compute scores for all papers then store in-place without filtering)
    orig_min = config.min_relevance_score
    config.min_relevance_score = -1.0          # temporarily remove threshold
    score_papers_sbert(papers, config)
    config.min_relevance_score = orig_min      # restore

    # Step 3: unify score field to sbert_score (used by run.py filter)
    for p in papers:
        p["score"] = p.get("sbert_score", 0.0)

    # Step 4: filter by sbert_score + sort
    result = [p for p in papers if p["score"] >= config.min_relevance_score]
    result.sort(key=lambda x: x["score"], reverse=True)

    logger.info("[Dual] TF-IDF + SBERT → %d papers accepted", len(result))
    return result
