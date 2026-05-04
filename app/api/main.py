"""FastAPI application entry point."""

from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI
from opensearchpy import OpenSearch

from app.api.schemas import SearchRequest, SearchResponse
from app.search.service import SearchService
from app.settings import settings


# ── OpenSearch client (shared, created once at startup) ───────────────
def _make_client() -> OpenSearch:
    return OpenSearch(hosts=[settings.opensearch_url])


_client: OpenSearch | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _client
    _client = _make_client()
    yield
    _client.close()


# ── FastAPI app ───────────────────────────────────────────────────────
app = FastAPI(title="Firmable Search API", version="0.1.0", lifespan=lifespan)


# ── Dependency: search service ────────────────────────────────────────
def get_search_service() -> SearchService:
    return SearchService(client=_client, index_name=settings.index_name)


SearchServiceDep = Annotated[SearchService, Depends(get_search_service)]


# ── Routes ────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    """Liveness probe — always returns 200 if the process is running."""
    return {"status": "ok"}


@app.get("/readiness")
def readiness():
    """Readiness probe — checks OpenSearch connectivity."""
    try:
        info = _client.info()
        return {"status": "ok", "opensearch": info.get("version", {}).get("number")}
    except Exception as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail=str(exc))


@app.post("/search", response_model=SearchResponse)
def search(request: SearchRequest, svc: SearchServiceDep):
    """Search companies by query and filters."""
    return svc.search(request)
