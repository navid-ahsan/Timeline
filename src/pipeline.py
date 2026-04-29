import os
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.types import Send, interrupt

from state import PatientState
from nodes import (
    route_documents,
    process_document,
    merge_events,
    select_top_10,
    evaluate_timeline,
    save_with_audit,
)


def _route_eval(state: PatientState) -> str:
    if state.get("eval_passed"):
        return "human_review"
    if state.get("retry_count", 0) < 2:
        return "select_top_10"
    return "human_review"  # force exit after max retries


def human_review_node(state: PatientState) -> dict:
    """LangGraph interrupt — social worker approves or edits the timeline."""
    approved_timeline = interrupt({
        "proposed_timeline": state["top_10_timeline"],
        "total_events_found": len(state.get("all_events", [])),
        "message": "Tarkista ja hyväksy aikajana.",
    })
    return {
        "top_10_timeline": approved_timeline,
        "human_approved": True,
    }


def build_graph(checkpointer) -> StateGraph:
    builder = StateGraph(PatientState)

    builder.add_node("route_documents",  route_documents)
    builder.add_node("process_document", process_document)
    builder.add_node("merge_events",     merge_events)
    builder.add_node("select_top_10",    select_top_10)
    builder.add_node("evaluate",         evaluate_timeline)
    builder.add_node("human_review",     human_review_node)
    builder.add_node("save",             save_with_audit)

    builder.add_edge(START, "route_documents")
    builder.add_conditional_edges(
        "route_documents",
        lambda s: [
            Send("process_document", {"doc": d, "patient_id": s["patient_id"]})
            for d in s["current_documents"]
        ],
        ["process_document"],
    )
    builder.add_edge("process_document", "merge_events")
    builder.add_edge("merge_events",     "select_top_10")
    builder.add_edge("select_top_10",    "evaluate")
    builder.add_conditional_edges("evaluate", _route_eval)
    builder.add_edge("human_review",     "save")
    builder.add_edge("save",             END)

    return builder.compile(
        checkpointer=checkpointer,
        interrupt_before=["human_review"],
    )


def get_pipeline():
    db_url = os.environ["DATABASE_URL"]
    with PostgresSaver.from_conn_string(db_url) as checkpointer:
        checkpointer.setup()
        return build_graph(checkpointer)
