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


def test_wsl_file_uri_converted_for_windows_driver(monkeypatch):
    from computer_use_agent.cua import client as client_mod

    monkeypatch.setenv("WSL_DISTRO_NAME", "Ubuntu")

    assert (
        client_mod._wsl_file_uri_to_windows(
            "file:///mnt/d/Learning/TSAI/EAG-V3/EAG-V3-Week-10/computer_use_agent/computer/fixtures/canvas_only.html"
        )
        == "file:///D:/Learning/TSAI/EAG-V3/EAG-V3-Week-10/computer_use_agent/computer/fixtures/canvas_only.html"
    )


def test_launch_app_normalizes_wsl_file_uri_for_windows_driver(monkeypatch, tmp_path):
    from computer_use_agent.cua import client as client_mod

    monkeypatch.setenv("WSL_DISTRO_NAME", "Ubuntu")
    exe = tmp_path / "cua-driver.exe"
    exe.write_text("", encoding="utf-8")
    captured = {}

    class Proc:
        returncode = 0
        stdout = "{}"
        stderr = ""

    def fake_run(command, **kwargs):
        captured["command"] = command
        return Proc()

    monkeypatch.setattr(client_mod.subprocess, "run", fake_run)

    client = client_mod.CuaDriverClient(binary=str(exe))
    client.launch_app(urls=["file:///mnt/d/Learning/canvas_only.html"])

    assert captured["command"][2] == "launch_app"
    assert "file:///D:/Learning/canvas_only.html" in captured["command"][3]


def test_canvas_fixture_uses_windows_shell_under_wsl(monkeypatch):
    from computer_use_agent.computer import layer3_vision as vision_mod

    calls = {}

    class FakeClient:
        def launch_app(self, **kwargs):
            raise AssertionError("canvas fixture should not call cua-driver launch_app under WSL")

    class FakePopen:
        def __init__(self, command, **kwargs):
            calls["command"] = command

    monkeypatch.setenv("WSL_DISTRO_NAME", "Ubuntu")
    monkeypatch.setattr(vision_mod.subprocess, "Popen", FakePopen)

    launched = vision_mod._launch_canvas_fixture(FakeClient())

    assert launched == {}
    assert calls["command"][:4] == ["cmd.exe", "/C", "start", ""]
    assert calls["command"][4] == "msedge"
    assert calls["command"][5].startswith("file:///")
    assert "/mnt/" not in calls["command"][5]


def test_canvas_wait_accepts_new_browser_window(monkeypatch):
    from computer_use_agent.computer import layer3_vision as vision_mod

    calls = {"list": 0}

    class FakeClient:
        def list_windows(self, pid=None):
            calls["list"] += 1
            if calls["list"] == 1:
                return {
                    "windows": [
                        {"pid": 1, "window_id": 2, "title": "Cursor", "app_name": "Cursor.exe"},
                    ]
                }
            return {
                "windows": [
                    {"pid": 1, "window_id": 2, "title": "Cursor", "app_name": "Cursor.exe"},
                    {"pid": 11, "window_id": 12, "title": "New tab", "app_name": "msedge.exe"},
                ]
            }

    before = vision_mod._window_keys(FakeClient().list_windows())
    monkeypatch.setattr(vision_mod.time, "sleep", lambda _seconds: None)

    pid, wid = vision_mod._wait_for_canvas_window(
        FakeClient(),
        before_windows=before,
        attempts=2,
    )

    assert (pid, wid) == (11, 12)


@pytest.mark.asyncio
async def test_canvas_vision_falls_back_to_red_blob_click(monkeypatch):
    import base64
    import io

    from PIL import Image, ImageDraw

    from computer_use_agent.computer import layer3_vision as vision_mod

    im = Image.new("RGB", (640, 480), "white")
    draw = ImageDraw.Draw(im)
    draw.ellipse((250, 220, 410, 380), fill="red")
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    image_url = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
    clicks = []

    class FakeClient:
        def list_windows(self, pid=None):
            return {"windows": []}

        def get_window_state(self, pid, window_id, **kwargs):
            return {
                "screenshot_png_b64": image_url.split(",", 1)[1],
                "screenshot_width": 640,
                "screenshot_height": 480,
            }

        def click(self, **kwargs):
            clicks.append(kwargs)
            return {}

    class FakeLLM:
        async def vision(self, **kwargs):
            class R:
                parsed = {"thinking": "I can see the red circle", "actions": []}
                text = "{}"

            return R()

    monkeypatch.setattr(vision_mod, "_launch_canvas_fixture", lambda _client: {})
    monkeypatch.setattr(vision_mod, "_wait_for_canvas_window", lambda *a, **k: (7, 8))

    result = await vision_mod.run_vision(
        FakeClient(),
        FakeLLM(),
        app="browser",
        goal="open canvas fixture and click inside the red circle",
    )

    assert result.success is True
    assert clicks
    assert 325 <= clicks[0]["x"] <= 335
    assert 295 <= clicks[0]["y"] <= 305
    assert result.actions[0]["actions"][-1]["source"] == "red_blob_fallback"


def test_enrich_computer_metadata_pins_assignment_calc_metadata():
    from computer_use_agent.computer.goal_utils import enrich_computer_metadata

    meta = enrich_computer_metadata(
        {
            "label": "bad planner output",
            "app": "desktop",
            "force_path": "vision",
            "hotkey_script": ["launch_app", "type_text"],
        },
        "Using the computer skill on my primary OS, open Calculator and compute 847 * 293. "
        "Use Layer 2a deterministic hotkeys only, record the run with start_recording, "
        "and return the numeric result plus trajectory_dir evidence.",
    )

    assert meta["query_id"] == "CU-CALC"
    assert meta["app"] == "Calculator"
    assert meta["force_path"] == "hotkey"
    assert meta["hotkey_script"][0]["tool"] == "launch_app"


def test_script_for_metadata_falls_back_when_custom_script_malformed():
    from computer_use_agent.computer.layer2a_hotkey import DEFAULT_CALC_SCRIPT, script_for_metadata

    assert (
        script_for_metadata({"hotkey_script": ["launch_app", {"tool": ""}]}, "Calculator")
        == DEFAULT_CALC_SCRIPT
    )


@pytest.mark.asyncio
async def test_hotkey_script_rejects_malformed_steps_without_empty_cua_call():
    from computer_use_agent.computer.layer2a_hotkey import run_hotkey_script

    class FakeClient:
        def ensure_daemon(self):
            return None

        def call(self, tool, args):
            raise AssertionError(f"should not call cua-driver with tool={tool!r}")

    out = await run_hotkey_script(FakeClient(), [{"args": {}}], app="Calculator")

    assert out["success"] is False
    assert "missing tool" in out["result"]


@pytest.mark.asyncio
async def test_hotkey_type_text_resolves_window_before_typing():
    from computer_use_agent.computer.layer2a_hotkey import run_hotkey_script

    calls = {}

    class FakeClient:
        def ensure_daemon(self):
            return None

        def list_windows(self, pid=None):
            calls.setdefault("list_windows", []).append(pid)
            return {"windows": [{"pid": 77, "window_id": 88, "title": "Notepad", "app_name": "Notepad.exe"}]}

        def launch_app_named(self, name, **kwargs):
            raise AssertionError("existing window should be reused")

        def type_text(self, pid, text, **kwargs):
            calls["type_text"] = {"pid": pid, "text": text, **kwargs}
            return {"text": text}

    out = await run_hotkey_script(
        FakeClient(),
        [{"tool": "type_text", "args": {"text": "hello"}}],
        app="Notepad",
    )

    assert out["success"] is True
    assert calls["type_text"]["pid"] == 77
    assert calls["type_text"]["window_id"] == 88


@pytest.mark.asyncio
async def test_hotkey_type_text_reports_missing_window_without_pid_zero_call():
    from computer_use_agent.computer.layer2a_hotkey import run_hotkey_script

    class FakeClient:
        def ensure_daemon(self):
            return None

        def list_windows(self, pid=None):
            return {"windows": []}

        def launch_app_named(self, name, **kwargs):
            return {}

        def launch_app(self, **kwargs):
            return {}

        def type_text(self, pid, text, **kwargs):
            raise AssertionError(f"should not call type_text with pid={pid}")

    out = await run_hotkey_script(
        FakeClient(),
        [{"tool": "type_text", "args": {"text": "hello"}}],
        app="Notepad",
    )

    assert out["success"] is False
    assert "type_text requires a target window" in out["result"]


@pytest.mark.asyncio
async def test_hotkey_script_retargets_after_second_launch(monkeypatch):
    from computer_use_agent.computer import layer2a_hotkey as hotkey_mod

    typed = []

    class FakeClient:
        def ensure_daemon(self):
            return None

        def launch_app_named(self, name, **kwargs):
            if name == "Calculator":
                return {"pid": 10, "windows": [{"pid": 10, "window_id": 11, "title": "Calculator"}]}
            if name == "Notepad":
                return {"pid": 20, "windows": [{"pid": 20, "window_id": 21, "title": "Notepad"}]}
            return {}

        def list_windows(self, pid=None):
            wins = [
                {"pid": 10, "window_id": 11, "title": "Calculator", "app_name": "Calculator.exe"},
                {"pid": 20, "window_id": 21, "title": "Notepad", "app_name": "Notepad.exe"},
            ]
            if pid is not None:
                wins = [w for w in wins if w["pid"] == pid]
            return {"windows": wins}

        def type_text(self, pid, text, **kwargs):
            typed.append({"pid": pid, "window_id": kwargs.get("window_id"), "text": text})
            return {"text": text}

        def get_window_state(self, pid, window_id, **kwargs):
            return {"tree_markdown": ""}

        def click(self, **kwargs):
            return {}

    monkeypatch.setattr(hotkey_mod, "_type_calculator_expr", lambda *a, **k: {"text": "248171"})

    out = await hotkey_mod.run_hotkey_script(
        FakeClient(),
        [
            {"tool": "launch_app", "args": {"name": "Calculator"}},
            {"tool": "type_text", "args": {"text": "847*293="}},
            {"tool": "launch_app", "args": {"name": "Notepad"}},
            {"tool": "type_text", "args": {"text": "Calculator result: 248171"}},
        ],
        app="Calculator",
    )

    assert out["success"] is True
    assert typed[-1] == {"pid": 20, "window_id": 21, "text": "Calculator result: 248171"}


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


@pytest.mark.asyncio
async def test_ax_reuses_existing_matching_window(monkeypatch):
    from computer_use_agent.computer import layer2b_ax as ax_mod

    class FakeClient:
        def list_windows(self, pid=None):
            return {"windows": [{"pid": 77, "window_id": 88, "title": "Untitled - Notepad", "app_name": "Notepad.exe"}]}

        def launch_app_named(self, name, **kwargs):
            raise AssertionError("existing window should be reused")

        def get_window_state(self, pid, window_id, **kwargs):
            assert (pid, window_id) == (77, 88)
            return {"markdown": "Untitled - Notepad\nAX layer verified for notes"}

    class FakeLLM:
        async def chat(self, **kwargs):
            class R:
                parsed = {"actions": [{"type": "done", "success": True, "note": "ok"}]}
                text = "{}"

            return R()

    result = await ax_mod.run_ax(
        FakeClient(),
        FakeLLM(),
        app="Notepad",
        goal="create note AX layer verified for notes",
    )

    assert result.success is True
    assert result.pid == 77
    assert result.window_id == 88


@pytest.mark.asyncio
async def test_ax_waits_for_window_after_launch(monkeypatch):
    from computer_use_agent.computer import layer2b_ax as ax_mod

    calls = {"list": 0}

    class FakeClient:
        def list_windows(self, pid=None):
            calls["list"] += 1
            if calls["list"] < 3:
                return {"windows": []}
            return {"windows": [{"pid": 91, "window_id": 92, "title": "Untitled - Notepad", "app_name": "Notepad.exe"}]}

        def launch_app_named(self, name, **kwargs):
            return {"pid": 91, "windows": []}

        def get_window_state(self, pid, window_id, **kwargs):
            assert (pid, window_id) == (91, 92)
            return {"markdown": "Untitled - Notepad\nAX layer verified for notes"}

    class FakeLLM:
        async def chat(self, **kwargs):
            class R:
                parsed = {"actions": [{"type": "done", "success": True, "note": "ok"}]}
                text = "{}"

            return R()

    monkeypatch.setattr(ax_mod.time, "sleep", lambda _seconds: None)

    result = await ax_mod.run_ax(
        FakeClient(),
        FakeLLM(),
        app="Notepad",
        goal="create note AX layer verified for notes",
    )

    assert result.success is True
    assert result.pid == 91
    assert result.window_id == 92


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
