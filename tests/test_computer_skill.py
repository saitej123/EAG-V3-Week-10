import pytest

from computer_use_agent.computer import layer2b_electron as electron_mod
from computer_use_agent.computer.skill import ComputerSkill
from computer_use_agent.cua.client import CuaDriverError
from computer_use_agent.cua.response_utils import (
    normalize_action_plan,
    windows_from_response,
)
from computer_use_agent.dag_schemas import NodeSpec


@pytest.mark.asyncio
async def test_computer_skill_returns_error_if_recording_fails(monkeypatch, tmp_path):
    class FakeClient:
        def __init__(self):
            pass

        def ensure_daemon(self):
            return None

    def boom(*args, **kwargs):
        raise RuntimeError("recording boom")

    monkeypatch.setattr("computer_use_agent.computer.skill.CuaDriverClient", FakeClient)
    monkeypatch.setattr("computer_use_agent.computer.skill.start_recording", boom)

    skill = ComputerSkill(artifacts_root=str(tmp_path), session="session-test")
    result = await skill.run(
        NodeSpec(
            skill="computer",
            metadata={"app": "Calculator", "goal": "What is 2*3?"},
        )
    )

    assert result.success is False
    assert result.error_code == "computer_environment"
    assert "recording boom" in (result.error or "")


def test_wsl_requires_windows_cua_driver(monkeypatch):
    from computer_use_agent.cua import client as client_mod

    monkeypatch.setenv("WSL_DISTRO_NAME", "Ubuntu")
    monkeypatch.delenv("CUA_DRIVER_BIN", raising=False)
    monkeypatch.delenv("CUA_DRIVER_WIN_BIN", raising=False)
    monkeypatch.setattr(client_mod.shutil, "which", lambda _name: "/root/.local/bin/cua-driver")
    monkeypatch.setattr(client_mod, "_find_windows_cua_driver", lambda: None)

    with pytest.raises(CuaDriverError) as exc:
        client_mod._find_cua_driver()

    assert "Windows cua-driver.exe" in str(exc.value)


def test_cua_response_normalization():
    plan = normalize_action_plan([{"type": "done", "success": True, "note": "ok"}])
    assert plan["actions"][0]["type"] == "done"
    wins = windows_from_response({"windows": [{"pid": 1, "window_id": 2}]})
    assert wins[0]["pid"] == 1


@pytest.mark.asyncio
async def test_electron_accepts_list_llm_plan(monkeypatch):
    class FakeClient:
        def list_windows(self, pid=None):
            return {"windows": [{"pid": 1, "window_id": 2, "title": "Cursor", "app_name": "Cursor.exe"}]}

    class FakeLLM:
        async def chat(self, **kwargs):
            class R:
                parsed = [{"type": "done", "success": True, "note": "ok"}]
                text = "[]"

            return R()

    monkeypatch.setattr(electron_mod, "_page_text", lambda *args, **kwargs: "computer-use layer2b ok")

    result = await electron_mod.run_electron(
        FakeClient(),
        FakeLLM(),
        app="Cursor",
        goal="update notes/computer_use_evidence.txt",
        electron_port=9222,
    )
    assert result.success is True


def test_infer_calculator_display_indian_grouping():
    from computer_use_agent.computer.layer2a_hotkey import _infer_result

    actions = [
        {
            "tool": "get_window_state",
            "result": {
                "tree_markdown": 'Text "Display is 2,48,171" [id=CalculatorResults]',
            },
        }
    ]
    assert _infer_result(actions, "Calculator") == "248171"


@pytest.mark.asyncio
async def test_hotkey_script_ensures_daemon(monkeypatch):
    from computer_use_agent.computer import layer2a_hotkey as hotkey_mod

    ensured = {"called": False}

    class FakeClient:
        def ensure_daemon(self):
            ensured["called"] = True

        def launch_app_named(self, name, **kwargs):
            return {"pid": 1, "windows": [{"pid": 1, "window_id": 2, "title": "Calculator"}]}

        def list_windows(self, pid=None):
            return {"windows": [{"pid": 1, "window_id": 2, "title": "Calculator"}]}

        def get_window_state(self, pid, window_id, **kwargs):
            return {"tree_markdown": 'Text "Display is 248171"'}

        def click(self, **kwargs):
            return {}

    monkeypatch.setattr(hotkey_mod, "_type_calculator_expr", lambda *a, **k: {"snapshot": {}})

    out = await hotkey_mod.run_hotkey_script(
        FakeClient(),
        hotkey_mod.DEFAULT_CALC_SCRIPT,
        app="Calculator",
    )
    assert ensured["called"] is True
    assert out["success"] is True
    assert out["result"] == "248171"
