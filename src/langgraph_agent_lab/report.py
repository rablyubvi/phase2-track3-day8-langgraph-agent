"""Report generation helper."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from .metrics import MetricsReport


def render_report_stub(metrics: MetricsReport) -> str:
    rows = []
    for item in metrics.scenario_metrics:
        rows.append(
            f"| {item.scenario_id} | {item.expected_route} | {item.actual_route or ''} | "
            f"{'yes' if item.success else 'no'} | {item.retry_count} | {item.interrupt_count} |"
        )
    table = "\n".join(rows) if rows else "| - | - | - | no | 0 | 0 |"
    return dedent(
        f"""\
        # Day 08 Lab Report

        ## Metrics summary

        - Total scenarios: {metrics.total_scenarios}
        - Success rate: {metrics.success_rate:.2%}
        - Average nodes visited: {metrics.avg_nodes_visited:.2f}
        - Total retries: {metrics.total_retries}
        - Total interrupts: {metrics.total_interrupts}
        - Resume success: {'yes' if metrics.resume_success else 'no'}

        ## Scenario results

        | Scenario | Expected route | Actual route | Success | Retries | Interrupts |
        |---|---|---|---:|---:|---:|
        {table}

        ## Architecture

        - `intake` normalizes the query and records audit metadata.
        - `classify` routes by keyword priority: risky, tool, missing_info, error, simple.
        - `tool` feeds `evaluate`, which either continues or retries until `max_attempts`.
        - `risky_action` goes through approval before continuing.
        - Every route ends at `finalize`.

        ## State schema

        - Append-only: `messages`, `tool_results`, `errors`, `events`
        - Overwrite: `route`, `risk_level`, `attempt`, `final_answer`, `pending_question`, `proposed_action`, `approval`, `evaluation_result`

        ## Failure analysis

        - Retry path exhausts at `max_attempts` and falls into `dead_letter`.
        - Approval rejection can redirect risky requests back to clarification.

        ## Persistence / recovery

        - The graph can run with an in-memory or SQLite checkpointer.
        - `thread_id` is stable per scenario for replay or state inspection.

        ## Improvement plan

        - Add a real tool backend, richer HITL handling, and persisted scenario traces.
        """
    ).strip() + "\n"


def write_report(metrics: MetricsReport, output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_report_stub(metrics), encoding="utf-8")
