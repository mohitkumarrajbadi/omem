"""LlamaIndex integration — OMem as a retriever and document bridge.

The adapter exposes OMem as a retrieval backend for LlamaIndex query chains.
It also provides a lightweight bridge for ingesting LlamaIndex Document objects
into OMem with namespace and metadata support.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..api import OMem
from ..types import Memory

try:
    from llama_index import Document
    from llama_index.retrievers.base import BaseRetriever
except Exception:
    Document = None  # type: ignore[assignment]
    BaseRetriever = object  # type: ignore[assignment]


class OMemLlamaIndexRetriever(BaseRetriever):
    """LlamaIndex-compatible retriever backed by OMem."""

    def __init__(
        self,
        omem: Optional[OMem] = None,
        namespace: str = "default",
        top_k: int = 5,
    ):
        self.omem = omem or OMem()
        self.namespace = namespace
        self.top_k = top_k

    def retrieve(self, query: str, **kwargs: Any) -> List[Any]:
        results = self.omem.recall(query, top_k=self.top_k, namespace=self.namespace)
        return [self._to_document(m) for m in results]

    async def aretrieve(self, query: str, **kwargs: Any) -> List[Any]:
        return self.retrieve(query, **kwargs)

    def _to_document(self, memory: Memory) -> Any:
        metadata = {
            "id": memory.id,
            "type": memory.type.name,
            "importance": memory.importance,
            "namespace": memory.namespace,
            "source": memory.source,
        }

        if Document is not None:
            return Document(text=memory.content, metadata=metadata)
        return {"text": memory.content, "metadata": metadata}


class OMemLlamaIndexAdapter:
    """Simple bridge for ingesting and converting LlamaIndex documents."""

    def __init__(
        self,
        omem: Optional[OMem] = None,
        namespace: str = "default",
        source: str = "llama_index",
    ):
        self.omem = omem or OMem()
        self.namespace = namespace
        self.source = source

    def add_text(
        self,
        content: str,
        importance: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        return self.omem.add(
            content,
            importance=importance,
            namespace=self.namespace,
            source=self.source,
            metadata=metadata,
        )

    def add_document(self, document: Any, importance: Optional[float] = None) -> str:
        if Document is not None and isinstance(document, Document):
            text = document.text
            metadata = getattr(document, "metadata", None)
        elif isinstance(document, dict):
            text = document.get("text", "")
            metadata = document.get("metadata")
        else:
            text = str(document)
            metadata = None

        return self.add_text(text, importance=importance, metadata=metadata)

    def pull_documents(self, query: str, top_k: Optional[int] = None) -> List[Any]:
        retriever = OMemLlamaIndexRetriever(
            omem=self.omem,
            namespace=self.namespace,
            top_k=top_k or 5,
        )
        return retriever.retrieve(query)


__all__ = ["OMemLlamaIndexRetriever", "OMemLlamaIndexAdapter"]
