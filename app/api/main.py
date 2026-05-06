"""FastAPI application entry point."""

import logging
import time
import uuid
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Annotated, Any

from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from opensearchpy import OpenSearch
from opensearchpy.exceptions import ConnectionError as OSConnectionError, NotFoundError as OSNotFoundError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest

from app.api.schemas import (
    AgentSearchRequest,
    FacetsRequest,
    FacetsResponse,
    SearchRequest,
    SearchResponse,
    TagCreateRequest,
    TagCreateResponse,
    TagLookupResponse,
)
from app.tags.repository import TagRepository
from app.logging_config import setup_logging
from app.search.service import SearchService
from app.search.templates import ensure_search_templates
from app.settings import settings

logger = logging.getLogger(__name__)


if TYPE_CHECKING:
    from app.agent.search_agent import SearchAgent


# ── OpenSearch client (shared, created once at startup) ───────────────
def _make_client() -> OpenSearch:
    return OpenSearch(hosts=[settings.opensearch_url])


_client: OpenSearch | None = None
_agent: Any | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging(
        service="api",
        opensearch_url=settings.effective_log_opensearch_url,
        opensearch_enabled=settings.log_opensearch_enabled,
    )
    global _client, _agent
    _client = _make_client()
    ensure_search_templates(_client)
    try:
        from app.agent.search_agent import make_agent

        _agent = make_agent(
            service=SearchService(client=_client, index_name=settings.index_name),
            settings=settings,
        )
    except ImportError as exc:
        logger.warning("Agent initialization skipped: %s", exc)
        _agent = None
    yield
    _client.close()


# ── FastAPI app ───────────────────────────────────────────────────────
app = FastAPI(title="Firmable Search API", version="0.1.0", lifespan=lifespan)

# Allow the static UI opened from file:// (origin=null) and from any localhost port.
# Starlette's CORSMiddleware rejects the literal string "null" as an invalid URL,
# so we use a thin custom middleware that handles the null origin explicitly.
_CORS_ALLOW_ORIGINS_RE = __import__("re").compile(
    r"^(null|https?://(localhost|127\.0\.0\.1)(:\d+)?)$"
)


class _LocalCorsMW(BaseHTTPMiddleware):
    async def dispatch(self, request: StarletteRequest, call_next):
        origin = request.headers.get("origin", "")
        is_allowed = bool(_CORS_ALLOW_ORIGINS_RE.match(origin))

        if request.method == "OPTIONS" and is_allowed:
            from starlette.responses import Response
            return Response(
                status_code=204,
                headers={
                    "Access-Control-Allow-Origin": origin,
                    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                    "Access-Control-Allow-Headers": "Content-Type",
                    "Access-Control-Max-Age": "600",
                },
            )

        response = await call_next(request)
        if is_allowed:
            response.headers["Access-Control-Allow-Origin"] = origin
        return response


app.add_middleware(_LocalCorsMW)


# ── Request logging middleware ────────────────────────────────────────
class _RequestLogMW(BaseHTTPMiddleware):
    async def dispatch(self, request: StarletteRequest, call_next):
        request_id = str(uuid.uuid4())
        t0 = time.monotonic()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            duration_ms = int((time.monotonic() - t0) * 1000)
            level = logging.WARNING if status_code >= 400 else logging.INFO
            logger.log(
                level,
                "http_request",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": status_code,
                    "duration_ms": duration_ms,
                    "client": request.client.host if request.client else None,
                },
            )


app.add_middleware(_RequestLogMW)

# ── Static UI ─────────────────────────────────────────────────────────
_WEB_DIR = Path(__file__).parent.parent.parent / "web"
if _WEB_DIR.is_dir():
    app.mount("/ui", StaticFiles(directory=_WEB_DIR, html=True), name="ui")


def get_search_service() -> SearchService:
    return SearchService(client=_client, index_name=settings.index_name)


SearchServiceDep = Annotated[SearchService, Depends(get_search_service)]


def get_tag_repository() -> TagRepository:
    return TagRepository(
        client=_client,
        index_name=settings.tag_index_name,
        default_user_id=settings.default_tag_user_id,
    )


TagRepositoryDep = Annotated[TagRepository, Depends(get_tag_repository)]


def get_agent() -> "SearchAgent":
    if _agent is None:
        raise HTTPException(status_code=503, detail="Agent unavailable")
    return _agent


AgentDep = Annotated["SearchAgent", Depends(get_agent)]


def _search_target_exists(client: OpenSearch, target: str) -> bool:
    return bool(client.indices.exists_alias(name=target) or client.indices.exists(index=target))


def _not_found_detail(exc: OSNotFoundError) -> str:
    info = getattr(exc, "info", None)
    if isinstance(info, dict):
        error = info.get("error", {})
        if isinstance(error, dict):
            reason = error.get("reason")
            if reason:
                return str(reason)
            root_cause = error.get("root_cause", [])
            if root_cause and isinstance(root_cause[0], dict):
                reason = root_cause[0].get("reason")
                if reason:
                    return str(reason)
    return "Search dependency not found"


# ── Routes ────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    """Liveness probe — always returns 200 if the process is running."""
    return {"status": "ok", "version": app.version}


@app.get("/")
def root():
    """Redirect / to the static UI."""
    return RedirectResponse(url="/ui")


@app.get("/readiness")
def readiness():
    """Readiness probe — checks OpenSearch connectivity and search target presence."""
    try:
        info = _client.info()
        opensearch_version = info.get("version", {}).get("number")
        index_ready = _search_target_exists(_client, settings.index_name)
        if not index_ready:
            raise HTTPException(
                status_code=503,
                detail=f"Search target '{settings.index_name}' does not exist as an alias or index",
            )
        return {
            "status": "ok",
            "opensearch": opensearch_version,
            "index_ready": index_ready,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@app.post("/search", response_model=SearchResponse)
def search(request: SearchRequest, svc: SearchServiceDep):
    """Search companies by query and filters."""
    try:
        result = svc.search(request)
    except OSConnectionError:
        raise HTTPException(status_code=503, detail="Search backend unavailable")
    except OSNotFoundError as exc:
        raise HTTPException(status_code=503, detail=_not_found_detail(exc))
    logger.info(
        "search",
        extra={
            "query": request.query,
            "filters": {
                "industry": request.industry,
                "size_range": request.size_range,
                "country": request.country,
                "city": request.city,
                "year_founded_gte": request.year_founded_gte,
                "year_founded_lte": request.year_founded_lte,
            },
            "page": request.page,
            "page_size": request.page_size,
            "total": result.total,
            "returned": len(result.items),
            "took_ms": result.took_ms,
        },
    )
    return result


@app.post("/facets", response_model=FacetsResponse)
def facets(request: FacetsRequest, svc: SearchServiceDep):
    """Return aggregated facet counts for the given filters."""
    try:
        result = svc.facets(request)
    except OSConnectionError:
        raise HTTPException(status_code=503, detail="Search backend unavailable")
    except OSNotFoundError as exc:
        raise HTTPException(status_code=503, detail=_not_found_detail(exc))
    logger.info(
        "facets",
        extra={
            "industry_buckets": len(result.industry),
            "country_buckets": len(result.country),
        },
    )
    return result


@app.post("/api/tag/", response_model=TagCreateResponse)
def create_tag(request: TagCreateRequest, repo: TagRepositoryDep):
    """Create or upsert a personal tag record for a single company."""
    try:
        record = repo.create_tag(tag_name=request.tag_name, company_id=request.company_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except OSConnectionError:
        raise HTTPException(status_code=503, detail="Search backend unavailable")
    except OSNotFoundError as exc:
        raise HTTPException(status_code=503, detail=_not_found_detail(exc))

    logger.info(
        "tag_create",
        extra={
            "tag_name_normalized": record.tag_name_normalized,
            "company_id": record.company_id,
            "user_id": record.user_id,
        },
    )
    return TagCreateResponse(
        tag_name=record.tag_name_display,
        tag_name_normalized=record.tag_name_normalized,
        company_id=record.company_id,
        user_id=record.user_id,
    )


@app.get("/tag/{tag_name}", response_model=TagLookupResponse)
def get_tagged_companies(tag_name: str, repo: TagRepositoryDep, svc: SearchServiceDep):
    """Resolve tagged companies by tag name using the tag index plus company lookup."""
    try:
        lookup = repo.find_tagged_company_ids(tag_name)
        items = svc.get_companies_by_ids(lookup.company_ids)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except OSConnectionError:
        raise HTTPException(status_code=503, detail="Search backend unavailable")
    except OSNotFoundError as exc:
        raise HTTPException(status_code=503, detail=_not_found_detail(exc))

    logger.info(
        "tag_lookup",
        extra={
            "tag_name_normalized": lookup.tag_name_normalized,
            "company_count": len(items),
        },
    )
    return TagLookupResponse(
        tag_name=lookup.tag_name_display,
        tag_name_normalized=lookup.tag_name_normalized,
        items=items,
        total=len(items),
    )


@app.post("/agent/search")
async def agent_search(request: AgentSearchRequest, agent: AgentDep):
    """Stream company search results from the ReAct agent as Server-Sent Events.

    Event types: token | tool_call | tool_result | result | error | done
    """
    async def _logged_stream():
        t0 = time.monotonic()
        fallback_used = False
        tool_calls: list[str] = []
        total = 0
        yield 'event: status\ndata: {"state":"started"}\n\n'
        async for chunk in agent.astream(request):
            # Parse result event to capture summary metrics for logging
            if chunk.startswith("event: result\n"):
                try:
                    data_line = chunk.split("\ndata: ", 1)[1].strip()
                    payload = __import__("json").loads(data_line)
                    fallback_used = payload.get("fallback_used", False)
                    tool_calls = payload.get("tool_calls", [])
                    total = payload.get("total", 0)
                except Exception:
                    pass
            yield chunk
        logger.info(
            "agent_search",
            extra={
                "query": request.query,
                "fallback_used": fallback_used,
                "tool_calls": tool_calls,
                "total": total,
                "duration_ms": int((time.monotonic() - t0) * 1000),
            },
        )

    return StreamingResponse(
        _logged_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )

