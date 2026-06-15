"""
SBERT embedding cache management module.

Saves paper embeddings to a .npy file so only new papers are computed on re-runs.
If the model changes, automatically resets the cache by comparing META_PATH.
"""
from __future__ import annotations

import json
import os
from typing import Optional

import numpy as np

# ─── Cache file path constants ───────────────────────────────────────────────
CACHE_DIR = "data"
EMB_PATH  = "data/embeddings_cache.npy"   # numpy embedding array (N, 384)
IDS_PATH  = "data/embeddings_ids.json"    # paper_id list (row order of array)
META_PATH = "data/embeddings_meta.json"   # metadata such as model name


# ─── Internal helpers ────────────────────────────────────────────────────────

def _paper_id(paper: dict) -> str:
    """Extract a unique ID from a paper dict (paper_id preferred, candidate_id as fallback)."""
    return paper.get("paper_id") or paper.get("candidate_id") or ""


# ─── Public API ──────────────────────────────────────────────────────────────

def detect_device() -> str:
    """
    Auto-detect available acceleration device.
    M-series Mac → "mps", NVIDIA GPU → "cuda", otherwise → "cpu"
    """
    try:
        import torch
        if torch.backends.mps.is_available():
            return "mps"
        if torch.cuda.is_available():
            return "cuda"
    except ImportError:
        pass
    return "cpu"


def load_cache(model_name: str) -> tuple[Optional[np.ndarray], list[str]]:
    """
    Load the stored embedding cache.
    Automatically resets the cache if the model has changed.

    Args:
        model_name: name of the SBERT model to use

    Returns:
        (embeddings ndarray of shape (N, 384), list of paper_id strings)
        Returns (None, []) if no cache exists.
    """
    # Check meta file: reset cache if stored model differs from current model
    if os.path.exists(META_PATH):
        with open(META_PATH, encoding="utf-8") as f:
            meta = json.load(f)
        if meta.get("model_name") != model_name:
            print(f"[Cache] Model change detected ({meta.get('model_name')} → {model_name}) → resetting cache")
            reset_cache()

    if os.path.exists(EMB_PATH) and os.path.exists(IDS_PATH):
        embeddings: np.ndarray = np.load(EMB_PATH)
        with open(IDS_PATH, encoding="utf-8") as f:
            ids: list[str] = json.load(f)
        print(f"[Cache] Loaded {len(ids)} embeddings")
        return embeddings, ids

    print("[Cache] No cache found → creating new")
    return None, []


def filter_new_papers(papers: list[dict], cached_ids: list[str]) -> list[dict]:
    """
    Filter and return only papers not present in the cache.

    Args:
        papers:     full list of candidate papers
        cached_ids: list of paper_ids whose embeddings are already stored

    Returns:
        List containing only papers not in the cache.
    """
    cached_set = set(cached_ids)
    new = [p for p in papers if _paper_id(p) not in cached_set]
    print(f"[Cache] Found {len(new)} new papers out of {len(papers)} total")
    return new


def compute_embeddings(papers: list[dict], model: object) -> np.ndarray:
    """
    Compute SBERT embeddings for title+abstract of the given paper list.
    Auto-detects device and processes in batches of 32.

    Args:
        papers: list of papers to compute embeddings for
        model:  SentenceTransformer model instance

    Returns:
        numpy array of shape (N, 384)
    """
    # Handle None values: title + space + abstract
    texts = [
        (p.get("title") or "") + " " + (p.get("abstract") or "")
        for p in papers
    ]
    device = detect_device()
    print(f"[SBERT] Computing {len(texts)} embeddings... (device: {device})")
    return model.encode(
        texts,
        batch_size=32,
        show_progress_bar=True,
        device=device,
        convert_to_numpy=True,
    )


def update_cache(
    cached_embs: Optional[np.ndarray],
    cached_ids: list[str],
    new_embs: np.ndarray,
    new_ids: list[str],
    model_name: str,
) -> tuple[np.ndarray, list[str]]:
    """
    Append new embeddings to the existing cache and save to file.

    Args:
        cached_embs: existing embedding array (None if no cache)
        cached_ids:  existing paper_id list
        new_embs:    newly computed embedding array
        new_ids:     paper_id list of the new papers
        model_name:  model name to store in metadata

    Returns:
        (merged full embeddings, full paper_id list)
    """
    if cached_embs is not None:
        # If existing cache, combine row-wise (vstack)
        all_embs = np.vstack([cached_embs, new_embs])
        all_ids  = cached_ids + new_ids
    else:
        all_embs = new_embs
        all_ids  = new_ids

    os.makedirs(CACHE_DIR, exist_ok=True)
    np.save(EMB_PATH, all_embs)
    with open(IDS_PATH, "w", encoding="utf-8") as f:
        json.dump(all_ids, f, indent=2)
    with open(META_PATH, "w", encoding="utf-8") as f:
        json.dump({"model_name": model_name}, f)

    print(f"[Cache] Saved → total {len(all_ids)} entries")
    return all_embs, all_ids


def align_embeddings(
    papers: list[dict],
    all_embs: np.ndarray,
    all_ids: list[str],
) -> np.ndarray:
    """
    Reorder the embedding array to match the paper list order.
    FAISS indexes by input order, so it must match the papers order.

    Args:
        papers:   paper list whose order to match
        all_embs: full embedding array (including cache)
        all_ids:  paper_id list with 1:1 correspondence to all_embs rows

    Returns:
        Embedding array (N, 384) sorted in the same order as papers.
    """
    id_to_row = {pid: i for i, pid in enumerate(all_ids)}
    return np.array([all_embs[id_to_row[_paper_id(p)]] for p in papers])


def reset_cache() -> None:
    """Delete all embedding cache files."""
    for path in (EMB_PATH, IDS_PATH, META_PATH):
        if os.path.exists(path):
            os.remove(path)
            print(f"[Cache] Deleted: {path}")


def cache_info() -> dict:
    """
    Return a summary of cache status.

    Returns:
        If cache exists: {"exists": True, "count": N, "size_kb": K, "model_name": "..."}
        If no cache:     {"exists": False}
    """
    if os.path.exists(EMB_PATH) and os.path.exists(IDS_PATH):
        with open(IDS_PATH, encoding="utf-8") as f:
            ids: list[str] = json.load(f)
        size_kb = round(os.path.getsize(EMB_PATH) / 1024, 1)
        model_name = None
        if os.path.exists(META_PATH):
            with open(META_PATH, encoding="utf-8") as f:
                model_name = json.load(f).get("model_name")
        return {
            "exists": True,
            "count": len(ids),
            "size_kb": size_kb,
            "model_name": model_name,
        }
    return {"exists": False}
