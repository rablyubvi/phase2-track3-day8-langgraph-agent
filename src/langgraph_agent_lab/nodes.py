"""Node implementations for the LangGraph workflow."""

from __future__ import annotations

import re

from .state import AgentState, ApprovalDecision, Route, make_event


def intake_node(state: AgentState) -> dict:
    query = " ".join(state.get("query", "").split())
    has_email = bool(re.search(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b", query))
    has_phone = bool(re.search(r"\b(?:\+?\d[\d\s().-]{7,}\d)\b", query))
    return {
        "query": query,
        "messages": [f"intake:{query[:40]}"],
        "events": [
            make_event(
                "intake",
                "completed",
                "query normalized",
                length=len(query),
                has_email=has_email,
                has_phone=has_phone,
            )
        ],
    }


def classify_node(state: AgentState) -> dict:
    query = state.get("query", "").lower()
    words = [word.strip("?!.,;:()[]{}\"'") for word in query.split()]

    def has_any(*terms: str) -> bool:
        return any(re.search(rf"\b{re.escape(term)}\b", query) for term in terms)

    route = Route.SIMPLE
    risk_level = "low"
    if has_any("refund", "delete", "send", "cancel", "remove", "revoke"):
        route = Route.RISKY
        risk_level = "high"
    elif has_any("status", "order", "lookup", "check", "track", "find", "search"):
        route = Route.TOOL
        risk_level = "medium"
    elif len(words) < 5 and any(word in {"it", "this", "that", "they", "there"} for word in words):
        route = Route.MISSING_INFO
    elif has_any("timeout", "fail", "error", "crash", "unavailable"):
        route = Route.ERROR
        risk_level = "medium"

    return {
        "route": route.value,
        "risk_level": risk_level,
        "events": [make_event("classify", "completed", f"route={route.value}")],
    }


def ask_clarification_node(state: AgentState) -> dict:
    query = state.get("query", "")
    if re.search(r"\border\b", query, re.I):
        question = "Can you share the order id so I can check the status?"
    else:
        question = "Can you share a bit more detail so I can help?"
    return {
        "pending_question": question,
        "final_answer": question,
        "events": [make_event("clarify", "completed", "missing information requested")],
    }


def tool_node(state: AgentState) -> dict:
    attempt = int(state.get("attempt", 0))
    scenario_id = state.get("scenario_id", "unknown")
    if (state.get("route") == Route.ERROR.value or state.get("should_retry")) and attempt < 2:
        result = f"ERROR: transient failure attempt={attempt} scenario={scenario_id}"
    else:
        result = f"mock-tool-result for scenario={scenario_id}"
    return {
        "tool_results": [result],
        "events": [make_event("tool", "completed", f"tool executed attempt={attempt}")],
    }


def risky_action_node(state: AgentState) -> dict:
    query = state.get("query", "")
    return {
        "proposed_action": f"review and approve risky request: {query}",
        "events": [
            make_event(
                "risky_action",
                "pending_approval",
                "approval required",
                risk_level=state.get("risk_level", "unknown"),
            )
        ],
    }


def approval_node(state: AgentState) -> dict:
    import os

    if os.getenv("LANGGRAPH_INTERRUPT", "").lower() == "true":
        from langgraph.types import interrupt

        value = interrupt(
            {
                "proposed_action": state.get("proposed_action"),
                "risk_level": state.get("risk_level"),
            }
        )
        if isinstance(value, dict):
            decision = ApprovalDecision(
                approved=bool(value.get("approved", False)),
                reviewer=str(value.get("reviewer", "human-reviewer")),
                comment=str(value.get("comment", "")),
            )
        else:
            decision = ApprovalDecision(approved=bool(value))
    else:
        decision = ApprovalDecision(approved=True, comment="mock approval for lab")
    return {
        "approval": decision.model_dump(),
        "events": [make_event("approval", "completed", f"approved={decision.approved}")],
    }


def retry_or_fallback_node(state: AgentState) -> dict:
    attempt = int(state.get("attempt", 0)) + 1
    backoff_ms = min(1000, 100 * (2 ** max(0, attempt - 1)))
    return {
        "attempt": attempt,
        "errors": [f"transient failure attempt={attempt}"],
        "events": [
            make_event("retry", "completed", "retry attempt recorded", attempt=attempt, backoff_ms=backoff_ms)
        ],
    }


def answer_node(state: AgentState) -> dict:
    route = state.get("route", Route.SIMPLE.value)
    if route == Route.MISSING_INFO.value and state.get("pending_question"):
        answer = state["pending_question"]
    elif state.get("tool_results"):
        answer = f"I found: {state['tool_results'][-1]}"
    elif route == Route.RISKY.value and (state.get("approval") or {}).get("approved"):
        answer = f"Approved action: {state.get('proposed_action', 'review completed')}"
    else:
        answer = f"Handled route={route} for: {state.get('query', '')}"
    return {
        "final_answer": answer,
        "events": [make_event("answer", "completed", "answer generated")],
    }


def evaluate_node(state: AgentState) -> dict:
    tool_results = state.get("tool_results", [])
    latest = tool_results[-1] if tool_results else ""
    if latest.startswith("ERROR"):
        return {
            "evaluation_result": "needs_retry",
            "events": [make_event("evaluate", "completed", "tool result indicates failure, retry needed")],
        }
    return {
        "evaluation_result": "success",
        "events": [make_event("evaluate", "completed", "tool result satisfactory")],
    }


def dead_letter_node(state: AgentState) -> dict:
    return {
        "final_answer": "Request could not be completed after maximum retry attempts. Logged for manual review.",
        "errors": [f"dead letter at attempt={state.get('attempt', 0)}"],
        "events": [
            make_event("dead_letter", "completed", f"max retries exceeded, attempt={state.get('attempt', 0)}")
        ],
    }


def finalize_node(state: AgentState) -> dict:
    return {"events": [make_event("finalize", "completed", "workflow finished")]}
