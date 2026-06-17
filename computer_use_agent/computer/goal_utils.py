"""Goal helpers for ComputerSkill cascade routing."""
from __future__ import annotations

import re

from cua.client import CuaDriverClient, CuaDriverError

# Apps cua-driver can resolve via name= on Windows.
_KNOWN_LAUNCH_NAMES = frozenset({
    "calculator", "calc", "notepad", "cursor", "code", "vscode",
    "visual studio code", "chrome", "msedge", "edge", "firefox",
    "excel", "word", "paint", "explorer",
})


def is_canvas_fixture_goal(goal: str) -> bool:
    g = goal.lower()
    return (
        "canvas_only" in g
        or ("canvas" in g and "fixture" in g)
        or ("canvas" in g and "red circle" in g)
    )


def is_cursor_goal(text: str) -> bool:
    g = text.lower()
    return (
        "in cursor" in g
        or g.startswith("cursor,")
        or g.startswith("cursor ")
        or "open cursor" in g
        or "notes/computer_use_evidence" in g
        or "layer2b" in g
    )


def is_calculator_goal(text: str) -> bool:
    g = text.lower()
    return (
        "calculator" in g
        or "calc " in g
        or bool(re.search(r"\b\d+\s*(times|x|\*)\s*\d+", g))
        or bool(re.search(r"compute \d+", g))
    )


def _pick_computer_goal(metadata: dict, user_query: str) -> str:
    goal = str(metadata.get("goal") or "").strip()
    question = str(metadata.get("question") or "").strip()
    uq = user_query.strip()
    if goal:
        return goal
    if question and uq:
        for detector in (is_calculator_goal, is_cursor_goal, is_canvas_fixture_goal):
            if detector(uq) and not detector(question):
                return uq
        return question
    return question or uq


def enrich_computer_metadata(metadata: dict, user_query: str) -> dict:
    """Fill app/goal/electron port from USER_QUERY when the Planner omits them."""
    meta = dict(metadata or {})
    goal = _pick_computer_goal(meta, user_query)
    if goal:
        meta["goal"] = goal
    combined = f"{goal} {user_query}".strip()
    low = combined.lower()

    if is_canvas_fixture_goal(combined):
        meta.setdefault("app", "browser")
    elif is_cursor_goal(combined):
        meta.setdefault("app", "Cursor")
        meta.setdefault("electron_debugging_port", 9222)
    elif is_calculator_goal(combined):
        meta.setdefault("app", "Calculator")
    elif not meta.get("app"):
        meta.setdefault("app", "desktop")

    return meta


def is_launchable_app_name(app: str) -> bool:
    if not app or app.lower() in ("desktop", "browser", ""):
        return False
    low = app.lower()
    if is_canvas_fixture_goal(low):
        return False
    if "fixture" in low or "canvas" in low and "only" in low:
        return False
    return any(k in low for k in _KNOWN_LAUNCH_NAMES) or low in _KNOWN_LAUNCH_NAMES


def safe_launch_app(client: CuaDriverClient, app: str) -> dict | None:
    """Launch only when app is a known OS target; never raise."""
    if not is_launchable_app_name(app):
        return None
    try:
        return client.launch_app_named(app)
    except CuaDriverError:
        return None


def normalize_app_for_goal(app: str, goal: str) -> str:
    if is_canvas_fixture_goal(goal):
        return "browser"
    return app
