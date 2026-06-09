"""Planner: convert user task to a Plan. v1 lets the LLM decide via spawn_agent
calls. This module is kept for a future deterministic rule-based planner."""

from __future__ import annotations

from dataclasses import dataclass

from nextcli.orchestrator.runner import Plan, SubTask
from nextcli.agent.events import AgentRole


def fallback_plan(user_task: str) -> Plan:
    """A safe deterministic plan used if the LLM planner is unavailable."""
    return Plan(
        subtasks=[
            SubTask(role=AgentRole.EXPLORER, task=f"Survey: {user_task}"),
            SubTask(role=AgentRole.IMPLEMENTER, task=f"Apply: {user_task}"),
            SubTask(role=AgentRole.REVIEWER, task=f"Verify: {user_task}"),
        ],
        reasoning="Fallback 3-agent plan",
    )
