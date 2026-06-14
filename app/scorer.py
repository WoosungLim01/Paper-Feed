import logging
from typing import List

from app.config import SurveyConfig

logger = logging.getLogger(__name__)


def score_papers(candidates: List[dict], config: SurveyConfig) -> List[dict]:
    """
    TF-IDF cosine similarity scoring.
    No LLM — deterministic, reproducible for same inputs.
    Reference: Karpathy arxiv-sanity analyze.py + Dynamic-LR baseline.md section 7.
    """
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity

    # Build query text from full config (richer than just keywords)
    query_text = " ".join([
        config.topic_overview,
        " ".join(config.research_questions),
        config.question_context,
        " ".join(config.query_hints),
    ])

    # Build corpus: title + abstract per candidate
    corpus = [
        (c.get("title") or "") + " " + (c.get("abstract") or "")
        for c in candidates
    ]
    corpus.append(query_text)  # query document appended last

    if len(corpus) < 2:
        logger.warning("Not enough documents to score (need at least 1 candidate).")
        return candidates

    # TF-IDF: ngram_range=(1,2) captures bigrams like "machine learning"
    vectorizer = TfidfVectorizer(
        max_features=8000,
        stop_words="english",
        ngram_range=(1, 2),
    )
    tfidf_matrix = vectorizer.fit_transform(corpus)

    query_vec = tfidf_matrix[-1]
    paper_vecs = tfidf_matrix[:-1]
    similarities = cosine_similarity(query_vec, paper_vecs).flatten()

    for i, c in enumerate(candidates):
        c["score"] = round(float(similarities[i]), 4)

    scores = [c["score"] for c in candidates]
    if scores:
        logger.info(
            "Score distribution — min: %.4f, max: %.4f, mean: %.4f",
            min(scores),
            max(scores),
            sum(scores) / len(scores),
        )

    return candidates
