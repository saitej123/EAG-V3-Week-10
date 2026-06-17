"""cua-driver MCP tool schemas exposed to the orchestrator (prefixed cua_).

Unprefixed names are used on the cua-driver MCP wire; the prefix avoids
collisions with eagv3 tools in skills.py / mcp_runner.py.
"""
from __future__ import annotations

# Tools any skill may opt into via agent_config.yaml tools_allowed.
CUA_TOOL_PREFIX = "cua_"

# Read-only subset for researcher (desktop discovery without actions).
CUA_READ_ONLY_TOOLS = frozenset({
    "cua_list_windows",
    "cua_get_window_state",
})

# All prefixed tools we expose to the gateway tool channel.
CUA_TOOL_NAMES = frozenset({
    "cua_list_windows",
    "cua_get_window_state",
    "cua_launch_app",
    "cua_click",
    "cua_type_text",
    "cua_hotkey",
    "cua_press_key",
    "cua_page",
})


def strip_cua_prefix(name: str) -> str:
    if name.startswith(CUA_TOOL_PREFIX):
        return name[len(CUA_TOOL_PREFIX):]
    return name


def is_cua_tool(name: str) -> bool:
    return name in CUA_TOOL_NAMES or name.startswith(CUA_TOOL_PREFIX)


_CUA_TOOL_CATALOG: dict[str, dict] = {
    "cua_list_windows": {
        "name": "cua_list_windows",
        "description": (
            "List top-level desktop windows (cua-driver). Read-only discovery."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    "cua_get_window_state": {
        "name": "cua_get_window_state",
        "description": (
            "Snapshot a window accessibility tree (cua-driver). "
            "Requires pid and window_id from list_windows or launch_app."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pid": {"type": "integer"},
                "window_id": {"type": "integer"},
                "capture_mode": {
                    "type": "string",
                    "enum": ["ax", "som", "vision"],
                    "default": "ax",
                },
                "query": {
                    "type": "string",
                    "description": "Optional filter for large AX trees",
                },
            },
            "required": ["pid", "window_id"],
        },
    },
    "cua_launch_app": {
        "name": "cua_launch_app",
        "description": "Launch a desktop app in the background (cua-driver).",
        "input_schema": {
            "type": "object",
            "properties": {
                "bundle_id": {"type": "string"},
                "name": {"type": "string"},
                "path": {"type": "string"},
                "electron_debugging_port": {"type": "integer"},
            },
        },
    },
    "cua_click": {
        "name": "cua_click",
        "description": "Click by element_index or window-local x,y (cua-driver).",
        "input_schema": {
            "type": "object",
            "properties": {
                "pid": {"type": "integer"},
                "window_id": {"type": "integer"},
                "element_index": {"type": "integer"},
                "x": {"type": "integer"},
                "y": {"type": "integer"},
            },
            "required": ["pid", "window_id"],
        },
    },
    "cua_type_text": {
        "name": "cua_type_text",
        "description": "Type text into the focused or indexed field (cua-driver).",
        "input_schema": {
            "type": "object",
            "properties": {
                "pid": {"type": "integer"},
                "text": {"type": "string"},
                "element_index": {"type": "integer"},
                "window_id": {"type": "integer"},
            },
            "required": ["pid", "text"],
        },
    },
    "cua_hotkey": {
        "name": "cua_hotkey",
        "description": "Press a chord hotkey globally (cua-driver).",
        "input_schema": {
            "type": "object",
            "properties": {
                "keys": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
            "required": ["keys"],
        },
    },
    "cua_press_key": {
        "name": "cua_press_key",
        "description": "Press a single key (cua-driver).",
        "input_schema": {
            "type": "object",
            "properties": {
                "pid": {"type": "integer"},
                "key": {"type": "string"},
                "modifiers": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
            "required": ["key"],
        },
    },
    "cua_page": {
        "name": "cua_page",
        "description": (
            "Interact with a browser/Electron page via CDP (cua-driver). "
            "action: get_text | execute_javascript"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pid": {"type": "integer"},
                "action": {"type": "string"},
                "javascript": {"type": "string"},
            },
            "required": ["pid", "action"],
        },
    },
}


def cua_tool_payload(tool_names: list[str]) -> list[dict]:
    return [_CUA_TOOL_CATALOG[n] for n in tool_names if n in _CUA_TOOL_CATALOG]
