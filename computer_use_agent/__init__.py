"""Computer Use Agent — vector memory, MCP tools, iteration loop or DAG orchestrator."""

from __future__ import annotations

from typing import TYPE_CHECKING

__all__ = ["ComputerUseAgent", "DagAgent"]

if TYPE_CHECKING:
    from computer_use_agent.agent import ComputerUseAgent
    from computer_use_agent.flow import DagAgent


def __getattr__(name: str):
    if name == "ComputerUseAgent":
        from computer_use_agent.agent import ComputerUseAgent

        return ComputerUseAgent
    if name == "DagAgent":
        from computer_use_agent.flow import DagAgent

        return DagAgent
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
