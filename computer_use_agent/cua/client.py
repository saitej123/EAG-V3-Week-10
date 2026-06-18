"""Thin wrapper around the cua-driver CLI (daemon-backed).

ComputerSkill and CuaDriverClient share this module. Tool-using skills
reach cua-driver via mcp_runner's MCP stdio session instead.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import re
import time
from typing import Any
from urllib.parse import quote, unquote, urlparse


class CuaDriverError(RuntimeError):
    pass


def _running_in_wsl() -> bool:
    if os.environ.get("WSL_DISTRO_NAME"):
        return True
    try:
        return "microsoft" in Path("/proc/version").read_text(encoding="utf-8").lower()
    except OSError:
        return False


def _windows_driver_candidates() -> list[str]:
    candidates: list[str] = []
    explicit = os.environ.get("CUA_DRIVER_WIN_BIN")
    if explicit:
        candidates.insert(0, explicit)
    legacy_explicit = os.environ.get("CUA_DRIVER_BIN")
    if legacy_explicit and legacy_explicit.lower().endswith(".exe"):
        candidates.append(legacy_explicit)
    path_exe = shutil.which("cua-driver.exe")
    if path_exe:
        candidates.append(path_exe)
    local = os.environ.get("LOCALAPPDATA")
    if local:
        candidates.append(os.path.join(local, "Programs", "Cua", "cua-driver", "bin", "cua-driver.exe"))
    users_root = Path("/mnt/c/Users")
    if users_root.is_dir():
        for user_dir in users_root.iterdir():
            if not user_dir.is_dir() or user_dir.name.lower() in {"public", "default", "default user"}:
                continue
            candidates.append(
                str(user_dir / "AppData" / "Local" / "Programs" / "Cua" / "cua-driver" / "bin" / "cua-driver.exe")
            )
    return candidates


def _windows_path_to_wsl(path: str) -> str:
    cleaned = path.strip().strip('"')
    if cleaned.startswith("/mnt/"):
        return cleaned
    match = re.match(r"^([A-Za-z]):[\\/](.*)$", cleaned)
    if not match:
        return cleaned
    drive = match.group(1).lower()
    rest = match.group(2).replace("\\", "/")
    return f"/mnt/{drive}/{rest}"


def _windows_driver_from_subprocess() -> str | None:
    commands = [
        ["cmd.exe", "/C", "where", "cua-driver.exe"],
        ["cmd.exe", "/C", "where", "cua-driver"],
        [
            "powershell.exe",
            "-NoProfile",
            "-Command",
            "$cmd = Get-Command cua-driver.exe -ErrorAction SilentlyContinue; if ($cmd) { $cmd.Source }",
        ],
        [
            "powershell.exe",
            "-NoProfile",
            "-Command",
            "$p = Join-Path $env:LOCALAPPDATA 'Programs\\Cua\\cua-driver\\bin\\cua-driver.exe'; "
            "if (Test-Path $p) { $p }",
        ],
    ]
    for command in commands:
        try:
            proc = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=8,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if proc.returncode != 0:
            continue
        for line in (proc.stdout or "").splitlines():
            candidate = _windows_path_to_wsl(line)
            if candidate.lower().endswith(".exe") and os.path.isfile(candidate):
                return candidate
    return None


def _find_windows_cua_driver() -> str | None:
    for candidate in _windows_driver_candidates():
        normalized = _windows_path_to_wsl(candidate)
        if normalized and normalized.lower().endswith(".exe") and os.path.isfile(normalized):
            return normalized
    return _windows_driver_from_subprocess()


def _is_windows_exe(path: str) -> bool:
    return path.lower().endswith(".exe")


def _wsl_path_to_windows(path: str) -> str:
    if not _running_in_wsl() or not path.startswith("/mnt/") or len(path) < 7:
        return path
    drive = path[5]
    if path[6] != "/":
        return path
    rest = path[7:].replace("/", "\\")
    return f"{drive.upper()}:\\{rest}"


def _wsl_file_uri_to_windows(uri: str) -> str:
    """Convert WSL file:// URIs to Windows file:// URIs for Windows cua-driver.exe."""
    if not _running_in_wsl() or not isinstance(uri, str) or not uri.startswith("file://"):
        return uri
    parsed = urlparse(uri)
    path = unquote(parsed.path or "")
    if not path.startswith("/mnt/") or len(path) < 7 or path[6] != "/":
        return uri
    drive = path[5].upper()
    rest = path[7:].replace("\\", "/")
    return "file:///" + drive + ":/" + quote(rest, safe="/:@")


def _normalize_windows_launch_args(args: dict[str, Any]) -> dict[str, Any]:
    """Normalize launch_app paths when WSL calls the Windows driver."""
    changed = False
    normalized = dict(args)
    urls = normalized.get("urls")
    if isinstance(urls, list):
        next_urls = []
        for value in urls:
            next_value = _wsl_file_uri_to_windows(value) if isinstance(value, str) else value
            changed = changed or next_value != value
            next_urls.append(next_value)
        normalized["urls"] = next_urls
    launch_path = normalized.get("launch_path")
    if isinstance(launch_path, str):
        next_path = _wsl_path_to_windows(launch_path)
        changed = changed or next_path != launch_path
        normalized["launch_path"] = next_path
    return normalized if changed else args


def _find_cua_driver() -> str:
    if _running_in_wsl():
        win = _find_windows_cua_driver()
        if win:
            return win
        linux_env = os.environ.get("CUA_DRIVER_BIN") or shutil.which("cua-driver") or "/root/.local/bin/cua-driver"
        raise CuaDriverError(
            "Windows desktop automation must use the Windows cua-driver.exe from WSL2. "
            "I searched Windows PATH and the default install folder but could not find it. "
            "Install cua-driver on Windows, add it to Windows PATH, or set CUA_DRIVER_WIN_BIN "
            f"to the .exe path. Ignored Linux driver: {linux_env}"
        )
    env = os.environ.get("CUA_DRIVER_BIN")
    if env and os.path.isfile(env):
        return env
    found = shutil.which("cua-driver")
    if found:
        return found
    win_default = os.path.join(
        os.environ.get("LOCALAPPDATA", ""),
        "Programs", "Cua", "cua-driver", "bin", "cua-driver.exe",
    )
    if win_default and os.path.isfile(win_default):
        return win_default
    raise CuaDriverError(
        "cua-driver not found on PATH. Install from https://github.com/trycua/cua "
        "(Windows: irm https://raw.githubusercontent.com/trycua/cua/main/libs/cua-driver/scripts/install.ps1 | iex)"
    )


class CuaDriverClient:
    """Call cua-driver tools through `cua-driver call <tool> <json>`."""

    def __init__(self, binary: str | None = None):
        self.binary = binary or _find_cua_driver()
        self._windows_binary = _is_windows_exe(self.binary)

    def daemon_running(self) -> bool:
        try:
            proc = subprocess.run(
                [self.binary, "status"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=8,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False
        out = f"{proc.stdout or ''}{proc.stderr or ''}".lower()
        return proc.returncode == 0 and "daemon is running" in out

    def ensure_daemon(self, *, timeout_s: float = 12.0) -> None:
        """Start `cua-driver serve` when needed so element_index cache persists across calls."""
        if self.daemon_running():
            return
        try:
            subprocess.Popen(
                [self.binary, "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError as e:
            raise CuaDriverError(f"failed to start cua-driver serve: {e}") from e
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if self.daemon_running():
                return
            time.sleep(0.25)
        raise CuaDriverError(
            "cua-driver daemon did not start in time. Run `cua-driver serve` on Windows "
            "or `cua-driver autostart enable` so element_index clicks work."
        )

    def call(self, tool: str, arguments: dict[str, Any] | None = None) -> Any:
        args = arguments or {}
        if self._windows_binary and tool == "start_recording" and isinstance(args.get("output_dir"), str):
            args = dict(args)
            args["output_dir"] = _wsl_path_to_windows(args["output_dir"])
        elif self._windows_binary and tool == "launch_app":
            args = _normalize_windows_launch_args(args)
        payload = json.dumps(args, ensure_ascii=True)
        proc = subprocess.run(
            [self.binary, "call", tool, payload],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            check=False,
        )
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip()
            if "glibc_2.39" in err.lower() or "glibc_2.39" in err:
                raise CuaDriverError(
                    "Linux cua-driver cannot run in this WSL2 image because GLIBC_2.39 is missing. "
                    "Use the Windows cua-driver.exe instead: install it on Windows and set "
                    "CUA_DRIVER_WIN_BIN to the .exe path."
                )
            raise CuaDriverError(f"cua-driver {tool} failed ({proc.returncode}): {err[:500]}")
        out = (proc.stdout or "").strip()
        if not out:
            return {}
        try:
            return json.loads(out)
        except json.JSONDecodeError:
            return {"raw": out}

    def launch_app(self, **kwargs: Any) -> dict:
        return self.call("launch_app", kwargs)

    def list_apps(self) -> dict:
        return self.call("list_apps", {})

    def launch_app_named(self, name: str, **kwargs: Any) -> dict:
        from .response_utils import launch_app_named

        return launch_app_named(self, name, **kwargs)

    def list_windows(self, pid: int | None = None) -> dict:
        body: dict[str, Any] = {}
        if pid is not None:
            body["pid"] = pid
        return self.call("list_windows", body)

    def get_window_state(
        self,
        pid: int,
        window_id: int,
        *,
        capture_mode: str = "ax",
        query: str | None = None,
    ) -> dict:
        body: dict[str, Any] = {
            "pid": pid,
            "window_id": window_id,
            "capture_mode": capture_mode,
        }
        if query:
            body["query"] = query
        return self.call("get_window_state", body)

    def click(self, pid: int, window_id: int, **kwargs: Any) -> dict:
        body: dict[str, Any] = {"pid": pid, "window_id": window_id, **kwargs}
        return self.call("click", body)

    def type_text(self, pid: int, text: str, **kwargs: Any) -> dict:
        body: dict[str, Any] = {"pid": pid, "text": text, **kwargs}
        return self.call("type_text", body)

    def hotkey(self, keys: list[str], **kwargs: Any) -> dict:
        return self.call("hotkey", {"keys": keys, **kwargs})

    def press_key(self, key: str, **kwargs: Any) -> dict:
        return self.call("press_key", {"key": key, **kwargs})

    def page(
        self,
        pid: int,
        action: str,
        *,
        window_id: int | None = None,
        **kwargs: Any,
    ) -> dict:
        body: dict[str, Any] = {"pid": pid, "action": action, **kwargs}
        if window_id is not None:
            body["window_id"] = window_id
        return self.call("page", body)

    def start_recording(self, output_dir: str, *, record_video: bool = False) -> dict:
        return self.call(
            "start_recording",
            {"output_dir": output_dir, "record_video": record_video},
        )

    def stop_recording(self) -> dict:
        return self.call("stop_recording", {})

    def get_recording_state(self) -> dict:
        return self.call("get_recording_state", {})
