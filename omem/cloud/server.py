"""OMem Cloud Server — FastAPI REST API + MCP over HTTP/SSE.

This is the primary entry point for the OMem managed service.
It exposes every layer of the AgentState SDK over HTTP and streams
MCP events over Server-Sent Events (SSE), making it compatible with
Claude Desktop, Cursor, and any MCP-capable agent.

Endpoints:

  GET   /v1/health                     — liveness + readiness
  GET   /v1/version                    — version info
  GET   /v1/metrics                    — Prometheus-compatible metrics

  POST  /v1/remember                   — store a memory
  POST  /v1/recall                     — retrieve memories
  POST  /v1/explain                    — explain recall decision
  POST  /v1/forget                     — prune low-importance memories

  POST  /v1/state/save                 — save / update session state
  GET   /v1/state/{session_id}         — load session state
  POST  /v1/state/{session_id}/snapshot  — create snapshot
  GET   /v1/state/{session_id}/snapshots — list snapshots
  POST  /v1/state/{session_id}/rollback  — rollback to snapshot
  POST  /v1/state/{session_id}/fork      — fork to new session
  POST  /v1/state/{session_id}/checkpoint — write checkpoint
  POST  /v1/state/{session_id}/resume    — resume from checkpoint
  GET   /v1/state/{session_id}/status    — session dashboard

  POST  /v1/context/build              — build token-optimised context
  POST  /v1/knowledge/link             — assert knowledge edge
  GET   /v1/knowledge/query            — query graph

  GET   /v1/observe/metrics            — session observability metrics
  GET   /v1/observe/traces/{session_id} — session trace events

  GET   /v1/runtime/agents             — list registered agents
  POST  /v1/runtime/register           — register agent

  # MCP over HTTP/SSE (Claude Desktop, Cursor MCP, etc.)
  GET   /mcp/sse                       — SSE transport
  POST  /mcp/messages                  — SSE message send

Run locally:
    uvicorn omem.cloud.server:app --reload --port 8080

Docker:
    docker build -f deploy/docker/Dockerfile.cloud -t omem-cloud .
    docker run -p 8080:8080 omem-cloud

Linode / production:
    See deploy/linode/ for Terraform + systemd configuration.
"""

from __future__ import annotations

import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .. import __version__
from ..agent_state import AgentState

logger = logging.getLogger("omem.cloud.server")
logging.basicConfig(level=os.getenv("OMEM_LOG_LEVEL", "INFO"))

# ─────────────────────────────────────────────────────────────────────────────
# Config — read from environment, suitable for Linode deployment
# ─────────────────────────────────────────────────────────────────────────────

_DB_PATH   = os.getenv("OMEM_DB_PATH", os.path.expanduser("~/.omem/cloud.db"))
_BACKEND   = os.getenv("OMEM_BACKEND", "sqlite")      # sqlite | postgres
_DB_URL    = os.getenv("OMEM_DB_URL")                 # postgres://... (overrides DB_PATH)
_NAMESPACE = os.getenv("OMEM_NAMESPACE", "default")
_API_KEY   = os.getenv("OMEM_API_KEY", "")            # empty = no auth (dev mode)

_START_TIME = time.time()


def _make_agent(session_id: Optional[str] = None, namespace: Optional[str] = None) -> AgentState:
    """Build an AgentState from env-resolved config."""
    return AgentState(
        session_id=session_id,
        namespace=namespace or _NAMESPACE,
        backend=_BACKEND,
        db_path=_DB_URL or _DB_PATH,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Optional API-key middleware
# ─────────────────────────────────────────────────────────────────────────────

async def _check_api_key(request: Request) -> None:
    if not _API_KEY:
        return
    key = request.headers.get("X-API-Key") or request.headers.get("Authorization", "").removeprefix("Bearer ")
    if key != _API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


# ─────────────────────────────────────────────────────────────────────────────
# Lifespan
# ─────────────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("OMem Cloud Server starting  backend=%s  db=%s", _BACKEND, _DB_URL or _DB_PATH)
    yield
    logger.info("OMem Cloud Server shutting down")


# ─────────────────────────────────────────────────────────────────────────────
# App
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="OMem Cloud API",
    description=(
        "Persistent State Infrastructure for AI Agents. "
        "Memory · State · Context · Knowledge · Governance"
    ),
    version=__version__,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic request/response models
# ─────────────────────────────────────────────────────────────────────────────

class RememberRequest(BaseModel):
    content: str
    session_id: Optional[str] = None
    namespace: Optional[str] = None
    importance: float = Field(0.5, ge=0, le=1)
    source: str = "user"


class RecallRequest(BaseModel):
    query: str
    session_id: Optional[str] = None
    namespace: Optional[str] = None
    k: int = Field(5, ge=1, le=50)
    mode: str = "recall"


class ExplainRequest(BaseModel):
    query: str
    session_id: Optional[str] = None
    namespace: Optional[str] = None
    k: int = Field(5, ge=1, le=20)
    mode: str = "recall"


class StateSaveRequest(BaseModel):
    session_id: str
    namespace: Optional[str] = None
    goal: Optional[str] = None
    plan: Optional[List[str]] = None
    status: Optional[str] = None


class SnapshotRequest(BaseModel):
    label: Optional[str] = None


class RollbackRequest(BaseModel):
    snapshot_id: str


class ForkRequest(BaseModel):
    snapshot_id: str
    new_session_id: Optional[str] = None


class KnowledgeLinkRequest(BaseModel):
    subject: str
    predicate: str
    obj: str = Field(alias="object")
    confidence: float = Field(1.0, ge=0, le=1)
    session_id: Optional[str] = None
    namespace: Optional[str] = None

    model_config = {"populate_by_name": True}


class ContextBuildRequest(BaseModel):
    task: str
    session_id: Optional[str] = None
    namespace: Optional[str] = None
    budget_tokens: int = Field(4000, ge=256, le=128000)
    mode: str = "recall"


class AgentRegisterRequest(BaseModel):
    agent_id: str
    session_id: str
    namespace: Optional[str] = None
    capabilities: Optional[List[str]] = None


# ─────────────────────────────────────────────────────────────────────────────
# Health / meta
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/v1/health", tags=["Meta"])
async def health():
    """Liveness and readiness probe. Used by Linode health checks."""
    try:
        agent = _make_agent()
        # Lightweight round-trip: store and retrieve a sentinel memory
        mem_id = agent.remember("__health_check__", importance=0.5)
        assert mem_id
        status = "healthy"
    except Exception as exc:
        logger.warning("Health check failed: %s", exc)
        status = "degraded"

    return {
        "status": status,
        "version": __version__,
        "uptime_seconds": round(time.time() - _START_TIME, 1),
        "backend": _BACKEND,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


@app.get("/v1/version", tags=["Meta"])
async def version():
    return {"version": __version__, "sdk": "omem-os", "protocol": "v1"}


@app.get("/v1/metrics", tags=["Meta"])
async def prometheus_metrics():
    """Minimal Prometheus text-format metrics endpoint."""
    uptime = time.time() - _START_TIME
    body = (
        f"# HELP omem_uptime_seconds Time since server started\n"
        f"# TYPE omem_uptime_seconds gauge\n"
        f"omem_uptime_seconds {uptime:.1f}\n"
        f"# HELP omem_info OMem version info\n"
        f"# TYPE omem_info gauge\n"
        f'omem_info{{version="{__version__}",backend="{_BACKEND}"}} 1\n'
    )
    return Response(content=body, media_type="text/plain")


# ─────────────────────────────────────────────────────────────────────────────
# Memory endpoints
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/v1/remember", tags=["Memory"])
async def remember(req: RememberRequest, request: Request):
    """Store a memory. Returns the memory ID."""
    await _check_api_key(request)
    try:
        agent = _make_agent(req.session_id, req.namespace)
        mem_id = agent.remember(
            req.content,
            importance=req.importance,
            source=req.source,
            namespace=req.namespace,
        )
        return {"memory_id": mem_id, "session_id": req.session_id}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/v1/recall", tags=["Memory"])
async def recall(req: RecallRequest, request: Request):
    """Retrieve top-K relevant memories for a query."""
    await _check_api_key(request)
    try:
        agent = _make_agent(req.session_id, req.namespace)
        memories = agent.recall(req.query, k=req.k, mode=req.mode, namespace=req.namespace)
        return {
            "memories": [
                {
                    "id": m.id,
                    "content": m.content,
                    "importance": m.importance,
                    "score": getattr(m, "score", m.importance),
                    "type": m.type.name,
                    "namespace": m.namespace,
                    "timestamp": m.timestamp,
                }
                for m in memories
            ],
            "count": len(memories),
            "session_id": req.session_id,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/v1/explain", tags=["Memory"])
async def explain(req: ExplainRequest, request: Request):
    """Explain why memories would be recalled — full score decomposition."""
    await _check_api_key(request)
    try:
        agent = _make_agent(req.session_id, req.namespace)
        report = agent.explain(req.query, k=req.k, mode=req.mode, namespace=req.namespace)
        return report.as_dict()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/v1/forget", tags=["Memory"])
async def forget(
    session_id: Optional[str] = None,
    namespace: Optional[str] = None,
    request: Request = None,
):
    """Run heuristic forgetting — prune low-importance memories."""
    await _check_api_key(request)
    try:
        agent = _make_agent(session_id, namespace)
        agent.forget()
        return {"status": "ok", "session_id": session_id}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ─────────────────────────────────────────────────────────────────────────────
# State endpoints
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/v1/state/save", tags=["State"])
async def state_save(req: StateSaveRequest, request: Request):
    """Create or update a session's state."""
    await _check_api_key(request)
    try:
        agent = _make_agent(req.session_id, req.namespace)
        if req.goal:
            agent.set_goal(req.goal)
        if req.plan:
            agent.set_plan(req.plan)
        payload = agent.current_state()
        return payload.to_dict()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/v1/state/{session_id}", tags=["State"])
async def state_load(session_id: str, namespace: Optional[str] = None, request: Request = None):
    """Load the current state payload for a session."""
    await _check_api_key(request)
    try:
        agent = _make_agent(session_id, namespace)
        payload = agent.current_state()
        return payload.to_dict()
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.post("/v1/state/{session_id}/snapshot", tags=["State"])
async def state_snapshot(session_id: str, req: SnapshotRequest, request: Request):
    """Create an immutable snapshot of current session state."""
    await _check_api_key(request)
    try:
        agent = _make_agent(session_id)
        snap = agent.snapshot(label=req.label)
        return {"snapshot_id": snap.id, "label": snap.label, "created_at": snap.created_at}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/v1/state/{session_id}/snapshots", tags=["State"])
async def state_list_snapshots(session_id: str, request: Request):
    """List all snapshots for a session."""
    await _check_api_key(request)
    try:
        agent = _make_agent(session_id)
        snaps = agent.list_snapshots()
        return {
            "snapshots": [
                {"id": s.id, "label": s.label, "created_at": s.created_at}
                for s in snaps
            ],
            "count": len(snaps),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/v1/state/{session_id}/rollback", tags=["State"])
async def state_rollback(session_id: str, req: RollbackRequest, request: Request):
    """Roll back session state to a snapshot."""
    await _check_api_key(request)
    try:
        agent = _make_agent(session_id)
        payload = agent.rollback(req.snapshot_id)
        return payload.to_dict()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/v1/state/{session_id}/fork", tags=["State"])
async def state_fork(session_id: str, req: ForkRequest, request: Request):
    """Fork a session into a new independent branch."""
    await _check_api_key(request)
    try:
        agent = _make_agent(session_id)
        fork_agent = agent.clone(req.new_session_id)
        return {
            "fork_session_id": fork_agent.session_id,
            "source_session_id": session_id,
            "source_snapshot_id": req.snapshot_id,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/v1/state/{session_id}/checkpoint", tags=["State"])
async def state_checkpoint(session_id: str, request: Request):
    """Write a crash-recovery checkpoint."""
    await _check_api_key(request)
    try:
        agent = _make_agent(session_id)
        chk_id = agent.checkpoint()
        return {"checkpoint_id": chk_id, "session_id": session_id}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/v1/state/{session_id}/resume", tags=["State"])
async def state_resume(session_id: str, request: Request):
    """Resume session from latest checkpoint."""
    await _check_api_key(request)
    try:
        agent = _make_agent(session_id)
        payload = agent.resume()
        return payload.to_dict()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/v1/state/{session_id}/status", tags=["State"])
async def state_status(session_id: str, namespace: Optional[str] = None, request: Request = None):
    """Full cross-layer status dashboard for a session."""
    await _check_api_key(request)
    try:
        agent = _make_agent(session_id, namespace)
        return agent.status()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ─────────────────────────────────────────────────────────────────────────────
# Context endpoint
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/v1/context/build", tags=["Context"])
async def context_build(req: ContextBuildRequest, request: Request):
    """Build a token-optimised context bundle for an LLM prompt."""
    await _check_api_key(request)
    try:
        agent = _make_agent(req.session_id, req.namespace)
        bundle = agent.build_context(req.task, budget_tokens=req.budget_tokens, mode=req.mode)
        return {
            "text": bundle.text,
            "token_count": bundle.token_count,
            "budget_tokens": bundle.budget_tokens,
            "savings_vs_naive": bundle.savings_vs_naive,
            "memories_used": bundle.memories_used,
            "state_included": bundle.state_included,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ─────────────────────────────────────────────────────────────────────────────
# Knowledge endpoints
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/v1/knowledge/link", tags=["Knowledge"])
async def knowledge_link(req: KnowledgeLinkRequest, request: Request):
    """Assert a typed knowledge edge."""
    await _check_api_key(request)
    try:
        agent = _make_agent(req.session_id, req.namespace)
        edge_id = agent.learn(req.subject, req.predicate, req.obj, confidence=req.confidence)
        return {"edge_id": edge_id, "subject": req.subject, "predicate": req.predicate, "object": req.obj}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/v1/knowledge/query", tags=["Knowledge"])
async def knowledge_query(
    entity: str = Query(..., description="Entity to query"),
    depth: int = Query(2, ge=1, le=5),
    session_id: Optional[str] = None,
    request: Request = None,
):
    """Query the knowledge graph around an entity."""
    await _check_api_key(request)
    try:
        agent = _make_agent(session_id)
        nodes = agent.knowledge.query(entity, depth=depth)
        return {"entity": entity, "nodes": nodes, "count": len(nodes)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ─────────────────────────────────────────────────────────────────────────────
# Observability endpoints
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/v1/observe/metrics", tags=["Observability"])
async def observe_metrics(
    session_id: Optional[str] = None,
    namespace: Optional[str] = None,
    request: Request = None,
):
    """Aggregated observability metrics for a session."""
    await _check_api_key(request)
    try:
        agent = _make_agent(session_id, namespace)
        return agent.observe.metrics(session_id=session_id, namespace=namespace)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/v1/observe/traces/{session_id}", tags=["Observability"])
async def observe_traces(session_id: str, request: Request):
    """Raw trace events for a session."""
    await _check_api_key(request)
    try:
        agent = _make_agent(session_id)
        traces = agent.observe.traces(session_id)
        return {
            "traces": [
                {
                    "id": t.id,
                    "event_type": t.event_type,
                    "timestamp": t.timestamp,
                    "duration_ms": t.duration_ms,
                    "namespace": t.namespace,
                    "payload": t.payload,
                }
                for t in traces
            ],
            "count": len(traces),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ─────────────────────────────────────────────────────────────────────────────
# Runtime / multi-agent endpoints
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/v1/runtime/register", tags=["Runtime"])
async def runtime_register(req: AgentRegisterRequest, request: Request):
    """Register an agent in the multi-agent runtime."""
    await _check_api_key(request)
    try:
        agent = _make_agent(req.session_id, req.namespace)
        reg = agent.register_agent(
            req.agent_id, req.session_id,
            namespace=req.namespace or _NAMESPACE,
            capabilities=req.capabilities or [],
        )
        return {
            "agent_id": reg.agent_id,
            "session_id": reg.session_id,
            "namespace": reg.namespace,
            "registered_at": reg.registered_at,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/v1/runtime/agents", tags=["Runtime"])
async def runtime_agents(
    namespace: str = Query("default"),
    request: Request = None,
):
    """List all registered agents in a namespace."""
    await _check_api_key(request)
    try:
        agent = _make_agent()
        agents = agent.runtime.list_agents(namespace)
        return {
            "agents": [
                {
                    "agent_id": a.agent_id,
                    "session_id": a.session_id,
                    "status": a.status,
                    "last_heartbeat": a.last_heartbeat,
                }
                for a in agents
            ],
            "count": len(agents),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ─────────────────────────────────────────────────────────────────────────────
# MCP over HTTP/SSE — compatible with Claude Desktop, Cursor, any MCP client
# ─────────────────────────────────────────────────────────────────────────────

_MCP_TOOLS = {
    "remember": {
        "description": "Store a memory in the agent's persistent memory store.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "content":    {"type": "string", "description": "What to remember"},
                "importance": {"type": "number", "description": "0.0–1.0 importance weight"},
                "session_id": {"type": "string", "description": "Session ID (optional)"},
                "namespace":  {"type": "string", "description": "Namespace (optional)"},
            },
            "required": ["content"],
        },
    },
    "recall": {
        "description": "Retrieve relevant memories for a query using hybrid scoring.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query":      {"type": "string", "description": "Search query"},
                "k":          {"type": "integer", "description": "Number of results (1–20)"},
                "session_id": {"type": "string"},
                "namespace":  {"type": "string"},
                "mode":       {"type": "string", "enum": ["recall", "planning", "coding", "chat"]},
            },
            "required": ["query"],
        },
    },
    "explain": {
        "description": "Explain why specific memories would be recalled — full score breakdown.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query":      {"type": "string"},
                "k":          {"type": "integer"},
                "session_id": {"type": "string"},
                "mode":       {"type": "string"},
            },
            "required": ["query"],
        },
    },
    "save_state": {
        "description": "Save the agent's current goal and execution plan.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
                "goal":       {"type": "string"},
                "plan":       {"type": "array", "items": {"type": "string"}},
            },
            "required": ["session_id"],
        },
    },
    "snapshot": {
        "description": "Create a named state snapshot (like a git commit for agent state).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
                "label":      {"type": "string"},
            },
            "required": ["session_id"],
        },
    },
    "rollback": {
        "description": "Roll back agent state to a prior snapshot.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id":   {"type": "string"},
                "snapshot_id":  {"type": "string"},
            },
            "required": ["session_id", "snapshot_id"],
        },
    },
    "checkpoint": {
        "description": "Write a crash-recovery checkpoint for the session.",
        "inputSchema": {
            "type": "object",
            "properties": {"session_id": {"type": "string"}},
            "required": ["session_id"],
        },
    },
    "build_context": {
        "description": "Build a token-optimised LLM context bundle from memories and state.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task":          {"type": "string", "description": "Current task description"},
                "session_id":    {"type": "string"},
                "budget_tokens": {"type": "integer", "description": "Max tokens (default 4000)"},
                "mode":          {"type": "string"},
            },
            "required": ["task"],
        },
    },
    "learn": {
        "description": "Assert a typed knowledge graph relationship.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "subject":    {"type": "string"},
                "predicate":  {"type": "string"},
                "object":     {"type": "string"},
                "confidence": {"type": "number"},
                "session_id": {"type": "string"},
            },
            "required": ["subject", "predicate", "object"],
        },
    },
    "status": {
        "description": "Get the full cross-layer status dashboard for an agent session.",
        "inputSchema": {
            "type": "object",
            "properties": {"session_id": {"type": "string"}},
            "required": [],
        },
    },
}


def _handle_mcp_tool(tool_name: str, args: Dict[str, Any]) -> Any:
    """Dispatch an MCP tool call to the corresponding AgentState method."""
    session_id = args.get("session_id")
    namespace  = args.get("namespace", _NAMESPACE)
    agent = _make_agent(session_id, namespace)

    if tool_name == "remember":
        mem_id = agent.remember(
            args["content"],
            importance=args.get("importance", 0.5),
            namespace=namespace,
        )
        return {"memory_id": mem_id, "status": "remembered"}

    elif tool_name == "recall":
        memories = agent.recall(
            args["query"],
            k=args.get("k", 5),
            mode=args.get("mode", "recall"),
            namespace=namespace,
        )
        return {
            "memories": [
                {"id": m.id, "content": m.content, "importance": m.importance,
                 "score": getattr(m, "score", m.importance)}
                for m in memories
            ],
            "count": len(memories),
        }

    elif tool_name == "explain":
        report = agent.explain(
            args["query"],
            k=args.get("k", 5),
            mode=args.get("mode", "recall"),
        )
        return report.as_dict()

    elif tool_name == "save_state":
        if args.get("goal"):
            agent.set_goal(args["goal"])
        if args.get("plan"):
            agent.set_plan(args["plan"])
        return agent.current_state().to_dict()

    elif tool_name == "snapshot":
        if not session_id:
            raise ValueError("session_id is required for snapshot")
        snap = agent.snapshot(label=args.get("label"))
        return {"snapshot_id": snap.id, "label": snap.label}

    elif tool_name == "rollback":
        if not session_id:
            raise ValueError("session_id is required for rollback")
        payload = agent.rollback(args["snapshot_id"])
        return payload.to_dict()

    elif tool_name == "checkpoint":
        if not session_id:
            raise ValueError("session_id is required for checkpoint")
        chk_id = agent.checkpoint()
        return {"checkpoint_id": chk_id}

    elif tool_name == "build_context":
        bundle = agent.build_context(
            args["task"],
            budget_tokens=args.get("budget_tokens", 4000),
            mode=args.get("mode", "recall"),
        )
        return {
            "text": bundle.text,
            "token_count": bundle.token_count,
            "savings_vs_naive": bundle.savings_vs_naive,
        }

    elif tool_name == "learn":
        edge_id = agent.learn(args["subject"], args["predicate"], args["object"],
                              confidence=args.get("confidence", 1.0))
        return {"edge_id": edge_id}

    elif tool_name == "status":
        return agent.status()

    else:
        raise ValueError(f"Unknown tool: {tool_name}")


@app.get("/mcp/sse", tags=["MCP"])
async def mcp_sse(request: Request):
    """SSE transport for MCP — compatible with Claude Desktop and Cursor.

    This endpoint streams MCP protocol events. Configure in claude_desktop_config.json:

        "omem": {
          "transport": "sse",
          "url": "http://<your-ip>:8080/mcp/sse"
        }
    """
    import asyncio
    import json as _json

    async def event_stream():
        # Initial MCP handshake — emit server capabilities
        capabilities = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {
                "serverInfo": {
                    "name": "omem",
                    "version": __version__,
                },
                "capabilities": {
                    "tools": {"listChanged": False},
                },
            },
        }
        yield f"data: {_json.dumps(capabilities)}\n\n"

        # Keep alive
        while True:
            await asyncio.sleep(15)
            yield ": keepalive\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/mcp/messages", tags=["MCP"])
async def mcp_messages(request: Request):
    """Handle MCP JSON-RPC messages (tools/call, tools/list, etc.)."""
    import json as _json

    body = await request.json()
    method  = body.get("method", "")
    req_id  = body.get("id")
    params  = body.get("params", {})

    def ok(result: Any) -> Dict:
        return {"jsonrpc": "2.0", "id": req_id, "result": result}

    def err(code: int, msg: str) -> Dict:
        return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": msg}}

    try:
        if method == "initialize":
            return ok({
                "protocolVersion": "2024-11-05",
                "serverInfo": {"name": "omem", "version": __version__},
                "capabilities": {"tools": {"listChanged": False}},
            })

        elif method == "tools/list":
            tools = [
                {"name": name, "description": defn["description"], "inputSchema": defn["inputSchema"]}
                for name, defn in _MCP_TOOLS.items()
            ]
            return ok({"tools": tools})

        elif method == "tools/call":
            tool_name = params.get("name", "")
            tool_args  = params.get("arguments", {})
            if tool_name not in _MCP_TOOLS:
                return err(-32601, f"Unknown tool: {tool_name}")

            result = _handle_mcp_tool(tool_name, tool_args)
            return ok({
                "content": [{"type": "text", "text": _json.dumps(result, default=str, indent=2)}],
                "isError": False,
            })

        elif method == "ping":
            return ok({})

        else:
            return err(-32601, f"Method not found: {method}")

    except Exception as exc:
        logger.exception("MCP tool error")
        return err(-32603, str(exc))
