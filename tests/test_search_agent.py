"""Unit tests for app.agent.search_agent — httpx and AgentExecutor are mocked."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agent.search_agent import SearchAgent, _SYSTEM_PROMPT, _build_user_input, _probe_ollama, _sse
from app.api.schemas import AgentSearchRequest, CompanyResult, SearchResponse


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_request(**kwargs):
    defaults = {"query": "tech companies in California"}
    defaults.update(kwargs)
    return AgentSearchRequest(**defaults)


def _make_search_response(items=None):
    items = items or [
        CompanyResult(
            company_id="c1",
            name="Acme Corp",
            domain="acme.com",
            industry="Information Technology",
            country="United States",
            city="San Francisco",
            size_range="51 - 200",
        )
    ]
    return SearchResponse(
        items=items, total=len(items), page=1, page_size=10, took_ms=8
    )


def _make_agent(service=None, settings=None):
    if service is None:
        service = MagicMock()
    if settings is None:
        settings = MagicMock()
        settings.llm_provider = "ollama"
        settings.ollama_base_url = "http://ollama:11434"
        settings.ollama_timeout = 30
        settings.agent_recursion_limit = 50
        settings.tavily_api_key = ""
    graph = MagicMock()
    return SearchAgent(graph=graph, service=service, settings=settings)


# ---------------------------------------------------------------------------
# _sse
# ---------------------------------------------------------------------------

def test_sse_format():
    chunk = _sse("token", {"text": "hello"})
    assert chunk == 'event: token\ndata: {"text": "hello"}\n\n'


def test_sse_done():
    chunk = _sse("done", {})
    assert chunk.startswith("event: done\n")


# ---------------------------------------------------------------------------
# _build_user_input
# ---------------------------------------------------------------------------

def test_build_user_input_no_filters():
    req = _make_request(query="tech startups")
    assert _build_user_input(req) == "tech startups"


def test_build_user_input_with_filters():
    req = _make_request(query="fintech", country="United States", city="New York")
    result = _build_user_input(req)
    assert "fintech" in result
    assert "country: United States" in result
    assert "city: New York" in result


def test_build_user_input_with_industry():
    req = _make_request(query="startups", industry=["Healthcare", "Biotech"])
    result = _build_user_input(req)
    assert "Healthcare" in result
    assert "Biotech" in result


def test_system_prompt_blocks_state_as_country_and_uses_lowercase_it():
    assert 'NEVER put a state or province name into the country field' in _SYSTEM_PROMPT
    assert 'NEVER set country and region to the same value' in _SYSTEM_PROMPT
    assert 'If hybrid_search returns 0 results, you MUST call web_search before producing the final answer' in _SYSTEM_PROMPT
    assert 'industry=["information technology"]' in _SYSTEM_PROMPT
    assert 'CompanyResult response model fields: company_id, name, domain, industry, size_range, city, region, country, year_founded, current_employee_estimate, explanation' in _SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# _probe_ollama
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_probe_ollama_returns_true_on_200():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_client = AsyncMock()
    mock_client.get.return_value = mock_resp

    with patch("app.agent.search_agent.httpx.AsyncClient") as MockClient:
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
        result = await _probe_ollama("http://ollama:11434", timeout=5)

    assert result is True


@pytest.mark.asyncio
async def test_probe_ollama_returns_false_on_connection_error():
    with patch("app.agent.search_agent.httpx.AsyncClient") as MockClient:
        MockClient.return_value.__aenter__ = AsyncMock(side_effect=Exception("refused"))
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
        result = await _probe_ollama("http://ollama:11434", timeout=5)

    assert result is False


@pytest.mark.asyncio
async def test_probe_ollama_returns_false_on_non_200():
    mock_resp = MagicMock()
    mock_resp.status_code = 503
    mock_client = AsyncMock()
    mock_client.get.return_value = mock_resp

    with patch("app.agent.search_agent.httpx.AsyncClient") as MockClient:
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
        result = await _probe_ollama("http://ollama:11434", timeout=5)

    assert result is False


# ---------------------------------------------------------------------------
# SearchAgent._fallback_stream
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fallback_stream_emits_result_and_done():
    service = MagicMock()
    service.search.return_value = _make_search_response()
    agent = _make_agent(service=service)
    req = _make_request()

    chunks = []
    async for chunk in agent._fallback_stream(req, t0=0):
        chunks.append(chunk)

    event_types = []
    for chunk in chunks:
        lines = chunk.split("\n")
        for line in lines:
            if line.startswith("event: "):
                event_types.append(line[7:])

    assert "result" in event_types
    assert "done" in event_types


@pytest.mark.asyncio
async def test_fallback_stream_sets_fallback_used_true():
    service = MagicMock()
    service.search.return_value = _make_search_response()
    agent = _make_agent(service=service)
    req = _make_request()

    result_payload = None
    async for chunk in agent._fallback_stream(req, t0=0):
        if chunk.startswith("event: result\n"):
            data = chunk.split("\ndata: ", 1)[1].strip()
            result_payload = json.loads(data)

    assert result_payload is not None
    assert result_payload["fallback_used"] is True
    assert result_payload["agent_path"] == "fallback"


@pytest.mark.asyncio
async def test_fallback_stream_emits_error_on_service_failure():
    service = MagicMock()
    service.search.side_effect = RuntimeError("OpenSearch unavailable")
    agent = _make_agent(service=service)
    req = _make_request()

    event_types = []
    async for chunk in agent._fallback_stream(req, t0=0):
        for line in chunk.split("\n"):
            if line.startswith("event: "):
                event_types.append(line[7:])

    assert "error" in event_types
    assert "done" in event_types


# ---------------------------------------------------------------------------
# SearchAgent.astream — fallback path when Ollama is down
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_astream_uses_fallback_when_ollama_down():
    service = MagicMock()
    service.search.return_value = _make_search_response()
    agent = _make_agent(service=service)
    req = _make_request()

    with patch("app.agent.search_agent._probe_ollama", new=AsyncMock(return_value=False)):
        chunks = [c async for c in agent.astream(req)]

    event_types = []
    for chunk in chunks:
        for line in chunk.split("\n"):
            if line.startswith("event: "):
                event_types.append(line[7:])

    assert "result" in event_types
    assert "done" in event_types
    # Should NOT have called the graph
    agent._graph.astream_events.assert_not_called()


@pytest.mark.asyncio
async def test_astream_emits_preview_result_after_search_tool_returns_hits():
    agent = _make_agent()
    req = _make_request(query="companies in melbourne", page=2, page_size=5)

    async def fake_astream_events(*args, **kwargs):
        yield {
            "event": "on_tool_start",
            "name": "hybrid_search",
            "data": {"input": {"query": "companies in melbourne"}},
        }
        yield {
            "event": "on_tool_end",
            "name": "hybrid_search",
            "data": {
                "output": json.dumps(
                    {
                        "hits": [
                            {
                                "company_id": "mel-1",
                                "name": "Melbourne Tech Co",
                                "industry": "Information Technology",
                                "city": "Melbourne",
                                "country": "Australia",
                            }
                        ],
                        "total": 1,
                    }
                )
            },
        }
        yield {
            "event": "on_chain_end",
            "data": {"output": {"messages": [MagicMock(content="Found 1 company in Melbourne.")] }},
        }

    agent._graph.astream_events = fake_astream_events

    with patch("app.agent.search_agent._probe_ollama", new=AsyncMock(return_value=True)):
        chunks = [c async for c in agent.astream(req)]

    event_types = []
    result_payloads = []
    for chunk in chunks:
        for line in chunk.split("\n"):
            if line.startswith("event: "):
                event_types.append(line[7:])
        if chunk.startswith("event: result\n"):
            data = chunk.split("\ndata: ", 1)[1].strip()
            result_payloads.append(json.loads(data))

    assert event_types[:3] == ["tool_call", "tool_result", "result"]
    assert len(result_payloads) == 2
    assert result_payloads[0]["total"] == 1
    assert result_payloads[0]["page"] == 2
    assert result_payloads[0]["page_size"] == 5
    assert result_payloads[0]["agent_explanation"] is None
    assert result_payloads[1]["agent_explanation"] == "Found 1 company in Melbourne."


@pytest.mark.asyncio
async def test_astream_uses_fallback_when_graph_hits_recursion_limit():
    service = MagicMock()
    service.search.return_value = _make_search_response()
    agent = _make_agent(service=service)
    req = _make_request()

    class GraphRecursionError(Exception):
        pass

    async def failing_astream_events(*args, **kwargs):
        raise GraphRecursionError("Recursion limit of 25 reached without hitting a stop condition")
        yield

    agent._graph.astream_events = failing_astream_events

    with patch("app.agent.search_agent._probe_ollama", new=AsyncMock(return_value=True)):
        chunks = [c async for c in agent.astream(req)]

    event_types = []
    result_payload = None
    for chunk in chunks:
        for line in chunk.split("\n"):
            if line.startswith("event: "):
                event_types.append(line[7:])
        if chunk.startswith("event: result\n"):
            data = chunk.split("\ndata: ", 1)[1].strip()
            result_payload = json.loads(data)

    assert event_types == ["result", "done"]
    assert result_payload is not None
    assert result_payload["fallback_used"] is True
    assert result_payload["agent_path"] == "fallback"
