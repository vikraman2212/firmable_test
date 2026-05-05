# Agent Search — Architecture & Operations

## Overview

`POST /agent/search` provides AI-powered company search using a LangChain ReAct agent backed by a local Ollama LLM (`gemma3:4b`). The endpoint streams results as Server-Sent Events (SSE).

## How It Works

```
Client → POST /agent/search
              ↓
        Ollama probe (5s timeout)
       /                        \
  Ollama UP                  Ollama DOWN
      ↓                           ↓
  ReAct agent              Hybrid search
  (streaming)              (silent fallback)
      ↓                           ↓
 SSE events               Single result event
```

### ReAct Loop

The agent uses a Thought → Action → Observation loop, choosing from four tools:

| Tool             | When Used                                                          |
| ---------------- | ------------------------------------------------------------------ |
| `hybrid_search`  | Primary — natural language queries (BM25 + neural)                 |
| `lexical_search` | Exact name/domain lookups (BM25-only)                              |
| `get_facets`     | Exploring available industries/locations                           |
| `web_search`     | External data when indexed results < 3 (requires `TAVILY_API_KEY`) |

### SSE Event Types

```
event: token         {"text": "..."}                     # LLM token stream
event: tool_call     {"tool": "...", "input": {...}}      # tool invoked
event: tool_result   {"tool": "...", "total": N}          # tool returned
event: result        {AgentSearchResponse}                # final structured result
event: error         {"message": "..."}                  # non-fatal error
event: done          {}                                   # stream complete
```

## Configuration

| Env Var             | Default               | Description                                        |
| ------------------- | --------------------- | -------------------------------------------------- |
| `OLLAMA_BASE_URL`   | `http://ollama:11434` | Ollama server URL                                  |
| `OLLAMA_MODEL`      | `gemma3:4b`           | Model to use                                       |
| `OLLAMA_TIMEOUT`    | `30`                  | Inference timeout (seconds)                        |
| `TAVILY_API_KEY`    | ``                    | Tavily API key — leave empty to disable web search |
| `LANGSMITH_TRACING` | `false`               | Enable LangSmith trace logging                     |
| `LANGSMITH_API_KEY` | ``                    | LangSmith API key                                  |

## Graceful Degradation

1. **Ollama unreachable** → silent fallback to hybrid search; `fallback_used: true` in result event
2. **Tavily key absent** → `web_search` tool returns a "not configured" error; agent proceeds without web search
3. **Agent parsing error** → `handle_parsing_errors=True` in `AgentExecutor`; retries with "Invalid output" observation
4. **Zero results** → `agent_explanation` in result event explains what was tried

## Latency Budget

| Component     | Target                              |
| ------------- | ----------------------------------- |
| Ollama probe  | ≤ 5 s                               |
| First token   | ≤ 3 s (depends on model / hardware) |
| Full response | ≤ 30 s                              |
| Fallback path | ≤ 500 ms                            |

## Scaling Notes

- The agent is stateless and shared across all requests. `AgentExecutor` is thread-safe for concurrent reads.
- For 30 RPS of agent traffic: Ollama's concurrency is bounded by GPU memory. Consider running multiple Ollama replicas behind a load balancer.
- LangSmith tracing adds ~50 ms overhead per request. Keep disabled in production unless debugging.
- Web search (Tavily free tier) is rate-limited to ~100 req/min. The agent only calls it as a last resort.

## Observability

Every completed agent request logs a structured `agent_search` event:

```json
{
  "event": "agent_search",
  "query": "tech companies in California",
  "fallback_used": false,
  "tool_calls": ["hybrid_search"],
  "total": 42,
  "duration_ms": 4500
}
```

The HTTP request itself is also logged by the `_RequestLogMW` middleware with `request_id`, `method`, `path`, `status_code`, and `duration_ms`.
