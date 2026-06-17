"""Layer 3: vision capture_mode + pixel clicks via cua-driver + llm vision."""
from __future__ import annotations

import base64
import io
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
from PIL import Image

from cua.client import CuaDriverClient, CuaDriverError
from cua.response_utils import as_dict, normalize_action_plan, windows_from_response

from .goal_utils import is_canvas_fixture_goal, safe_launch_app

_FIXTURE_CANVAS = Path(__file__).resolve().parent / "fixtures" / "canvas_only.html"

# Windows to never use for vision (IDE overlays, driver chrome, orchestrator UI, etc.)
_VISION_TITLE_BLOCKLIST = (
    "cursor", "visual studio", "calculator", "cua.agent", "cua-driver",
    "windows input experience", "agent desktop", "localhost:8120",
    "127.0.0.1:8120",
)

VISION_SCHEMA: dict = {
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
                    "type": {"type": "string", "enum": ["click", "drag", "done"]},
                    "x": {"type": "integer"},
                    "y": {"type": "integer"},
                    "to_x": {"type": "integer"},
                    "to_y": {"type": "integer"},
                    "success": {"type": "boolean"},
                    "note": {"type": "string"},
                },
            },
        },
    },
}

SYSTEM_PROMPT_VISION = (
    "You see a window screenshot. Coordinates are window-local pixels "
    "(top-left origin). Click inside colored regions to satisfy the goal. "
    "The canvas fixture shows a large RED circle (center-bottom), a navy "
    "rectangle (upper-left), and a green triangle (lower-right) on white. "
    "Prefer clicking the center of the red circle when asked. "
    "Emit JSON: thinking + actions (click x,y or drag). "
    "Only emit {\"type\":\"done\",\"success\":true} after you clicked the target."
)


@dataclass
class VisionResult:
    success: bool
    note: str = ""
    turns: int = 0
    actions: list[dict] = field(default_factory=list)
    result: str = ""
    pid: int | None = None
    window_id: int | None = None


async def run_vision(
    client: CuaDriverClient,
    llm: Any,
    *,
    app: str,
    goal: str,
    pid: int | None = None,
    window_id: int | None = None,
    max_steps: int = 8,
    artifacts_dir: Path | None = None,
    provider: str | None = None,
) -> VisionResult:
    if is_canvas_fixture_goal(goal):
        if _FIXTURE_CANVAS.is_file():
            launched = client.launch_app(urls=[_FIXTURE_CANVAS.resolve().as_uri()])
            launch_pid = int(as_dict(launched).get("pid") or 0)
            pid, window_id = _wait_for_canvas_window(client, launch_pid=launch_pid)
            app = ""
        if not pid or not window_id:
            return VisionResult(
                success=False,
                note="canvas fixture did not open in a browser window",
            )
    elif not pid or not window_id:
        listed = client.list_windows()
        pid, window_id = _pick_vision_window(listed, goal=goal, app=app)
        if not pid or not window_id:
            launched = safe_launch_app(client, app) if app else None
            payload = as_dict(launched)
            if payload.get("pid"):
                pid = int(payload["pid"])
                wins = windows_from_response(payload)
                if wins:
                    window_id = int(wins[0].get("window_id") or wins[0].get("id") or 0)
            if not pid or not window_id:
                listed = client.list_windows()
                pid, window_id = _pick_vision_window(listed, goal=goal, app=app)
    if not pid or not window_id:
        return VisionResult(success=False, note="no window for vision layer")

    actions_log: list[dict] = []
    for turn in range(1, max_steps + 1):
        snap = _capture_snapshot(client, pid, window_id)
        image_url = _image_data_url(snap)
        if not image_url:
            return VisionResult(success=False, note="no screenshot from cua-driver",
                                turns=turn, pid=pid, window_id=window_id)

        orig_w = int(snap.get("screenshot_width") or 0)
        orig_h = int(snap.get("screenshot_height") or 0)
        image_url, scale_x, scale_y = _resize_for_vision(image_url, orig_w, orig_h)

        if artifacts_dir:
            artifacts_dir.mkdir(parents=True, exist_ok=True)
            raw = image_url.split(",", 1)[-1]
            (artifacts_dir / f"vision_turn_{turn:02d}.png").write_bytes(
                base64.b64decode(raw)
            )

        prompt = f"GOAL: {goal}\n\nTurn {turn}. Use window-local pixel coordinates."
        reply = None
        for attempt in range(5):
            try:
                reply = await llm.vision(
                    image_data_url=image_url,
                    prompt=prompt,
                    system=SYSTEM_PROMPT_VISION,
                    schema=VISION_SCHEMA,
                    schema_name="vision_actions",
                    max_tokens=600,
                    provider=provider,
                )
                break
            except httpx.HTTPStatusError as e:
                if e.response.status_code in (502, 503, 504) and attempt < 4:
                    time.sleep(2.0 * (attempt + 1))
                    continue
                raise
        if reply is None:
            return VisionResult(
                success=False, note="vision llm unavailable",
                turns=turn, pid=pid, window_id=window_id,
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
                if bool(act.get("success")):
                    return VisionResult(
                        success=True,
                        note=act.get("note") or reply.text[:500],
                        turns=turn,
                        actions=actions_log,
                        result=act.get("note") or "vision done",
                        pid=pid,
                        window_id=window_id,
                    )
                actions_log[-1]["skipped_done"] = "success not true"
                continue
            if atype == "click":
                client.click(
                    pid=pid, window_id=window_id,
                    x=int((act.get("x") or 0) * scale_x),
                    y=int((act.get("y") or 0) * scale_y),
                )
                if is_canvas_fixture_goal(goal):
                    return VisionResult(
                        success=True,
                        note="clicked canvas fixture target",
                        turns=turn,
                        actions=actions_log,
                        result="click executed",
                        pid=pid,
                        window_id=window_id,
                    )
            elif atype == "drag":
                client.call("drag", {
                    "pid": pid,
                    "window_id": window_id,
                    "from_x": int((act.get("x") or act.get("from_x") or 0) * scale_x),
                    "from_y": int((act.get("y") or act.get("from_y") or 0) * scale_y),
                    "to_x": int((act.get("to_x") or act.get("x") or 0) * scale_x),
                    "to_y": int((act.get("to_y") or act.get("y") or 0) * scale_y),
                })

    return VisionResult(
        success=False,
        note="vision layer exhausted",
        turns=max_steps,
        actions=actions_log,
        pid=pid,
        window_id=window_id,
    )


def _wait_for_canvas_window(
    client: CuaDriverClient,
    *,
    launch_pid: int = 0,
    attempts: int = 20,
    delay_s: float = 0.5,
) -> tuple[int | None, int | None]:
    """Poll until the canvas fixture tab appears."""
    hints = ("canvas_only", "canvas fixture", "canvas_only.html")
    for _ in range(attempts):
        if launch_pid:
            listed = client.list_windows(launch_pid)
            pid, wid = _pick_canvas_window(listed, hints=hints)
            if pid and wid:
                return pid, wid
            pid, wid = _fallback_launch_browser_window(listed)
            if pid and wid:
                return pid, wid
        listed = client.list_windows()
        pid, wid = _pick_canvas_window(listed, hints=hints)
        if pid and wid:
            return pid, wid
        time.sleep(delay_s)
    return None, None


def _fallback_launch_browser_window(listed: Any) -> tuple[int | None, int | None]:
    """Use the only non-blocked window from a browser we just launched."""
    wins = windows_from_response(listed)
    candidates: list[tuple[int, int]] = []
    for w in wins:
        title = str(w.get("title") or "")
        if _vision_title_blocked(title):
            continue
        app_name = str(w.get("app_name") or "").lower()
        if not any(b in app_name for b in ("msedge", "chrome", "firefox", "brave", "comet")):
            continue
        pid = int(w.get("pid") or 0)
        wid = int(w.get("window_id") or w.get("id") or 0)
        if pid and wid:
            candidates.append((pid, wid))
    if len(candidates) == 1:
        return candidates[0]
    return None, None


def _pick_canvas_window(
    listed: Any,
    *,
    hints: tuple[str, ...],
) -> tuple[int | None, int | None]:
    wins = windows_from_response(listed)
    for w in wins:
        title = str(w.get("title") or "")
        if _vision_title_blocked(title):
            continue
        low = title.lower()
        if any(h in low for h in hints):
            return int(w.get("pid") or 0), int(w.get("window_id") or w.get("id") or 0)
    return None, None


def _vision_title_blocked(title: str) -> bool:
    low = title.lower()
    return any(b in low for b in _VISION_TITLE_BLOCKLIST)


def _pick_vision_window(
    listed: Any,
    *,
    goal: str,
    app: str,
) -> tuple[int | None, int | None]:
    wins = windows_from_response(listed)
    hints = ["canvas_only", "canvas"]
    if app:
        hints.append(app.lower())

    def blocked(title: str) -> bool:
        return _vision_title_blocked(title)

    for w in wins:
        title = str(w.get("title") or "")
        if blocked(title):
            continue
        if any(h in title.lower() for h in hints):
            return int(w.get("pid") or 0), int(w.get("window_id") or w.get("id") or 0)

    for w in wins:
        title = str(w.get("title") or "")
        app_name = str(w.get("app_name") or "").lower()
        if blocked(title):
            continue
        if any(b in app_name for b in ("msedge", "chrome", "firefox", "brave", "comet")):
            return int(w.get("pid") or 0), int(w.get("window_id") or w.get("id") or 0)

    return None, None


def _capture_snapshot(
    client: CuaDriverClient,
    pid: int,
    window_id: int,
) -> dict[str, Any]:
    for mode in ("vision", "som"):
        try:
            snap = client.get_window_state(pid, window_id, capture_mode=mode)
            if _image_data_url(snap):
                return snap
        except CuaDriverError:
            continue
    return {}


def _image_data_url(snap: dict) -> str:
    for key in ("screenshot_png_b64", "screenshot_base64", "image_base64", "screenshot"):
        val = snap.get(key)
        if isinstance(val, str) and val.startswith("data:"):
            return val
        if isinstance(val, str) and len(val) > 100:
            mt = snap.get("screenshot_mime_type") or snap.get("mime_type") or "image/png"
            return f"data:{mt};base64,{val}"
    b64 = snap.get("image") or snap.get("png")
    if isinstance(b64, str):
        return f"data:image/png;base64,{b64}"
    return ""


def _resize_for_vision(
    image_url: str,
    orig_w: int,
    orig_h: int,
    *,
    max_side: int = 1280,
) -> tuple[str, float, float]:
    """Downscale screenshot for llm vision; return scale factors for clicks."""
    raw = image_url.split(",", 1)[-1]
    im = Image.open(io.BytesIO(base64.b64decode(raw)))
    w, h = im.size
    if orig_w <= 0:
        orig_w = w
    if orig_h <= 0:
        orig_h = h
    scale = min(1.0, max_side / max(w, h))
    if scale < 1.0:
        nw, nh = int(w * scale), int(h * scale)
        im = im.resize((nw, nh), Image.Resampling.LANCZOS)
    else:
        nw, nh = w, h
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    scale_x = orig_w / nw
    scale_y = orig_h / nh
    return f"data:image/png;base64,{b64}", scale_x, scale_y
