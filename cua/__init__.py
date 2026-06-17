"""Compatibility package for the top-level cua import path.

The implementation lives under the computer_use_agent/cua directory.
This shim makes the existing imports such as `from cua.client import ...`
work from both the repo root and the alias package path used by tests.
"""

from pathlib import Path

__path__ = [str((Path(__file__).resolve().parent.parent / "computer_use_agent" / "cua").resolve())]
