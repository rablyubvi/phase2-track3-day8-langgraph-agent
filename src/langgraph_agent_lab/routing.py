"""Routing functions for conditional edges."""

from __future__ import annotations

from .state import AgentState, Route


def route_after_classify(state: AgentState) -> str:
    route = state.get("route", Route.SIMPLE.value)
    mapping = {
        Route.SIMPLE.value: "answer",
        Route.TOOL.value: "tool",
        Route.MISSING_INFO.value: "clarify",
        Route.RISKY.value: "risky_action",
        Route.ERROR.value: "retry",
    }
    return mapping.get(route, "dead_letter")


def route_after_retry(state: AgentState) -> str:
    if int(state.get("attempt", 0)) >= int(state.get("max_attempts", 3)):
        return "dead_letter"
    return "tool"


def route_after_evaluate(state: AgentState) -> str:
    if state.get("evaluation_result") == "needs_retry":
        return "retry"
    return "answer"


def route_after_approval(state: AgentState) -> str:
    approval = state.get("approval") or {}
    if approval.get("approved"):
        return "tool"
    if approval.get("final_action") == "dead_letter":
        return "dead_letter"
    if approval.get("edit"):
        return "tool"
    return "clarify"
