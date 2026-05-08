import re
import hashlib
from collections import Counter

import numpy as np


_embedding_model = None
_embedding_cache = {}


def split_text(text, chunk_size=220):
    words = text.split()
    return [" ".join(words[i:i + chunk_size]) for i in range(0, len(words), chunk_size)]


def retrieve_relevant_chunks(chunks, query, limit=4):
    if not chunks:
        return []

    try:
        return _faiss_search(chunks, query, limit)
    except Exception:
        return _keyword_search(chunks, query, limit)


def _faiss_search(chunks, query, limit):
    import faiss

    model = _get_embedding_model()
    cache_key = hashlib.sha256("\n".join(chunks).encode("utf-8", errors="ignore")).hexdigest()
    chunk_embeddings = _embedding_cache.get(cache_key)
    if chunk_embeddings is None:
        chunk_embeddings = model.encode(chunks, convert_to_numpy=True, normalize_embeddings=True)
        _embedding_cache[cache_key] = chunk_embeddings

    query_embedding = model.encode([query], convert_to_numpy=True, normalize_embeddings=True)

    index = faiss.IndexFlatIP(chunk_embeddings.shape[1])
    index.add(np.asarray(chunk_embeddings, dtype="float32"))
    _, indices = index.search(np.asarray(query_embedding, dtype="float32"), min(limit, len(chunks)))

    return [chunks[i] for i in indices[0] if 0 <= i < len(chunks)]


def _get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        from sentence_transformers import SentenceTransformer

        _embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
    return _embedding_model


def _keyword_search(chunks, query, limit):
    query_terms = [
        term for term in re.findall(r"[a-zA-Z0-9]+", query.lower())
        if len(term) > 2
    ]
    if not query_terms:
        return chunks[:limit]

    query_counts = Counter(query_terms)
    ranked = []
    for chunk in chunks:
        chunk_terms = Counter(re.findall(r"[a-zA-Z0-9]+", chunk.lower()))
        score = sum(chunk_terms[term] * weight for term, weight in query_counts.items())
        if score:
            ranked.append((score, chunk))

    ranked.sort(key=lambda item: item[0], reverse=True)
    return [chunk for _, chunk in ranked[:limit]] or chunks[:limit]
