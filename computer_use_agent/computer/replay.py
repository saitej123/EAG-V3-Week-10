"""Computer-use trajectory evidence — replay report from persisted DAG sessions."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote

from ..catalog import get_dag_query
from ..persistence import SessionStore

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SAFE_REL = re.compile(r"^[A-Za-z0-9._/-]+$")
_COMPUTER_QUERY_RE = re.compile(r"^dag_(CU-[A-Z]+)_")
_NOISE_TEXT_RE = re.compile(r"[\ufffc\ufeff\u200b-\u200f\u2028\u2029]")
_WHITESPACE_RE = re.compile(r"\s+")


def sanitize_evidence_text(text: Any, *, max_len: int = 180) -> str:
    """Strip UI dump noise (object replacement chars, private-use glyphs) for display."""
    raw = str(text or "")
    raw = _NOISE_TEXT_RE.sub(" ", raw)
    raw = _WHITESPACE_RE.sub(" ", raw).strip()
    if len(raw) > max_len:
        return raw[: max_len - 1].rstrip() + "…"
    return raw


def _flatten_output_actions(actions: Any) -> list[Any]:
    """Normalize ComputerOutput.actions — may be flat or nested {turn, actions: []}."""
    if not isinstance(actions, list):
        return []
    flat: list[Any] = []
    for item in actions:
        if isinstance(item, dict) and isinstance(item.get("actions"), list):
            nested = item.get("actions") or []
            if nested:
                flat.extend(nested)
            else:
                flat.append(item)
        else:
            flat.append(item)
    return flat


def _load_trajectory_turns(trajectory_dir: str) -> list[dict[str, Any]]:
    """Parse turn-*/action.json files from a recorded trajectory directory."""
    root = _safe_trajectory_dir(trajectory_dir)
    if not root:
        return []
    turns: list[dict[str, Any]] = []
    for action_path in sorted(root.glob("turn-*/action.json")):
        try:
            data = json.loads(action_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(data, dict):
            continue
        turn_name = action_path.parent.name
        t_ms = data.get("t_ms_from_session_start")
        if t_ms is None:
            t_ms = data.get("t_start_ms_from_session_start")
        args = data.get("arguments") or {}
        summary = sanitize_evidence_text(
            data.get("result_summary") or data.get("result") or "",
            max_len=220,
        )
        if not summary and isinstance(args, dict):
            tool = str(data.get("tool") or "")
            if tool == "launch_app" and args.get("launch_path"):
                summary = f"Launch {args.get('launch_path')}"
            elif tool == "page" and args.get("action"):
                summary = f"page.{args.get('action')}"
            elif args:
                bits = [f"{k}={args[k]!r}" for k in list(args.keys())[:3]]
                summary = " ".join(bits)
        turns.append(
            {
                "turn": turn_name,
                "tool": data.get("tool"),
                "t_ms": t_ms,
                "summary": summary or "(no summary)",
                "arguments": args if isinstance(args, dict) else {},
            }
        )
    return turns


def _elapsed_ms_from_turns(turns: list[dict[str, Any]], trajectory_dir: str) -> int | None:
    ms_values = [int(t["t_ms"]) for t in turns if isinstance(t.get("t_ms"), (int, float))]
    if ms_values:
        return max(ms_values)
    root = _safe_trajectory_dir(trajectory_dir)
    if not root:
        return None
    session_path = root / "session.json"
    if session_path.is_file():
        try:
            data = json.loads(session_path.read_text(encoding="utf-8"))
            started = data.get("started_at_monotonic_ms")
            if isinstance(started, (int, float)):
                return int(started)
        except (json.JSONDecodeError, OSError):
            pass
    return None


def _parse_json(raw: str | dict | None) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _sessions_root() -> Path:
    return _PROJECT_ROOT / "state" / "sessions"


def _state_roots() -> list[Path]:
    roots = [(_PROJECT_ROOT / "state").resolve()]
    cwd_state = (Path.cwd() / "state").resolve()
    if cwd_state not in roots:
        roots.append(cwd_state)
    return [r for r in roots if r.is_dir()] or roots[:1]


def _safe_trajectory_dir(trajectory_dir: str) -> Path | None:
    raw = (trajectory_dir or "").strip()
    if not raw:
        return None
    try:
        resolved = Path(raw).resolve()
    except OSError:
        return None
    if not any(str(resolved).startswith(str(root)) for root in _state_roots()):
        return None
    return resolved if resolved.is_dir() else None


def resolve_trajectory_artifact(trajectory_dir: str, rel_path: str) -> Path | None:
    """Resolve a file inside a recorded trajectory directory for HTTP serving."""
    root = _safe_trajectory_dir(trajectory_dir)
    rel = (rel_path or "").strip().replace("\\", "/").lstrip("/")
    if not root or not rel or ".." in rel.split("/"):
        return None
    if not _SAFE_REL.match(rel):
        return None
    full = (root / rel).resolve()
    if not str(full).startswith(str(root)):
        return None
    return full if full.is_file() else None


def computer_replay_payload(output: dict[str, Any] | None) -> dict[str, Any]:
    """Compact evidence block for UI / formatter."""
    if not isinstance(output, dict):
        return {"available": False}
    actions = _flatten_output_actions(output.get("actions") or [])
    trajectory_dir = str(output.get("trajectory_dir") or "")
    timeline = _load_trajectory_turns(trajectory_dir)
    elapsed_ms = _elapsed_ms_from_turns(timeline, trajectory_dir)
    action_count = len(timeline) if timeline else len(actions)
    result_raw = output.get("result")
    result_preview = sanitize_evidence_text(result_raw, max_len=160)
    return {
        "available": True,
        "app": output.get("app"),
        "goal": output.get("goal"),
        "path": output.get("path"),
        "turns": output.get("turns", 0),
        "result": result_raw,
        "result_preview": result_preview,
        "actions": actions,
        "timeline": timeline,
        "trajectory_dir": trajectory_dir,
        "recording_ok": bool(_safe_trajectory_dir(trajectory_dir)),
        "action_count": action_count,
        "elapsed_ms": elapsed_ms,
        "elapsed_s": round(elapsed_ms / 1000.0, 2) if elapsed_ms is not None else None,
    }


def format_computer_path(path: str | None) -> str:
    key = str(path or "unknown").strip().lower()
    labels = {
        "read": "read — AX snapshot only, no LLM",
        "hotkey": "hotkey — Layer 2a deterministic scripts, zero vision",
        "electron": "electron — Layer 2b page/CDP against Electron app",
        "ax": "ax — Layer 2b element_index + text LLM",
        "vision": "vision — Layer 3 screenshot + pixel clicks",
    }
    return labels.get(key, key)


def _format_action_line(action: Any, index: int) -> str:
    if isinstance(action, str):
        return f"{index}. {action}"
    if not isinstance(action, dict):
        return f"{index}. {action!r}"
    tool = action.get("tool") or action.get("action") or action.get("type")
    args = action.get("args") or {}
    if tool:
        arg_bits = []
        if isinstance(args, dict):
            for key in ("name", "text", "key", "element_index", "pid"):
                if args.get(key) is not None:
                    arg_bits.append(f"{key}={args[key]!r}")
        suffix = (" " + " ".join(arg_bits)) if arg_bits else ""
        return f"{index}. {tool}{suffix}"
    char = action.get("char")
    if char is not None:
        idx = action.get("element_index")
        return f"{index}. click {char!r} (element_index={idx})"
    try:
        body = json.dumps(action, ensure_ascii=False)
    except (TypeError, ValueError):
        body = str(action)
    return f"{index}. {body}"


def _planner_dag_summary(store: SessionStore) -> dict[str, Any]:
    graph = store.load_graph()
    nodes: list[dict[str, Any]] = []
    for nid, data in graph.nodes(data=True):
        nodes.append(
            {
                "id": nid,
                "skill": data.get("skill"),
                "label": (data.get("metadata") or {}).get("label") or data.get("label") or nid,
                "inputs": list(data.get("inputs") or []),
            }
        )
    edges = [{"source": u, "target": v} for u, v in graph.edges()]
    ordered_skills = [n["skill"] for n in sorted(nodes, key=lambda x: str(x["id"])) if n.get("skill")]
    flow = " → ".join(ordered_skills)
    return {"nodes": nodes, "edges": edges, "flow": flow}


def _list_trajectory_files(trajectory_dir: str) -> list[dict[str, str]]:
    root = _safe_trajectory_dir(trajectory_dir)
    if not root:
        return []
    files: list[dict[str, str]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if rel.startswith("."):
            continue
        kind = "file"
        lower = rel.lower()
        if lower.endswith((".png", ".jpg", ".jpeg", ".webp")):
            kind = "image"
        elif lower.endswith(".json"):
            kind = "json"
        files.append({"path": rel, "kind": kind, "size": str(path.stat().st_size)})
    return files


def _artifact_url(trajectory_dir: str, rel_path: str) -> str:
    return (
        "/api/dag/computer-artifact?"
        f"trajectory_dir={quote(trajectory_dir)}&path={quote(rel_path)}"
    )


def _pick_primary_computer_run(runs: list[dict[str, Any]]) -> dict[str, Any]:
    """Prefer the richest successful computer run (recovery may leave partial earlier runs)."""
    if not runs:
        return {}

    def _score(run: dict[str, Any]) -> tuple[int, int, int, int]:
        status = str(run.get("status") or "")
        complete = 1 if status == "complete" else 0
        recording = 1 if run.get("recording_ok") else 0
        actions = int(run.get("action_count") or 0)
        timeline_len = len(run.get("timeline") or [])
        return (complete, recording, actions, timeline_len)

    return max(runs, key=_score)


def _build_replay_frames(run: dict[str, Any]) -> list[dict[str, Any]]:
    """Ordered replay frames from trajectory turns (screenshot per turn, optional click)."""
    trajectory_dir = str(run.get("trajectory_dir") or "")
    root = _safe_trajectory_dir(trajectory_dir)
    if not root:
        return []

    timeline = run.get("timeline") or []
    frames: list[dict[str, Any]] = []

    def _append_frame(rel_path: str, *, section: str, caption: str, step: dict[str, Any] | None = None) -> None:
        frames.append(
            {
                "url": _artifact_url(trajectory_dir, rel_path),
                "path": rel_path,
                "caption": caption or rel_path,
                "section": section,
                "t_ms": step.get("t_ms") if isinstance(step, dict) else None,
                "turn": step.get("turn") if isinstance(step, dict) else None,
                "tool": step.get("tool") if isinstance(step, dict) else None,
            }
        )

    for step in timeline:
        if not isinstance(step, dict):
            continue
        turn = str(step.get("turn") or "").strip()
        if not turn:
            continue
        tool = str(step.get("tool") or "action")
        summary = str(step.get("summary") or "").strip()
        t_ms = step.get("t_ms")
        section = f"{turn} · {tool}"
        if isinstance(t_ms, (int, float)):
            caption = f"@{int(t_ms)}ms — {summary}" if summary else f"@{int(t_ms)}ms"
        else:
            caption = summary or f"{turn}/screenshot.png"

        screenshot_rel = f"{turn}/screenshot.png"
        if (root / screenshot_rel).is_file():
            _append_frame(screenshot_rel, section=section, caption=caption, step=step)

        click_rel = f"{turn}/click.png"
        if (root / click_rel).is_file():
            click_caption = f"{caption} (click target)" if caption else click_rel
            _append_frame(click_rel, section=section, caption=click_caption, step=step)

    if frames:
        return frames

    for file_info in _list_trajectory_files(trajectory_dir):
        if file_info.get("kind") != "image":
            continue
        rel = str(file_info.get("path") or "")
        if not rel:
            continue
        frames.append(
            {
                "url": _artifact_url(trajectory_dir, rel),
                "path": rel,
                "caption": rel,
                "section": "Trajectory",
                "t_ms": None,
                "turn": None,
                "tool": None,
            }
        )
    return frames


def _manifest_summary(trajectory_dir: str) -> str:
    root = _safe_trajectory_dir(trajectory_dir)
    if not root:
        return "(trajectory directory missing or outside state/)"
    manifest = root / "manifest.json"
    if manifest.is_file():
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
            lines = [
                f"app={data.get('app', '?')}",
                f"goal={data.get('goal', '?')}",
                f"started_at={data.get('started_at', '?')}",
            ]
            return "\n".join(lines)
        except (json.JSONDecodeError, OSError):
            pass
    return "(manifest.json not found — start_recording may have failed)"


def _recording_checklist(run: dict[str, Any]) -> str:
    traj = str(run.get("trajectory_dir") or "")
    root = _safe_trajectory_dir(traj)
    lines = [
        f"start_recording output_dir: {traj or '(empty)'}",
        f"directory exists: {'yes' if root else 'no'}",
    ]
    if root:
        manifest = root / "manifest.json"
        lines.append(f"manifest.json: {'yes' if manifest.is_file() else 'missing'}")
        files = _list_trajectory_files(traj)
        lines.append(f"files captured: {len(files)}")
    return "\n".join(lines)


def _query_id_from_session(session_id: str) -> str | None:
    match = _COMPUTER_QUERY_RE.match(session_id or "")
    return match.group(1) if match else None


def _expected_for_query(query_id: str | None) -> dict[str, Any]:
    if not query_id:
        return {}
    row = get_dag_query(query_id)
    if not row:
        return {}
    return {
        "expected_path": row.get("expected_path"),
        "expected_vision_calls": row.get("expected_vision_calls"),
        "verify_hint": row.get("verify_hint"),
    }


def format_computer_replay_sections(report: dict[str, Any]) -> list[dict[str, Any]]:
    """Numbered evidence sections for the computer trajectory viewer."""
    run = _pick_primary_computer_run(report.get("computer_runs") or [])
    dag = report.get("planner_dag") or {}
    timeline = run.get("timeline") or []
    actions = run.get("actions") or []
    if timeline:
        action_lines = []
        for i, step in enumerate(timeline):
            t_ms = step.get("t_ms")
            timer = f" @ {int(t_ms)}ms" if isinstance(t_ms, (int, float)) else ""
            tool = step.get("tool") or "action"
            summary = step.get("summary") or ""
            action_lines.append(f"{i + 1}. {tool}{timer} — {summary}")
    else:
        action_lines = [_format_action_line(a, i + 1) for i, a in enumerate(actions)]
    trajectory_dir = str(run.get("trajectory_dir") or "")
    files = _list_trajectory_files(trajectory_dir) if trajectory_dir else []
    replay_frames = report.get("frames") or _build_replay_frames(run)
    images = [
        {
            "path": frame.get("path") or "",
            "caption": frame.get("caption") or frame.get("path") or "",
            "url": frame.get("url") or "",
        }
        for frame in replay_frames
        if frame.get("url")
    ]

    dag_lines = [f"{n.get('id')} ({n.get('skill')})" for n in dag.get("nodes") or []]
    dag_body = (dag.get("flow") or " → ".join(dag_lines)) + (
        "\n" + "\n".join(f"  {e.get('source')} → {e.get('target')}" for e in dag.get("edges") or [])
        if dag.get("edges")
        else ""
    )

    file_lines = [
        f"{f['path']} ({f.get('kind', 'file')}, {f.get('size', '?')} bytes)" for f in files
    ]
    files_body = "\n".join(file_lines) if file_lines else "(no files in trajectory directory yet)"

    expected = report.get("expected") or {}
    verify_bits = []
    if expected.get("expected_path"):
        verify_bits.append(f"expected path={expected['expected_path']}")
    if expected.get("expected_vision_calls") is not None:
        verify_bits.append(f"expected vision calls={expected['expected_vision_calls']}")
    if expected.get("verify_hint"):
        verify_bits.append(str(expected["verify_hint"]))
    verify_body = "\n".join(verify_bits) if verify_bits else "(see task catalogue)"

    return [
        {"n": 1, "title": "Original user goal", "body": report.get("user_goal") or "(none)"},
        {"n": 2, "title": "Planner DAG", "body": dag_body.strip() or "(none)"},
        {
            "n": 3,
            "title": "Cascade path chosen",
            "body": format_computer_path(run.get("path")),
            "badge": run.get("path"),
        },
        {
            "n": 4,
            "title": "start_recording evidence",
            "body": _recording_checklist(run),
            "trajectory_dir": trajectory_dir,
        },
        {
            "n": 5,
            "title": "Computer actions taken",
            "body": "\n".join(action_lines) if action_lines else "(no actions logged in ComputerOutput)",
            "count": len(action_lines),
        },
        {
            "n": 6,
            "title": "Trajectory directory files",
            "body": files_body,
            "screenshots": images,
            "count": len(files),
        },
        {
            "n": 7,
            "title": "Manifest snapshot",
            "body": _manifest_summary(trajectory_dir),
        },
        {
            "n": 8,
            "title": "Result & task verify",
            "body": (
                f"result={run.get('result_preview') or sanitize_evidence_text(run.get('result')) or '(none)'}\n"
                f"app={run.get('app') or '?'}\n"
                f"turns={run.get('turns', 0)}\n"
                f"elapsed={run.get('elapsed_s')}s\n"
                f"actions={run.get('action_count', 0)}\n\n"
                f"{verify_body}"
            ),
        },
    ]


def replay_report_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Computer-use trajectory evidence",
        "",
        f"**Session:** `{report.get('session_id', '')}`",
        f"**Trajectory:** `{((report.get('computer_runs') or [{}])[0] or {}).get('trajectory_dir', '')}`",
        "",
    ]
    for sec in format_computer_replay_sections(report):
        lines.append(f"## {sec['n']}. {sec['title']}")
        lines.append("")
        lines.append("```text")
        lines.append(str(sec.get("body") or "").strip() or "(empty)")
        lines.append("```")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def build_computer_replay_report(session_id: str, *, node_id: str | None = None) -> dict[str, Any]:
    """Full computer trajectory report for a persisted session."""
    store = SessionStore(session_id)
    if not store.exists():
        raise FileNotFoundError(f"No session at {store.root}")

    query = store.load_query() or ""
    states = store.load_all_node_states()
    graph = store.load_graph()

    computer_runs: list[dict[str, Any]] = []
    primary_id: str | None = None

    for nid, data in graph.nodes(data=True):
        if data.get("skill") != "computer":
            continue
        if node_id and nid != node_id:
            continue
        primary_id = nid
        st = states.get(nid)
        out = _parse_json(st.output if st else None)
        payload = computer_replay_payload(out)
        if not payload.get("available"):
            continue
        computer_runs.append(
            {
                "node_id": nid,
                "label": (data.get("metadata") or {}).get("label") or nid,
                **payload,
                "status": st.status.value if st and hasattr(st.status, "value") else None,
                "error": st.error if st else None,
            }
        )

    query_id = _query_id_from_session(session_id)
    primary_run = _pick_primary_computer_run(computer_runs)
    primary_id = str(primary_run.get("node_id") or primary_id or "")

    report: dict[str, Any] = {
        "kind": "computer",
        "available": bool(computer_runs) or bool(query),
        "session_id": session_id,
        "query_id": query_id,
        "node_id": primary_id or None,
        "user_goal": query,
        "planner_dag": _planner_dag_summary(store),
        "computer_runs": computer_runs,
        "expected": _expected_for_query(query_id),
    }
    report["frames"] = _build_replay_frames(primary_run) if primary_run else []
    report["sections"] = format_computer_replay_sections(report)
    report["markdown"] = replay_report_markdown(report)
    return report


def _is_test_artifact_session(session_id: str, trajectory_dir: str) -> bool:
    """Drop stale rows where trajectory_dir points at pytest temp outside state/."""
    if _safe_trajectory_dir(trajectory_dir):
        return False
    traj = str(trajectory_dir or "").replace("\\", "/")
    return "/tmp/pytest" in traj


def list_computer_evidence_sessions(limit: int = 40) -> list[dict[str, Any]]:
    """Summaries of computer-use runs across persisted sessions (newest first)."""
    from ..graph_viz import list_dag_sessions

    rows: list[dict[str, Any]] = []
    for meta in list_dag_sessions()[:limit]:
        sid = str(meta.get("session_id") or "")
        if not sid or not _COMPUTER_QUERY_RE.match(sid):
            continue
        try:
            report = build_computer_replay_report(sid)
        except (FileNotFoundError, OSError):
            continue
        for run in report.get("computer_runs") or []:
            traj = str(run.get("trajectory_dir") or "")
            if _is_test_artifact_session(sid, traj):
                continue
            rows.append(
                {
                    "session_id": sid,
                    "query_id": report.get("query_id"),
                    "node_id": run.get("node_id"),
                    "path": run.get("path"),
                    "result": run.get("result_preview") or sanitize_evidence_text(run.get("result")),
                    "result_preview": run.get("result_preview"),
                    "trajectory_dir": traj,
                    "action_count": run.get("action_count", 0),
                    "elapsed_s": run.get("elapsed_s"),
                    "elapsed_ms": run.get("elapsed_ms"),
                    "recording_ok": run.get("recording_ok"),
                    "status": run.get("status"),
                    "error": run.get("error"),
                    "query_preview": meta.get("query_preview"),
                    "run_complete": meta.get("run_complete"),
                }
            )
    rows.sort(key=lambda r: str(r.get("session_id") or ""), reverse=True)
    return rows
