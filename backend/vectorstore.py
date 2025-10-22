from __future__ import annotations
from dataclasses import dataclass
from typing import List, Dict, Any, Iterable
import uuid

import chromadb
from chromadb.config import Settings
from openai import OpenAI

from .settings import (
    OPENAI_API_KEY,
    OPENAI_EMBED_MODEL,
    CHROMA_DIR,
    CHROMA_COLLECTION,
)


@dataclass
class VSDoc:
    id: str
    text: str
    metadata: Dict[str, Any]


class OpenAIEmbedder:
    def __init__(self, api_key: str | None, model: str):
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not set")
        self.client = OpenAI(api_key=api_key)
        self.model = model

    def embed(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        resp = self.client.embeddings.create(model=self.model, input=texts)
        # OpenAI Python SDK v1 returns data[].embedding
        return [d.embedding for d in resp.data]


class ChromaVS:
    def __init__(self):
        self.client = chromadb.PersistentClient(
            path=CHROMA_DIR, settings=Settings(anonymized_telemetry=False)
        )
        self.collection = self.client.get_or_create_collection(
            name=CHROMA_COLLECTION, metadata={"hnsw:space": "cosine"}
        )
        self.embedder = OpenAIEmbedder(OPENAI_API_KEY, OPENAI_EMBED_MODEL)

    def reset(self):
        try:
            self.client.delete_collection(CHROMA_COLLECTION)
        except Exception:
            pass
        self.collection = self.client.get_or_create_collection(
            name=CHROMA_COLLECTION, metadata={"hnsw:space": "cosine"}
        )

    def upsert(self, docs: Iterable[VSDoc]):
        docs = list(docs)
        if not docs:
            return
        ids = [d.id for d in docs]
        texts = [d.text for d in docs]
        metas = [d.metadata for d in docs]
        embeds = self.embedder.embed(texts)
        self.collection.upsert(
            ids=ids, documents=texts, metadatas=metas, embeddings=embeds
        )

    def query(self, query_text: str, k: int = 3) -> List[Dict[str, Any]]:
        embeds = self.embedder.embed([query_text])[0]
        res = self.collection.query(query_embeddings=[embeds], n_results=k)
        out = []
        for i in range(len(res["ids"][0])):
            out.append(
                {
                    "id": res["ids"][0][i],
                    "text": res["documents"][0][i],
                    "metadata": res["metadatas"][0][i],
                    "distance": res["distances"][0][i] if "distances" in res else None,
                }
            )
        return out


def new_id(prefix: str = "doc") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"
