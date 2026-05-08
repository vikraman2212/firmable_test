"""LangChain ReAct search agent with SSE streaming and Ollama fallback gate."""

from __future__ import annotations

import dataclasses
import json
import logging
import time
from typing import TYPE_CHECKING, AsyncGenerator, Optional

import httpx
from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage

from app.agent.tools import make_search_tools
from app.api.schemas import (
    AgentSearchRequest,
    AgentSearchResponse,
    CompanyResult,
    SearchRequest,
)
from app.search.service import SearchService
from app.settings import Settings

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph

logger = logging.getLogger(__name__)

_DEFAULT_AGENT_RECURSION_LIMIT = 50  # fallback if settings object is missing the field


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a company search agent for Firmable, a dataset of 7 million companies.
Help users find companies by using the available search tools.

Guidelines:
- Use hybrid_search as the primary tool for natural language queries
- Use lexical_search only for exact company name or domain lookups
- If hybrid_search returns 0 results, you MUST call web_search before producing the final answer
- If hybrid_search returns 1-2 results, use web_search when the user asks for broader/external coverage
- Location mapping rules (MUST follow exactly):
    * US states like "California", "Texas", "New York" → region="california" / region="texas" / region="new york" (lowercase)
    * Countries like "United States", "Australia", "UK" → country="united states" / country="australia" / country="united kingdom"
    * Cities like "San Francisco", "Austin" → city="san francisco" / city="austin"
    * NEVER put a state name into the city field
    * NEVER put a state or province name into the country field
    * If the user mentions a US state and does not explicitly mention a country, set region only and leave country unset
    * NEVER set country and region to the same value
- Map industry synonyms: "tech"/"software"/"IT" → industry=["information technology"]
- Valid size_range values (use exactly): "1 - 10", "11 - 50", "51 - 200", "201 - 500", \
"501 - 1000", "1001 - 5000", "5001 - 10000", "10001+"
- When you describe returned companies, align with the CompanyResult response model fields: company_id, name, domain, industry, size_range, city, region, country, year_founded, current_employee_estimate, explanation
- Do not invent additional company fields outside that response model
- NEVER invent or hallucinate company results — only report what the tools return
- Always provide a final answer summarising what was found
"""


# ---------------------------------------------------------------------------
# Ollama probe
# ---------------------------------------------------------------------------


async def _probe_ollama(base_url: str, timeout: int = 30) -> bool:
    """Return True if Ollama is reachable at base_url within the probe timeout."""
    probe_timeout = min(timeout, 5)
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(base_url, timeout=probe_timeout)
            return resp.status_code == 200
    except Exception:
        return False


# ---------------------------------------------------------------------------
# SSE helper
# ---------------------------------------------------------------------------


def _sse(event_type: str, payload: dict) -> str:
    return f"event: {event_type}\ndata: {json.dumps(payload)}\n\n"


def _agent_response_from_search_result(
    request: AgentSearchRequest,
    search_result: dict,
    *,
    took_ms: int,
    tool_calls: list[str],
    web_search_used: bool,
    final_explanation: Optional[str] = None,
) -> AgentSearchResponse:
    items = [
        CompanyResult(
            company_id=hit.get("company_id", ""),
            name=hit.get("name", ""),
            domain=hit.get("domain"),
            industry=hit.get("industry"),
            size_range=hit.get("size_range"),
            city=hit.get("city"),
            region=hit.get("region"),
            country=hit.get("country"),
            year_founded=hit.get("year_founded"),
            current_employee_estimate=hit.get("current_employee_estimate"),
        )
        for hit in search_result.get("hits", [])
    ]
    return AgentSearchResponse(
        items=items,
        total=search_result.get("total", 0),
        page=request.page,
        page_size=request.page_size,
        took_ms=took_ms,
        agent_path="web_enriched" if web_search_used else "agent",
        fallback_used=False,
        tool_calls=tool_calls,
        agent_explanation=final_explanation,
    )


# ---------------------------------------------------------------------------
# SearchAgent
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class _StreamState:
    tool_calls: list[str] = dataclasses.field(default_factory=list)
    last_search_result: Optional[dict] = None
    final_explanation: Optional[str] = None
    web_search_used: bool = False


class SearchAgent:
    def __init__(
        self,
        graph: "CompiledStateGraph",
        service: SearchService,
        settings: Settings,
    ) -> None:
        self._graph = graph
        self._service = service
        self._settings = settings

    def _graph_config(self) -> dict[str, int]:
        limit = getattr(self._settings, "agent_recursion_limit", _DEFAULT_AGENT_RECURSION_LIMIT)
        if not isinstance(limit, int) or limit <= 0:
            limit = _DEFAULT_AGENT_RECURSION_LIMIT
        return {"recursion_limit": limit}

    @staticmethod
    def _is_recursion_limit_error(exc: Exception) -> bool:
        return (
            type(exc).__name__ == "GraphRecursionError"
            or "Recursion limit" in str(exc)
        )

    # ------------------------------------------------------------------
    # Graph event handlers — each returns a list of SSE strings to yield
    # ------------------------------------------------------------------

    @staticmethod
    def _on_llm_stream(event: dict) -> list[str]:
        chunk = event["data"].get("chunk")
        if chunk is None:
            return []
        raw = chunk.content if hasattr(chunk, "content") else str(chunk)
        # content may be a list of blocks (e.g. [{"type": "text", "text": "..."}])
        if isinstance(raw, list):
            text = "".join(
                block.get("text", "") if isinstance(block, dict) else str(block)
                for block in raw
            )
        else:
            text = raw
        return [_sse("token", {"text": text})] if text else []

    @staticmethod
    def _on_tool_start(event: dict, state: _StreamState) -> list[str]:
        name = event.get("name", "")
        tool_input = event["data"].get("input", {})
        if name not in state.tool_calls:
            state.tool_calls.append(name)
        if name == "web_search":
            state.web_search_used = True
        return [_sse("tool_call", {"tool": name, "input": tool_input})]

    @staticmethod
    def _on_tool_end(
        event: dict,
        state: _StreamState,
        request: AgentSearchRequest,
        t0: float,
    ) -> list[str]:
        name = event.get("name", "")
        raw_output = event["data"].get("output", "")
        if hasattr(raw_output, "content"):
            raw_output = raw_output.content
        total = 0
        try:
            output_data = (
                json.loads(raw_output) if isinstance(raw_output, str) else raw_output
            )
            if isinstance(output_data, dict):
                total = output_data.get("total", 0)
                index_unavailable = output_data.get("error") == "search_index_unavailable"
                if "hits" in output_data and name != "web_search" and not index_unavailable:
                    state.last_search_result = output_data
        except (json.JSONDecodeError, TypeError):
            pass
        events = [_sse("tool_result", {"tool": name, "total": total})]
        if state.last_search_result and total > 0:
            preview = _agent_response_from_search_result(
                request,
                state.last_search_result,
                took_ms=int((time.monotonic() - t0) * 1000),
                tool_calls=state.tool_calls,
                web_search_used=state.web_search_used,
            )
            events.append(_sse("result", json.loads(preview.model_dump_json())))
        return events

    @staticmethod
    def _on_chain_end(event: dict, state: _StreamState) -> None:
        output = event["data"].get("output")
        if not isinstance(output, dict):
            return
        messages = output.get("messages", [])
        if not messages:
            return
        last_msg = messages[-1]
        content = last_msg.content if hasattr(last_msg, "content") else str(last_msg)
        if content and isinstance(content, str):
            state.final_explanation = content

    # ------------------------------------------------------------------
    # Main stream entry point
    # ------------------------------------------------------------------

    async def astream(self, request: AgentSearchRequest) -> AsyncGenerator[str, None]:
        """Stream SSE events for an agent search request."""
        t0 = time.monotonic()

        if self._settings.llm_provider == "ollama":
            ollama_up = await _probe_ollama(
                self._settings.ollama_base_url, self._settings.ollama_timeout
            )
            if not ollama_up:
                logger.warning(
                    "Ollama unavailable at %s — using hybrid fallback",
                    self._settings.ollama_base_url,
                )
                async for chunk in self._fallback_stream(request, t0):
                    yield chunk
                return

        state = _StreamState()
        graph_input = {"messages": [HumanMessage(content=_build_user_input(request))]}

        try:
            async for event in self._graph.astream_events(
                graph_input,
                config=self._graph_config(),
                version="v2",
            ):
                kind = event["event"]

                if kind in ("on_chat_model_stream", "on_llm_stream"):
                    for sse in self._on_llm_stream(event):
                        yield sse

                elif kind == "on_tool_start":
                    for sse in self._on_tool_start(event, state):
                        yield sse

                elif kind == "on_tool_end":
                    for sse in self._on_tool_end(event, state, request, t0):
                        yield sse

                elif kind == "on_chain_end":
                    self._on_chain_end(event, state)

        except Exception as exc:
            if self._is_recursion_limit_error(exc):
                logger.warning("Agent recursion limit reached; using fallback search")
                async for chunk in self._fallback_stream(request, t0):
                    yield chunk
                return
            logger.error("Agent execution error: %s", exc, exc_info=True)
            yield _sse("error", {"message": str(exc)})

        # Build and emit the final structured result
        took_ms = int((time.monotonic() - t0) * 1000)
        total = state.last_search_result.get("total", 0) if state.last_search_result else 0

        if total == 0 and not state.final_explanation:
            state.final_explanation = (
                "AI couldn't find any results for the search criteria. Try a different search."
            )

        response = (
            _agent_response_from_search_result(
                request,
                state.last_search_result,
                took_ms=took_ms,
                tool_calls=state.tool_calls,
                web_search_used=state.web_search_used,
                final_explanation=state.final_explanation,
            )
            if state.last_search_result
            else AgentSearchResponse(
                items=[],
                total=0,
                page=request.page,
                page_size=request.page_size,
                took_ms=took_ms,
                agent_path="web_enriched" if state.web_search_used else "agent",
                fallback_used=False,
                tool_calls=state.tool_calls,
                agent_explanation=state.final_explanation,
            )
        )
        yield _sse("result", json.loads(response.model_dump_json()))
        yield _sse("done", {})

    async def _fallback_stream(
        self, request: AgentSearchRequest, t0: float
    ) -> AsyncGenerator[str, None]:
        """Yield a single result event using the deterministic hybrid search."""
        try:
            search_req = SearchRequest(
                query=request.query,
                industry=request.industry,
                size_range=request.size_range,
                country=request.country,
                city=request.city,
                year_founded_gte=request.year_founded_gte,
                year_founded_lte=request.year_founded_lte,
                page=request.page,
                page_size=request.page_size,
            )
            result = self._service.search(search_req)
            took_ms = int((time.monotonic() - t0) * 1000)
            response = AgentSearchResponse(
                items=result.items,
                total=result.total,
                page=result.page,
                page_size=result.page_size,
                took_ms=took_ms,
                agent_path="fallback",
                fallback_used=True,
                tool_calls=[],
                agent_explanation=None,
            )
            yield _sse("result", json.loads(response.model_dump_json()))
        except Exception as exc:
            logger.error("Fallback stream error: %s", exc)
            yield _sse("error", {"message": str(exc)})
        yield _sse("done", {})


# ---------------------------------------------------------------------------
# Input builder
# ---------------------------------------------------------------------------


def _build_user_input(request: AgentSearchRequest) -> str:
    """Combine the query with any sidebar filter context for the agent."""
    filter_parts: list[str] = []
    if request.industry:
        filter_parts.append(f"industry: {', '.join(request.industry)}")
    if request.country:
        filter_parts.append(f"country: {request.country}")
    if request.city:
        filter_parts.append(f"city: {request.city}")
    if request.size_range:
        filter_parts.append(f"size: {', '.join(request.size_range)}")
    if request.year_founded_gte:
        filter_parts.append(f"founded after: {request.year_founded_gte}")
    if request.year_founded_lte:
        filter_parts.append(f"founded before: {request.year_founded_lte}")
    if filter_parts:
        return f"{request.query} [filters: {'; '.join(filter_parts)}]"
    return request.query


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def make_agent(service: SearchService, settings: Settings) -> SearchAgent:
    """Build and return a configured SearchAgent."""
    if settings.langsmith_tracing and settings.langsmith_api_key:
        import os

        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_API_KEY"] = settings.langsmith_api_key

    # Pass provider-specific kwargs through to init_chat_model.
    # For Ollama, base_url must be set explicitly (Docker hostname differs from localhost).
    llm_kwargs: dict = {"temperature": settings.llm_temperature}
    if settings.llm_provider == "ollama":
        llm_kwargs["base_url"] = settings.ollama_base_url

    llm = init_chat_model(
        f"{settings.llm_provider}:{settings.llm_model}",
        **llm_kwargs,
    )
    tools = make_search_tools(service, settings.tavily_api_key)
    graph = create_agent(
        model=llm,
        tools=tools,
        system_prompt=_SYSTEM_PROMPT
    )
    return SearchAgent(graph=graph, service=service, settings=settings)

