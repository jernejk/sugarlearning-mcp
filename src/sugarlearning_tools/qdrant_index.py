"""Qdrant vector index for SugarLearning content."""

from __future__ import annotations

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

from .config import get_settings

_EMBEDDING_MODEL = "all-MiniLM-L6-v2"
_VECTOR_SIZE = 384  # all-MiniLM-L6-v2 output dimension
_encoder = None


def _get_encoder():
    global _encoder
    if _encoder is None:
        from sentence_transformers import SentenceTransformer
        _encoder = SentenceTransformer(_EMBEDDING_MODEL)
    return _encoder


def _get_client() -> QdrantClient:
    settings = get_settings()
    return QdrantClient(url=settings.qdrant_url)


def build_index(snapshot: dict) -> None:
    """Build Qdrant index from a snapshot."""
    settings = get_settings()
    client = _get_client()
    encoder = _get_encoder()
    collection = settings.qdrant_collection

    # Recreate collection
    if client.collection_exists(collection):
        client.delete_collection(collection)

    client.create_collection(
        collection_name=collection,
        vectors_config=VectorParams(size=_VECTOR_SIZE, distance=Distance.COSINE),
    )

    # Collect all texts and payloads first, then batch-encode
    texts: list[str] = []
    payloads: list[dict] = []

    # Modules
    for mod in snapshot.get("modules", []):
        mid = str(mod.get("id", ""))
        texts.append(f"{mod.get('name', '')}. {mod.get('description', '')}")
        payloads.append({
            "type": "module",
            "id": mid,
            "name": mod.get("name"),
            "description": mod.get("description"),
            "manager": mod.get("manager"),
            "items_count": mod.get("items", 0),
            "users_count": mod.get("users", 0),
            "url": f"{settings.base_url}/{settings.company_code}/admin/modules/{mid}",
        })

    # Learning items
    # Build module ID → name lookup
    mod_names = {str(m.get("id")): m.get("name", str(m.get("id"))) for m in snapshot.get("modules", [])}

    for mid, items in snapshot.get("module_items", {}).items():
        mod_name = mod_names.get(mid, mid)
        for item in items:
            texts.append(f"{item.get('name', '')}. {item.get('description', '')}")
            payloads.append({
                "type": "learning_item",
                "id": str(item.get("id", "")),
                "name": item.get("name"),
                "description": item.get("description"),
                "module_id": mid,
                "module_name": mod_name,
                "status": item.get("status"),
            })

    # Batch encode all texts at once (much faster than one-by-one)
    vectors = encoder.encode(texts, show_progress_bar=len(texts) > 50)

    # Build points
    points = [
        PointStruct(id=i, vector=vec.tolist(), payload=payload)
        for i, (vec, payload) in enumerate(zip(vectors, payloads))
    ]

    # Batch upsert
    batch_size = 100
    for i in range(0, len(points), batch_size):
        client.upsert(
            collection_name=collection,
            points=points[i:i + batch_size],
        )

    import sys
    print(f"Indexed {len(points)} items into Qdrant collection '{collection}'", file=sys.stderr)


def search_items(query: str, limit: int = 10) -> list[dict]:
    """Semantic search in Qdrant."""
    settings = get_settings()
    client = _get_client()
    encoder = _get_encoder()

    if not client.collection_exists(settings.qdrant_collection):
        import sys
        print("Qdrant collection not found. Run 'sl index' first.", file=sys.stderr)
        return []

    vector = encoder.encode(query).tolist()
    results = client.query_points(
        collection_name=settings.qdrant_collection,
        query=vector,
        limit=limit,
    )

    return [
        {"score": r.score, "payload": r.payload}
        for r in results.points
    ]
