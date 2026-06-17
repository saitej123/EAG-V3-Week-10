"""Tests for computer trajectory evidence replay."""

from __future__ import annotations

import json

import networkx as nx

from computer_use_agent.computer.replay import (
    build_computer_replay_report,
    computer_replay_payload,
    format_computer_replay_sections,
    list_computer_evidence_sessions,
    resolve_trajectory_artifact,
)
from computer_use_agent.dag_schemas import NodeState, NodeStatus
from computer_use_agent.persistence import SessionStore


def test_computer_replay_payload():
    payload = computer_replay_payload(
        {
            "app": "Calculator",
            "goal": "847 * 293",
            "path": "hotkey",
            "result": "248171",
            "actions": [{"turn": 1, "actions": [{"tool": "launch_app", "args": {"name": "Calculator"}}]}],
            "trajectory_dir": "/tmp/not-allowed",
        }
    )
    assert payload["available"] is True
    assert payload["path"] == "hotkey"
    assert payload["action_count"] == 1
    assert payload["recording_ok"] is False
    assert payload["result_preview"] == "248171"


def test_sanitize_evidence_text_strips_noise():
    from computer_use_agent.computer.replay import sanitize_evidence_text

    raw = "￼\n￼\nFile\nEdit\n" + ("x" * 300)
    cleaned = sanitize_evidence_text(raw, max_len=40)
    assert "￼" not in cleaned
    assert cleaned.endswith("…")
    assert len(cleaned) <= 40


def test_build_computer_replay_report(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    state_root = tmp_path / "state" / "sessions" / "dag_CU-CALC_test01"
    traj = state_root / "computer" / "trajectory_123"
    traj.mkdir(parents=True)
    (traj / "manifest.json").write_text(
        json.dumps({"app": "Calculator", "goal": "847 * 293", "started_at": 1.0}),
        encoding="utf-8",
    )
    turn_dir = traj / "turn-00001"
    turn_dir.mkdir()
    (turn_dir / "action.json").write_text(
        json.dumps(
            {
                "tool": "launch_app",
                "arguments": {"name": "Calculator"},
                "result_summary": "Launched Calculator",
                "t_ms_from_session_start": 1200,
            }
        ),
        encoding="utf-8",
    )
    (traj / "artifacts").mkdir()
    (traj / "artifacts" / "vision_turn_01.png").write_bytes(b"\x89PNG\r\n")

    store = SessionStore("dag_CU-CALC_test01")
    store.save_query("Compute 847 * 293 on Calculator")
    g = nx.DiGraph()
    g.add_node("n:1", skill="planner", metadata={"label": "p"})
    g.add_node("n:2", skill="computer", metadata={"label": "c"})
    g.add_edge("n:1", "n:2")
    store.save_graph(g)

    out = {
        "app": "Calculator",
        "goal": "847 * 293",
        "path": "hotkey",
        "result": "248171",
        "actions": [
            {"tool": "launch_app", "args": {"name": "Calculator"}},
            {"tool": "type_text", "args": {"text": "847*293="}},
        ],
        "trajectory_dir": str(traj.resolve()),
    }
    store.save_node_state(
        NodeState(
            node_id="n:2",
            skill="computer",
            status=NodeStatus.complete,
            output=json.dumps(out),
        )
    )

    report = build_computer_replay_report("dag_CU-CALC_test01")
    assert report["kind"] == "computer"
    assert report["query_id"] == "CU-CALC"
    assert report["computer_runs"][0]["result"] == "248171"
    assert report["computer_runs"][0]["recording_ok"] is True
    assert report["computer_runs"][0]["action_count"] == 1
    assert report["computer_runs"][0]["timeline"][0]["tool"] == "launch_app"
    sections = format_computer_replay_sections(report)
    assert len(sections) == 8
    assert "start_recording" in sections[3]["title"].lower()
    assert sections[5]["count"] >= 1
    assert "1200ms" in sections[4]["body"]

    resolved = resolve_trajectory_artifact(str(traj.resolve()), "manifest.json")
    assert resolved and resolved.is_file()

    rows = list_computer_evidence_sessions()
    assert any(r["session_id"] == "dag_CU-CALC_test01" for r in rows)


def test_computer_evidence_api(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    state_root = tmp_path / "state" / "sessions" / "dag_CU-CALC_api01"
    traj = state_root / "computer" / "trajectory_999"
    traj.mkdir(parents=True)
    (traj / "manifest.json").write_text("{}", encoding="utf-8")

    store = SessionStore("dag_CU-CALC_api01")
    store.save_query("calc")
    g = nx.DiGraph()
    g.add_node("n:2", skill="computer")
    store.save_graph(g)
    store.save_node_state(
        NodeState(
            node_id="n:2",
            skill="computer",
            status=NodeStatus.complete,
            output=json.dumps(
                {
                    "app": "Calculator",
                    "goal": "847 * 293",
                    "path": "hotkey",
                    "result": "248171",
                    "actions": [{"tool": "launch_app"}],
                    "trajectory_dir": str(traj.resolve()),
                }
            ),
        )
    )

    from fastapi.testclient import TestClient

    import app as app_mod

    client = TestClient(app_mod.app)
    res = client.get("/api/dag/computer-evidence")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "success"
    assert any(r["session_id"] == "dag_CU-CALC_api01" for r in body["runs"])

    replay = client.get("/api/dag/computer-replay?session_id=dag_CU-CALC_api01")
    assert replay.status_code == 200
    assert replay.json()["kind"] == "computer"
