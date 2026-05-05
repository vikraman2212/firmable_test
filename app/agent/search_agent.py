"""LangChain ReAct search agent with SSE streaming and Ollama fallback gate."""

from __future__ import annotations

import json
import logging
import time
from typing import TYPE_CHECKING, AsyncGenerator, Optional

import httpx
from langchain.agents import create_agent
from langchain_core.messages import HumanMessage
from langchain_ollama import ChatOllama

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


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a company search agent for Firmable, a dataset of 7 million companies.
Help users find companies by using the available search tools.

Guidelines:
- Use hybrid_search as the primary tool for natural language queries
- Use lexical_search only for exact company name or domain lookups
- Use web_search ONLY when hybrid_search returns fewer than 3 results AND the query seeks external data
- Location mapping rules (MUST follow exactly):
    * US states like "California", "Texas", "New York" → region="california" / region="texas" / region="new york" (lowercase)
    * Countries like "United States", "Australia", "UK" → country="united states" / country="australia" / country="united kingdom"
    * Cities like "San Francisco", "Austin" → city="san francisco" / city="austin"
    * NEVER put a state name into the city field
- Map industry synonyms: "tech"/"software"/"IT" → industry=["Information Technology"]
- Valid size_range values (use exactly): "1 - 10", "11 - 50", "51 - 200", "201 - 500", \
"501 - 1000", "1001 - 5000", "5001 - 10000", "10001+"
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


# ---------------------------------------------------------------------------
# SearchAgent
# ---------------------------------------------------------------------------


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

    async def astream(self, request: AgentSearchRequest) -> AsyncGenerator[str, None]:
        """Stream SSE events for an agent search request."""
        t0 = time.monotonic()

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

        tool_calls: list[str] = []
        last_search_result: Optional[dict] = None
        final_explanation: Optional[str] = None
        web_search_used = False

        user_input = _build_user_input(request)
        graph_input = {"messages": [HumanMessage(content=user_input)]}

        try:
            async for event in self._graph.astream_events(graph_input, version="v2"):
                kind = event["event"]
                name = event.get("name", "")

                # LLM token streaming (v2 API uses on_chat_model_stream)
                if kind in ("on_chat_model_stream", "on_llm_stream"):
                    chunk = event["data"].get("chunk")
                    if chunk is not None:
                        text = chunk.content if hasattr(chunk, "content") else str(chunk)
                        if text:
                            yield _sse("token", {"text": text})

                elif kind == "on_tool_start":
                    tool_input = event["data"].get("input", {})
                    if name not in tool_calls:
                        tool_calls.append(name)
                    if name == "web_search":
                        web_search_used = True
                    yield _sse("tool_call", {"tool": name, "input": tool_input})

                elif kind == "on_tool_end":
                    raw_output = event["data"].get("output", "")
                    # LangGraph wraps tool output in a ToolMessage in newer versions
                    if hasattr(raw_output, "content"):
                        raw_output = raw_output.content
                    total = 0
                    try:
                        output_data = (
                            json.loads(raw_output)
                            if isinstance(raw_output, str)
                            else raw_output
                        )
                        if isinstance(output_data, dict):
                            total = output_data.get("total", 0)
                            if "hits" in output_data and name != "web_search":
                                last_search_result = output_data
                    except (json.JSONDecodeError, TypeError):
                        pass
                    yield _sse("tool_result", {"tool": name, "total": total})

                elif kind == "on_chain_end":
                    output = event["data"].get("output")
                    # LangGraph returns {"messages": [...]} as the final output
                    if isinstance(output, dict):
                        messages = output.get("messages", [])
                        if messages:
                            last_msg = messages[-1]
                            content = (
                                last_msg.content
                                if hasattr(last_msg, "content")
                                else str(last_msg)
                            )
                            if content and isinstance(content, str):
                                final_explanation = content

        except Exception as exc:
            logger.error("Agent execution error: %s", exc, exc_info=True)
            yield _sse("error", {"message": str(exc)})

        # Build and emit the final structured result
        took_ms = int((time.monotonic() - t0) * 1000)
        items: list[CompanyResult] = []
        total = 0

        if last_search_result:
            total = last_search_result.get("total", 0)
            items = [
                CompanyResult(
                    company_id=h.get("company_id", ""),
                    name=h.get("name", ""),
                    domain=h.get("domain"),
                    industry=h.get("industry"),
                    size_range=h.get("size_range"),
                    city=h.get("city"),
                    region=h.get("region"),
                    country=h.get("country"),
                    year_founded=h.get("year_founded"),
                    current_employee_estimate=h.get("current_employee_estimate"),
                )
                for h in last_search_result.get("hits", [])
            ]

        if total == 0 and not final_explanation:
            final_explanation = (
                "No companies matched your query. Try broader terms or removing some filters."
            )

        response = AgentSearchResponse(
            items=items,
            total=total,
            page=1,
            page_size=len(items) if items else request.page_size,
            took_ms=took_ms,
            agent_path="web_enriched" if web_search_used else "agent",
            fallback_used=False,
            tool_calls=tool_calls,
            agent_explanation=final_explanation,
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

    llm = ChatOllama(
        base_url=settings.ollama_base_url,
        model=settings.ollama_model,
        temperature=0,
    )
    tools = make_search_tools(service, settings.tavily_api_key)
    graph = create_agent(
        model=llm,
        tools=tools,
        system_prompt=_SYSTEM_PROMPT,
    )
    return SearchAgent(graph=graph, service=service, settings=settings)

