"""Qdrant document retrieval for company and prospect research."""
import hashlib
from typing import Any, Dict, List, Optional

from qdrant_client import QdrantClient

from config.schemas import FilterConfig
from core.retrieval.embeddings import EmbeddingService
from core.retrieval.filter_builder import build_qdrant_filter


class QdrantRetriever:
    def __init__(self, url: str, api_key: Optional[str], collection_name: str,
                 embedding_service: EmbeddingService, top_k: int = 7, score_threshold: float = 0.5):
        self.client = QdrantClient(url=url, api_key=api_key, prefer_grpc=False,
                                   https=url.lower().startswith("https") if url else True, timeout=30)
        self.collection_name = collection_name
        self.embedding_service = embedding_service
        self.top_k = top_k
        self.score_threshold = score_threshold

    async def search(self, query: str, context: Dict[str, Any], top_k: Optional[int] = None,
                     prioritize_images: bool = False, collection_name: Optional[str] = None,
                     filter_config: Optional[FilterConfig] = None) -> List[Dict[str, Any]]:
        collection = collection_name or self.collection_name
        if not collection:
            raise ValueError("collection_name is required for vector search")
        query_vector = await self.embedding_service.embed(query)
        results = self._search_points(query_vector, build_qdrant_filter(filter_config),
                                      top_k or self.top_k, True, collection)
        return self._format_results(results)

    def _search_points(self, query_vector, query_filter, limit, with_payload, collection_name: str):
        if hasattr(self.client, "search"):
            return self.client.search(collection_name=collection_name, query_vector=query_vector,
                                      query_filter=query_filter, limit=limit, with_payload=with_payload)
        response = self.client.query_points(collection_name=collection_name, query=query_vector,
                                             query_filter=query_filter, limit=limit, with_payload=with_payload)
        return getattr(response, "points", response)

    def _format_results(self, results) -> List[Dict[str, Any]]:
        formatted = []
        seen = set()
        for result in results:
            payload = result.payload or {}
            content = payload.get("pageContent") or payload.get("content") or payload.get("text") or ""
            content_hash = hashlib.sha256(content.encode()).digest()
            if content_hash in seen:
                continue
            seen.add(content_hash)
            formatted.append({"content": content, "metadata": payload.get("metadata", payload),
                              "score": result.score, "match_type": "vector"})
        return formatted
