"""Layer 2b electron: cua page tool + CDP (text LLM loop)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from cua.client import CuaDriverClient, CuaDriverError
from cua.response_utils import normalize_action_plan, page_text_from_response, windows_from_response

ACTION_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["thinking", "actions"],
    "properties": {
        "thinking": {"type": "string"},
        "actions": {
            "type": "array",
            "minItems": 1,
            "maxItems": 2,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["type"],
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": ["hotkey", "type_text", "page_js", "page_text", "done"],
                    },
                    "keys": {"type": "array", "items": {"type": "string"}},
                    "text": {"type": "string"},
                    "javascript": {"type": "string"},
                    "success": {"type": "boolean"},
                    "note": {"type": "string"},
                },
            },
        },
    },
}

SYSTEM_PROMPT = (
    "You drive an Electron app via cua-driver page tools (get_text, execute_javascript). "
    "On Windows the app must already be running with --remote-debugging-port "
    "(see computer/scripts/launch_cursor_debug.ps1). Each turn you see page text "
    "and goal progress. Emit JSON with thinking and 1-2 actions: "
    "hotkey(keys), type_text(text), page_js(javascript), page_text (refresh), "
    "done(success, note)."
)


@dataclass
class ElectronResult:
    success: bool
    note: str = ""
    turns: int = 0
    actions: list[dict] = field(default_factory=list)
    result: str = ""
    pid: int | None = None
    window_id: int | None = None


async def run_electron(
    client: CuaDriverClient,
    llm: Any,
    *,
    app: str,
    goal: str,
    electron_port: int,
    max_steps: int = 8,
    provider: str | None = None,
) -> ElectronResult:
    pid, window_id = _resolve_electron_window(
        client, app=app, electron_port=electron_port,
    )
    if not pid or not window_id:
        return ElectronResult(
            success=False,
            note=(
                f"no {app} window for electron layer — "
                f"run computer/scripts/launch_cursor_debug.ps1 (port {electron_port})"
            ),
        )

    actions_log: list[dict] = []
    page_text = _page_text(client, pid, window_id)

    for turn in range(1, max_steps + 1):
        prompt = (
            f"GOAL: {goal}\n\nPAGE TEXT (truncated):\n{page_text[:6000]}\n\n"
            f"Turn {turn}. Reply with JSON actions."
        )
        reply = await llm.chat(
            prompt=prompt,
            system=SYSTEM_PROMPT,
            schema=ACTION_SCHEMA,
            schema_name="electron_actions",
            max_tokens=800,
            provider=provider,
        )
        plan = normalize_action_plan(reply.parsed)
        thinking = plan["thinking"]
        step_actions = plan["actions"]
        turn_log = {"turn": turn, "thinking": thinking, "actions": step_actions}
        actions_log.append(turn_log)

        for act in step_actions:
            if not isinstance(act, dict):
                continue
            atype = act.get("type")
            if atype == "done":
                ok = bool(act.get("success"))
                note = act.get("note") or thinking
                return ElectronResult(
                    success=ok,
                    note=note,
                    turns=turn,
                    actions=actions_log,
                    result=note if ok else page_text[:2000],
                    pid=pid,
                    window_id=window_id,
                )
            try:
                if atype == "hotkey":
                    client.hotkey(
                        keys=act.get("keys") or [],
                        pid=pid,
                        window_id=window_id,
                    )
                elif atype == "type_text":
                    client.type_text(
                        pid=pid,
                        text=act.get("text") or "",
                        window_id=window_id,
                    )
                elif atype == "page_js":
                    client.page(
                        pid=pid,
                        window_id=window_id,
                        action="execute_javascript",
                        javascript=act.get("javascript") or "",
                    )
                elif atype == "page_text":
                    page_text = _page_text(client, pid, window_id)
            except CuaDriverError as e:
                page_text = f"(cua-driver error: {e})"
        page_text = _page_text(client, pid, window_id)
        if _goal_met(goal, page_text):
            return ElectronResult(
                success=True,
                note="goal satisfied per page text",
                turns=turn,
                actions=actions_log,
                result=page_text[:2000],
                pid=pid,
                window_id=window_id,
            )

    return ElectronResult(
        success=False,
        note="electron layer exhausted steps",
        turns=max_steps,
        actions=actions_log,
        result=page_text[:2000],
        pid=pid,
        window_id=window_id,
    )


def _resolve_electron_window(
    client: CuaDriverClient,
    *,
    app: str,
    electron_port: int,
) -> tuple[int, int]:
    # cua-driver docs: electron_debugging_port on launch_app is a no-op on Windows.
    # Attach to an already-running Electron window (launch via launch_cursor_debug.ps1).
    del electron_port
    listed = client.list_windows()
    wins = windows_from_response(listed)
    hint = app.lower()
    for w in wins:
        title = str(w.get("title") or "").lower()
        name = str(w.get("name") or "").lower()
        app_name = str(w.get("app_name") or "").lower()
        if "overlay" in title:
            continue
        if (
            hint in title
            or hint in name
            or (hint == "cursor" and ("cursor" in title or "cursor.exe" in app_name))
        ):
            pid = int(w.get("pid") or 0)
            window_id = int(w.get("window_id") or w.get("id") or 0)
            if pid and window_id:
                return pid, window_id
    return 0, 0


def _page_text(client: CuaDriverClient, pid: int, window_id: int) -> str:
    try:
        out = client.page(pid=pid, window_id=window_id, action="get_text")
        text = page_text_from_response(out)
        if text:
            return text
    except CuaDriverError as e:
        return f"(page get_text error: {e})"
    return ""


def _goal_met(goal: str, text: str) -> bool:
    g = goal.lower()
    if "computer_use_evidence" in g and "computer-use layer2b ok" in text.lower():
        return True
    if "proof" in g and len(text) > 20:
        return "ok" in text.lower() or "evidence" in text.lower()
    return False
