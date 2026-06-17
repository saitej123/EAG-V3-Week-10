"""Shared cua-driver client for Computer-Use and opt-in MCP tools."""
from .client import CuaDriverClient, CuaDriverError
from .recording import TrajectorySession, start_recording
from .tools import (
    CUA_READ_ONLY_TOOLS,
    CUA_TOOL_NAMES,
    CUA_TOOL_PREFIX,
    cua_tool_payload,
    is_cua_tool,
    strip_cua_prefix,
)

__all__ = [
    "CuaDriverClient",
    "CuaDriverError",
    "TrajectorySession",
    "start_recording",
    "CUA_READ_ONLY_TOOLS",
    "CUA_TOOL_NAMES",
    "CUA_TOOL_PREFIX",
    "cua_tool_payload",
    "is_cua_tool",
    "strip_cua_prefix",
]
