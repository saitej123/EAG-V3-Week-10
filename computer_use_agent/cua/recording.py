"""Trajectory recording via cua-driver start_recording / stop_recording."""
from __future__ import annotations

import json
import time
from pathlib import Path

from .client import CuaDriverClient


class TrajectorySession:
    def __init__(
        self,
        output_dir: Path,
        *,
        session_id: str = "",
        goal: str = "",
        app: str = "",
        client: CuaDriverClient | None = None,
    ):
        self.output_dir = output_dir
        self.session_id = session_id
        self.goal = goal
        self.app = app
        self._client = client or CuaDriverClient()
        self._started = False

    def start(self) -> Path:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        manifest = {
            "session_id": self.session_id,
            "app": self.app,
            "goal": self.goal,
            "started_at": time.time(),
            "cua_output_dir": str(self.output_dir),
        }
        (self.output_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )
        self._client.start_recording(str(self.output_dir.resolve()))
        self._started = True
        return self.output_dir

    def stop(self) -> None:
        if self._started:
            try:
                self._client.stop_recording()
            except Exception:
                pass
            self._started = False


def start_recording(
    base_dir: Path,
    *,
    session_id: str = "",
    goal: str = "",
    app: str = "",
    client: CuaDriverClient | None = None,
) -> TrajectorySession:
    ts = int(time.time())
    out = base_dir / f"trajectory_{ts}"
    sess = TrajectorySession(out, session_id=session_id, goal=goal, app=app, client=client)
    sess.start()
    return sess
