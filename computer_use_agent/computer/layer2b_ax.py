"""Layer 2b AX: element_index loop via cua-driver + text LLM."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from cua.client import CuaDriverClient
from cua.response_utils import as_dict, normalize_action_plan, windows_from_response

from .goal_utils import is_canvas_fixture_goal, safe_launch_app
from .layer2b_electron import ACTION_SCHEMA, SYSTEM_PROMPT


@dataclass
class AxResult:
    success: bool
    note: str = ""
    turns: int = 0
    actions: list[dict] = field(default_factory=list)
    result: str = ""
    pid: int | None = None
    window_id: int | None = None


async def run_ax(
    client: CuaDriverClient,
    llm: Any,
    *,
    app: str,
    goal: str,
    pid: int | None = None,
    window_id: int | None = None,
    max_steps: int = 10,
    provider: str | None = None,
) -> AxResult:
    if is_canvas_fixture_goal(goal):
        return AxResult(success=False, note="canvas fixture uses vision layer")

    if not pid or not window_id:
        launched = safe_launch_app(client, app)
        payload = as_dict(launched)
        if payload:
            pid = int(payload.get("pid") or 0)
            wins = windows_from_response(payload)
            if wins:
                window_id = int(wins[0].get("window_id") or wins[0].get("id") or 0)
    if not pid or not window_id:
        return AxResult(success=False, note="no target window for AX layer")

    actions_log: list[dict] = []
    for turn in range(1, max_steps + 1):
        snap = client.get_window_state(pid, window_id, capture_mode="ax")
        legend = _legend(snap)
        prompt = f"GOAL: {goal}\n\nAX LEGEND:\n{legend[:8000]}\n\nTurn {turn}."
        reply = await llm.chat(
            prompt=prompt,
            system=SYSTEM_PROMPT.replace("page/CDP", "AX element_index"),
            schema=ACTION_SCHEMA,
            schema_name="ax_actions",
            max_tokens=800,
            provider=provider,
        )
        plan = normalize_action_plan(reply.parsed)
        step_actions = plan["actions"]
        actions_log.append({
            "turn": turn,
            "thinking": plan["thinking"],
            "actions": step_actions,
        })
        for act in step_actions:
            if not isinstance(act, dict):
                continue
            atype = act.get("type")
            if atype == "done":
                ok = bool(act.get("success"))
                return AxResult(
                    success=ok,
                    note=act.get("note") or "",
                    turns=turn,
                    actions=actions_log,
                    result=legend[:2000],
                    pid=pid,
                    window_id=window_id,
                )
            if atype == "hotkey":
                client.hotkey(keys=act.get("keys") or [])
            elif atype == "type_text":
                idx = act.get("element_index")
                if idx is not None:
                    client.click(pid=pid, window_id=window_id, element_index=int(idx))
                client.type_text(pid=pid, text=act.get("text") or "",
                                 element_index=act.get("element_index"),
                                 window_id=window_id)
        snap2 = client.get_window_state(pid, window_id, capture_mode="ax")
        if _goal_in_text(goal, _legend(snap2)):
            return AxResult(
                success=True,
                note="goal satisfied after AX actions",
                turns=turn,
                actions=actions_log,
                result=_legend(snap2)[:2000],
                pid=pid,
                window_id=window_id,
            )

    return AxResult(
        success=False,
        note="AX layer exhausted",
        turns=max_steps,
        actions=actions_log,
        pid=pid,
        window_id=window_id,
    )


def _legend(snap: dict) -> str:
    for key in ("markdown", "ax_tree", "text", "content"):
        val = snap.get(key)
        if isinstance(val, str):
            return val
    return str(snap)[:4000]


def _goal_in_text(goal: str, text: str) -> bool:
    return len(text) > 50 and "error" not in text.lower()[:100]
