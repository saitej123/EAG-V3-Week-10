"""Layer 2a: deterministic hotkey scripts via cua-driver (no LLM)."""
from __future__ import annotations

import re
import time
from typing import Any

from cua.client import CuaDriverClient, CuaDriverError
from cua.response_utils import as_dict, windows_from_response


# Default Calculator script for validation task 1 (847 * 293).
DEFAULT_CALC_SCRIPT: list[dict[str, Any]] = [
    {"tool": "launch_app", "args": {"name": "Calculator"}},
    {"tool": "type_text", "args": {"text": "847*293="}},
]


async def run_hotkey_script(
    client: CuaDriverClient,
    script: list[dict[str, Any]],
    *,
    app: str,
) -> dict[str, Any]:
    """Execute a list of {tool, args} steps. Returns {success, result, actions, pid}."""
    actions: list[dict] = []
    pid: int | None = None
    window_id: int | None = None
    current_app = app

    try:
        client.ensure_daemon()
    except CuaDriverError as e:
        return {
            "success": False,
            "result": str(e),
            "actions": actions,
            "pid": pid,
            "window_id": window_id,
        }

    try:
        for step in script:
            if not isinstance(step, dict):
                return {
                    "success": False,
                    "result": f"invalid hotkey step: expected object, got {type(step).__name__}",
                    "actions": actions,
                    "pid": pid,
                    "window_id": window_id,
                }
            tool = step.get("tool") or ""
            args = dict(step.get("args") or {})
            if not tool:
                return {
                    "success": False,
                    "result": "invalid hotkey step: missing tool",
                    "actions": actions,
                    "pid": pid,
                    "window_id": window_id,
                }
            if tool == "launch_app":
                if app and "name" not in args and "path" not in args:
                    args.setdefault("name", app)
                launch_app_hint = str(
                    args.get("name")
                    or args.get("launch_path")
                    or args.get("path")
                    or current_app
                    or app
                )
                if "launch_path" not in args and "path" not in args and args.get("name"):
                    out = client.launch_app_named(str(args.pop("name")), **args)
                else:
                    out = client.launch_app(**args)
                payload = as_dict(out)
                if payload:
                    pid = int(payload.get("pid") or pid or 0) or pid
                    wins = windows_from_response(payload)
                    if wins:
                        window_id = int(wins[0].get("window_id") or wins[0].get("id") or 0)
                    if pid:
                        pid, window_id = _resolve_target_window(client, launch_app_hint, pid, window_id)
                    if launch_app_hint:
                        current_app = launch_app_hint
            elif tool == "hotkey":
                pid, window_id = _ensure_target_window(client, current_app, pid, window_id)
                if not pid:
                    return {
                        "success": False,
                        "result": "hotkey requires a target window — launch_app did not resolve a window",
                        "actions": actions,
                        "pid": pid,
                        "window_id": window_id,
                    }
                if pid:
                    args.setdefault("pid", pid)
                if window_id:
                    args.setdefault("window_id", window_id)
                out = client.hotkey(**args)
            elif tool == "type_text":
                pid = int(args.get("pid") or pid or 0) or None
                window_id = int(args.get("window_id") or window_id or 0) or None
                pid, window_id = _ensure_target_window(client, current_app, pid, window_id)
                if not pid or not window_id:
                    return {
                        "success": False,
                        "result": "type_text requires a target window — launch_app did not resolve a window",
                        "actions": actions,
                        "pid": pid,
                        "window_id": window_id,
                    }
                args["pid"] = pid
                args["window_id"] = window_id
                if "calc" in current_app.lower():
                    out = _type_calculator_expr(
                        client,
                        int(pid),
                        int(window_id),
                        str(args.get("text") or ""),
                    )
                else:
                    out = client.type_text(
                        pid=int(pid),
                        text=str(args.get("text") or ""),
                        **{k: v for k, v in args.items() if k not in ("pid", "text")},
                    )
            elif tool == "press_key":
                pid = int(args.get("pid") or pid or 0) or None
                window_id = int(args.get("window_id") or window_id or 0) or None
                pid, window_id = _ensure_target_window(client, current_app, pid, window_id)
                if not pid:
                    return {
                        "success": False,
                        "result": "press_key requires a target window — launch_app did not resolve a window",
                        "actions": actions,
                        "pid": pid,
                        "window_id": window_id,
                    }
                args["pid"] = pid
                if window_id:
                    args["window_id"] = window_id
                out = client.press_key(**args)
            elif tool == "click":
                pid = int(args.get("pid") or pid or 0) or None
                window_id = int(args.get("window_id") or window_id or 0) or None
                pid, window_id = _ensure_target_window(client, current_app, pid, window_id)
                if not pid or not window_id:
                    return {
                        "success": False,
                        "result": "click requires a target window — launch_app did not resolve a window",
                        "actions": actions,
                        "pid": pid,
                        "window_id": window_id,
                    }
                args["pid"] = pid
                args["window_id"] = window_id
                out = client.click(**args)
            else:
                out = client.call(tool, args)
            actions.append({"tool": tool, "args": args, "result": out})

        if pid and window_id and "calc" in current_app.lower():
            pid, window_id = _resolve_target_window(client, current_app, int(pid), int(window_id))
            snap = client.get_window_state(int(pid), int(window_id), capture_mode="ax")
            actions.append(
                {
                    "tool": "get_window_state",
                    "args": {"pid": pid, "window_id": window_id},
                    "result": snap,
                }
            )
            inferred = _infer_result(actions, app)
            if inferred and inferred != "hotkey script completed":
                return {
                    "success": True,
                    "result": inferred,
                    "actions": actions,
                    "pid": pid,
                    "window_id": window_id,
                }

        result = _infer_result(actions, current_app)
        return {
            "success": bool(result) and result != "hotkey script completed",
            "result": result,
            "actions": actions,
            "pid": pid,
            "window_id": window_id,
        }
    except CuaDriverError as e:
        return {
            "success": False,
            "result": str(e),
            "actions": actions,
            "pid": pid,
            "window_id": window_id,
        }


def _resolve_target_window(
    client: CuaDriverClient,
    app: str,
    pid: int,
    window_id: int | None,
    *,
    attempts: int = 12,
    delay_s: float = 0.35,
) -> tuple[int | None, int | None]:
    """Resolve a stable (pid, window_id) for UWP hosts like Calculator."""
    hint = app.lower()
    for _ in range(attempts):
        listed = client.list_windows()
        for w in windows_from_response(listed):
            title = str(w.get("title") or "").lower()
            if hint and hint in title:
                resolved_pid = int(w.get("pid") or 0)
                resolved_wid = int(w.get("window_id") or w.get("id") or 0)
                if resolved_pid and resolved_wid:
                    return resolved_pid, resolved_wid
        listed = client.list_windows(pid)
        wins = windows_from_response(listed)
        if wins:
            w = wins[0]
            resolved_pid = int(w.get("pid") or 0)
            resolved_wid = int(w.get("window_id") or w.get("id") or 0)
            if resolved_pid and resolved_wid:
                return resolved_pid, resolved_wid
        time.sleep(delay_s)
    return pid, window_id


def _ensure_target_window(
    client: CuaDriverClient,
    app: str,
    pid: int | None,
    window_id: int | None,
) -> tuple[int | None, int | None]:
    """Return a usable target window; never let interactive tools run with pid=0."""
    if pid and window_id:
        return _resolve_target_window(client, app, int(pid), int(window_id))
    if pid:
        resolved_pid, resolved_window_id = _resolve_target_window(
            client,
            app,
            int(pid),
            window_id,
            attempts=6,
            delay_s=0.25,
        )
        if resolved_pid and resolved_window_id:
            return resolved_pid, resolved_window_id

    listed = client.list_windows()
    matched = _pick_app_window(listed, app)
    if matched[0] and matched[1]:
        return matched

    if app:
        try:
            launched = client.launch_app_named(app)
        except (CuaDriverError, AttributeError):
            launched = client.launch_app(name=app)
        payload = as_dict(launched)
        launch_pid = int(payload.get("pid") or 0) or None
        wins = windows_from_response(payload)
        if wins:
            win = wins[0]
            launch_pid = int(win.get("pid") or launch_pid or 0) or launch_pid
            launch_window_id = int(win.get("window_id") or win.get("id") or 0) or None
            if launch_pid and launch_window_id:
                return _resolve_target_window(client, app, launch_pid, launch_window_id)
        if launch_pid:
            return _resolve_target_window(client, app, launch_pid, None)

    return None, None


def _pick_app_window(listed: Any, app: str) -> tuple[int | None, int | None]:
    hints = [part for part in re.split(r"[^a-z0-9]+", app.lower()) if part]
    candidates = []
    for w in windows_from_response(listed):
        title = str(w.get("title") or "").lower()
        app_name = str(w.get("app_name") or w.get("process_name") or "").lower()
        haystack = f"{title} {app_name}"
        if hints and not any(h in haystack for h in hints):
            continue
        resolved_pid = int(w.get("pid") or 0)
        resolved_wid = int(w.get("window_id") or w.get("id") or 0)
        if resolved_pid and resolved_wid:
            candidates.append((resolved_pid, resolved_wid))
    return candidates[0] if candidates else (None, None)


def _wait_for_window(
    client: CuaDriverClient,
    pid: int,
    window_id: int | None,
    *,
    attempts: int = 10,
    delay_s: float = 0.4,
) -> tuple[int | None, int | None]:
    for _ in range(attempts):
        listed = client.list_windows(pid)
        wins = windows_from_response(listed)
        if not wins:
            listed = client.list_windows()
            wins = [
                w for w in windows_from_response(listed)
                if int(w.get("pid") or 0) == pid
            ]
        for w in wins:
            if int(w.get("pid") or 0) == pid:
                wid = int(w.get("window_id") or w.get("id") or 0)
                if wid:
                    return pid, wid
        time.sleep(delay_s)
    return pid, window_id


def _type_calculator_expr(
    client: CuaDriverClient,
    pid: int,
    window_id: int,
    expr: str,
) -> dict:
    """Drive Win11 Calculator via button clicks from AX element indices."""
    snap = client.get_window_state(pid, window_id, capture_mode="ax")
    actions: list[dict] = []
    for ch in expr:
        if ch in (" ", "\n"):
            continue
        idx = _calc_button_index(snap, ch)
        if idx is None:
            continue
        client.click(pid=pid, window_id=window_id, element_index=idx)
        actions.append({"char": ch, "element_index": idx})
        time.sleep(0.06)
    return {"actions": actions, "snapshot": snap}


def _calc_button_index(snap: dict, ch: str) -> int | None:
    key = ch.lower()
    labels = {
        "0": ("zero", "num0button"),
        "1": ("one", "num1button"),
        "2": ("two", "num2button"),
        "3": ("three", "num3button"),
        "4": ("four", "num4button"),
        "5": ("five", "num5button"),
        "6": ("six", "num6button"),
        "7": ("seven", "num7button"),
        "8": ("eight", "num8button"),
        "9": ("nine", "num9button"),
        "*": ("multiply", "multiplybutton"),
        "x": ("multiply", "multiplybutton"),
        "×": ("multiply", "multiplybutton"),
        "/": ("divide", "dividebutton"),
        "+": ("plus", "plusbutton"),
        "-": ("minus", "minusbutton"),
        "=": ("equals", "equalbutton"),
    }
    patterns = labels.get(key, (key,))
    text = str(
        snap.get("tree_markdown")
        or snap.get("markdown")
        or snap.get("ax_tree")
        or ""
    ).lower()
    for line in text.splitlines():
        low = line.lower()
        if not any(p in low for p in patterns):
            continue
        m = re.search(r"\[(\d+)\]", line)
        if m:
            return int(m.group(1))
    elements = snap.get("elements") or snap.get("ax_elements") or []
    if isinstance(elements, list):
        for el in elements:
            if not isinstance(el, dict):
                continue
            name = str(el.get("name") or el.get("label") or "").lower()
            aid = str(el.get("automation_id") or el.get("id") or "").lower()
            if any(p in name or p in aid for p in patterns):
                idx = el.get("element_index") or el.get("index")
                if idx is not None:
                    return int(idx)
    return None


def script_for_metadata(metadata: dict, app: str) -> list[dict[str, Any]]:
    custom = metadata.get("hotkey_script")
    if isinstance(custom, list) and custom:
        normalized = []
        for step in custom:
            if not isinstance(step, dict) or not step.get("tool"):
                normalized = []
                break
            args = step.get("args") or {}
            normalized.append({"tool": str(step.get("tool")), "args": args if isinstance(args, dict) else {}})
        if normalized:
            return normalized
    if "calculator" in app.lower() or "calc" in app.lower():
        return DEFAULT_CALC_SCRIPT
    return []


def _infer_result(actions: list[dict], app: str) -> str:
    for act in reversed(actions):
        res = act.get("result")
        if not isinstance(res, dict):
            continue
        for key in ("display", "text", "result", "value"):
            if res.get(key):
                return str(res[key])
        snap = res.get("snapshot") or res
        if isinstance(snap, dict):
            for key in ("tree_markdown", "markdown", "ax_tree", "text"):
                if isinstance(snap.get(key), str) and snap[key].strip():
                    body = snap[key]
                    if "calc" in app.lower():
                        m = re.search(r"display is\s+([\d,]+)", body, re.I)
                        if m:
                            return m.group(1).replace(",", "")
                        m = re.search(r"[\d,]+\.?\d*", body.replace(",", ""))
                        if m:
                            return m.group(0)
    return "hotkey script completed"
