"""Layer 1: read-only desktop state via cua-driver (no LLM, no vision)."""
from __future__ import annotations

from typing import Any

from cua.client import CuaDriverClient, CuaDriverError
from cua.response_utils import as_dict, windows_from_response

from .goal_utils import is_canvas_fixture_goal, is_launchable_app_name, safe_launch_app


def _pick_window(windows: list[dict], app_hint: str) -> dict | None:
    if not windows:
        return None
    hint = app_hint.lower()
    for w in windows:
        title = str(w.get("title") or "").lower()
        name = str(w.get("name") or "").lower()
        if hint in title or hint in name:
            return w
    return windows[0]


async def try_read(
    client: CuaDriverClient,
    *,
    app: str,
    goal: str,
    pid: int | None = None,
    window_id: int | None = None,
) -> dict[str, Any] | None:
    """Return {result, pid, window_id, snapshot} when read-only state answers goal."""
    if is_canvas_fixture_goal(goal) or "click" in goal.lower():
        return None

    windows: list[dict] = []
    if pid is None or window_id is None:
        if app and is_launchable_app_name(app):
            launched = safe_launch_app(client, app)
            payload = as_dict(launched)
            if payload:
                windows = windows_from_response(payload)
                if payload.get("pid"):
                    pid = int(payload["pid"])
        if not windows:
            listed = client.list_windows()
            windows = windows_from_response(listed)
        win = _pick_window(windows, app)
        if not win:
            return None
        pid = int(win.get("pid") or pid or 0)
        window_id = int(win.get("window_id") or win.get("id") or 0)
    if not pid or not window_id:
        return None

    try:
        snap = client.get_window_state(pid, window_id, capture_mode="ax")
    except CuaDriverError:
        return None
    text = _ax_text(snap)
    if not text:
        return None
    if _goal_already_satisfied(goal, text):
        return {
            "result": text[:4000],
            "pid": pid,
            "window_id": window_id,
            "snapshot": snap,
        }
    return None


def _ax_text(snap: dict) -> str:
    for key in ("markdown", "ax_tree", "text", "content"):
        val = snap.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def _goal_already_satisfied(goal: str, text: str) -> bool:
    g = goal.lower()
    if "compute" in g or "calculate" in g or "×" in g or "*" in g:
        return False
    if len(text) < 80:
        return False
    if any(v in g for v in ("read", "list", "what is open", "describe")):
        return True
    return False
