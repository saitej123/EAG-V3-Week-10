"""Normalize cua-driver and LLM payloads to the shapes ComputerSkill expects."""
from __future__ import annotations

from typing import Any


def as_dict(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        return payload
    return {}


def windows_from_response(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [w for w in payload if isinstance(w, dict)]
    if not isinstance(payload, dict):
        return []
    wins = payload.get("windows")
    if wins is None:
        wins = payload.get("_legacy_windows")
    if isinstance(wins, list):
        return [w for w in wins if isinstance(w, dict)]
    return []


def normalize_action_plan(parsed: Any) -> dict[str, Any]:
    """Coerce LLM JSON into {thinking, actions:[{type,...}, ...]}."""
    if isinstance(parsed, dict):
        actions = parsed.get("actions")
        if isinstance(actions, dict):
            actions = [actions]
        elif not isinstance(actions, list):
            actions = []
        return {
            "thinking": str(parsed.get("thinking") or ""),
            "actions": [a for a in actions if isinstance(a, dict)],
        }
    if isinstance(parsed, list):
        if parsed and isinstance(parsed[0], dict) and (
            "actions" in parsed[0] or "thinking" in parsed[0]
        ):
            return normalize_action_plan(parsed[0])
        return {
            "thinking": "",
            "actions": [a for a in parsed if isinstance(a, dict)],
        }
    return {"thinking": "", "actions": []}


def apps_from_response(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [a for a in payload if isinstance(a, dict)]
    if not isinstance(payload, dict):
        return []
    apps = payload.get("apps")
    if isinstance(apps, list):
        return [a for a in apps if isinstance(a, dict)]
    return []


def find_app_entry(client: Any, name_hint: str) -> dict[str, Any] | None:
    """Resolve a desktop app via cua-driver list_apps (preferred on Windows)."""
    hint = (name_hint or "").strip().lower()
    if not hint:
        return None
    listed = client.list_apps()
    for app in apps_from_response(listed):
        name = str(app.get("name") or "").lower()
        bundle = str(app.get("bundle_id") or "").lower()
        if hint == name or hint in name or name in hint or hint in bundle:
            return app
    return None


def launch_app_named(client: Any, name: str, **kwargs: Any) -> dict[str, Any]:
    """Launch using list_apps launch_path when available.

    Official cua-driver on Windows: ``launch_path`` beats ``name`` for packaged apps.
    ``electron_debugging_port`` on launch_app is currently a no-op on Windows — start
    Electron apps with ``--remote-debugging-port`` via launch_cursor_debug.ps1 instead.
    """
    body: dict[str, Any] = dict(kwargs)
    entry = find_app_entry(client, name)
    if entry and entry.get("launch_path"):
        body["launch_path"] = entry["launch_path"]
        body.pop("name", None)
        body.pop("electron_debugging_port", None)
    elif name and "launch_path" not in body and "path" not in body:
        body["name"] = name
    return client.call("launch_app", body)


def page_text_from_response(payload: Any) -> str:
    if isinstance(payload, str):
        return payload
    if isinstance(payload, dict):
        for key in ("text", "content", "raw"):
            val = payload.get(key)
            if isinstance(val, str) and val.strip():
                return val
        import json

        return str(json.dumps(payload)[:4000])
    if isinstance(payload, list):
        parts = [page_text_from_response(item) for item in payload[:5]]
        joined = "\n".join(p for p in parts if p)
        return joined[:4000]
    return ""
