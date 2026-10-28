"""LangGraph wiring. State is checkpointed in PostgreSQL after every step, so a paused or crashed run resumes.

orchestrator -> document_analysis -> research -> drafting -> verification -> strategy_risk -> monitoring
  -> approval (PAUSE: lawyer approves / edits) -> [edit: back to verification] -> finalize

A draft whose verification is 'blocked' cannot be approved; amber items must each be acknowledged.
"""
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from docketpilot.agents import nodes
from docketpilot.agents.nodes import State, save_draft
from docketpilot.config import get_settings


def approval(state: State) -> dict[str, Any]:
    """Pause until the lawyer decides. Resume value: {"action": "approve", "user_id", "acknowledged": [...]}
    or {"action": "revise", "text": "..."}."""
    report = state["verification"]
    decision = interrupt({"draft_id": state["draft_id"], "release": report["release"],
                          "blocking_items": report["blocking_items"],
                          "items_needing_acknowledgement": report["items_needing_acknowledgement"]})
    if decision.get("action") == "revise":
        return {"draft_text": decision["text"], "approval": {"action": "revise"}}
    if report["release"] == "blocked":
        return {"approval": {"action": "refused", "reason": "Verification found blocking problems. Edit the draft."}}
    missing = set(report["items_needing_acknowledgement"]) - set(decision.get("acknowledged", []))
    if missing:
        return {"approval": {"action": "refused", "reason": f"Acknowledge these items first: {sorted(missing)}"}}
    return {"approval": {"action": "approve", "user_id": decision["user_id"],
                         "acknowledged": decision.get("acknowledged", [])}}


def after_approval(state: State) -> str:
    action = state.get("approval", {}).get("action")
    return {"revise": "verification", "approve": "finalize"}.get(action or "", "approval")


def finalize(state: State) -> dict[str, Any]:
    """Re-insert real names from the local vault and write the Word file (only after approval)."""
    from docketpilot.drafting.docx_out import write_docx
    from docketpilot.privacy import redact as pii
    from docketpilot.privacy import vault

    mapping = vault.load(state["matter_id"])
    body = pii.restore(state["draft_text"], mapping)
    ack = state["approval"].get("acknowledged", [])
    path = nodes.OUTPUTS / state["matter_id"] / f"{state['draft_id']}.docx"
    write_docx(path, body, state["verification"], ack)
    save_draft(state["draft_id"], status="approved", output_file=str(path), acknowledged=ack,
               approved_by=state["approval"]["user_id"], approved_at=datetime.now(UTC), trace=state.get("trace", []))
    return {"status": "approved"}


def _ok(next_node: str) -> Any:
    def route(state: State) -> str:
        return END if state.get("status") == "failed" else next_node
    return route


def build() -> StateGraph:
    g = StateGraph(State)
    for name in ("orchestrator", "document_analysis", "research", "drafting", "verification", "strategy_risk",
                 "monitoring"):
        g.add_node(name, getattr(nodes, name))
    g.add_node("approval", approval)
    g.add_node("finalize", finalize)
    g.add_edge(START, "orchestrator")
    chain = ["orchestrator", "document_analysis", "research", "drafting", "verification", "strategy_risk",
             "monitoring", "approval"]
    for a, b in zip(chain, chain[1:], strict=False):
        g.add_conditional_edges(a, _ok(b))
    g.add_conditional_edges("approval", after_approval)
    g.add_edge("finalize", END)
    return g


@lru_cache
def checkpointer() -> PostgresSaver:
    url = get_settings().database_url.replace("postgresql+asyncpg://", "postgresql://")
    pool = ConnectionPool(url, max_size=4, kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
                          open=True)
    saver = PostgresSaver(pool)  # type: ignore[arg-type]
    saver.setup()
    return saver


@lru_cache
def app() -> Any:
    return build().compile(checkpointer=checkpointer())


def start(draft_id: str, matter_id: str, workflow: str, documents: list[dict[str, Any]],
          doc_type: str | None = None, instructions: str | None = None) -> dict[str, Any]:
    cfg = {"configurable": {"thread_id": draft_id}}
    init: dict[str, Any] = {"draft_id": draft_id, "matter_id": matter_id, "workflow": workflow, "documents": documents,
                            "trace": []}
    if doc_type:
        init["doc_type"] = doc_type
    if instructions:
        init["instructions"] = instructions
    return app().invoke(init, cfg)


def resume(draft_id: str, decision: dict[str, Any]) -> dict[str, Any]:
    cfg = {"configurable": {"thread_id": draft_id}}
    return app().invoke(Command(resume=decision), cfg)


def current(draft_id: str) -> dict[str, Any]:
    snap = app().get_state({"configurable": {"thread_id": draft_id}})
    return {"values": snap.values, "next": list(snap.next),
            "interrupt": [i.value for t in snap.tasks for i in t.interrupts]}
