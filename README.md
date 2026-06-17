# Computer Use Agent

<p align="center">
  <img src="Images/app-icon.svg" alt="Computer Use Agent logo" width="72" height="72">
</p>

<p align="center">
  <strong>Computer Use Agent</strong> — a desktop automation skill for the EAG computer-use assignment.<br>
  Five-layer cascade · <code>cua-driver</code> · recorded trajectory evidence
</p>

Computer Use Agent adds a `computer` skill to the DAG catalogue, drives primary-OS apps with `cua-driver`, follows a visible five-layer cascade, records every run with `start_recording`, and returns the `trajectory_dir` as evidence.

The computer-use skill uses direct Gemini SDK calls for text and vision judgment. Deterministic work stays in `cua-driver` actions, and vision is called only when the cascade reaches Layer 3.

## Quick Start

```bash
uv sync
cp .env.example .env   # GEMINI_API_KEY
./scripts/serve.sh
```

Open `http://127.0.0.1:8080/` → **Tasks** sidebar → run the three computer-use tasks:

| Task | Layer | Target | Vision |
|------|-------|--------|--------|
| **CU-CALC** | 2a hotkey | Calculator · `847 × 293` | 0 calls |
| **CU-CURSOR** | 2b electron | Cursor · write evidence note | 0 calls |
| **CU-CANVAS** | 3 vision | Canvas fixture · red circle | ≥1 call |

For the Cursor/Electron task, launch Cursor with a debugging port first:

```powershell
computer_use_agent/computer/scripts/launch_cursor_debug.ps1
```

When running the server from WSL2 on a Windows machine, install `cua-driver` on Windows:

```powershell
irm https://raw.githubusercontent.com/trycua/cua/main/libs/cua-driver/scripts/install.ps1 | iex
```

The app searches Windows PATH and the default install folder. If needed:

```bash
export CUA_DRIVER_WIN_BIN="/mnt/c/Users/<you>/AppData/Local/Programs/Cua/cua-driver/bin/cua-driver.exe"
```

Do not use a Linux `cua-driver` binary inside WSL for Windows desktop automation.

The UI auto-starts the `cua-driver serve` daemon when needed (required for element-index clicks on tasks like **CU-CALC**).

## Assignment Brief

Build a Computer-Use skill that drops into the DAG and solves **three real tasks** on your primary OS. Respect the five-layer architecture so cascade discipline is visible in code. Record every run with `start_recording` and submit the trajectory directory as evidence.

### Picked tasks (from the brief)

| Id | Category from brief | Concrete task | Winning path | Vision |
|----|---------------------|---------------|--------------|--------|
| `CU-CALC` | Calculator / simple arithmetic with deterministic hotkeys | Open Calculator and compute `847 * 293` | `hotkey` | 0 |
| `CU-CURSOR` | Electron app using page tool + `electron_debugging_port` | In Cursor, write `computer-use layer2b ok` to `notes/computer_use_evidence.txt` | `electron` | 0 |
| `CU-CANVAS` | Canvas-rendered target forcing vision | Open the local canvas fixture and click the red circle | `vision` | ≥1 |

### Constraint coverage

| Constraint | Satisfied by |
|------------|--------------|
| At least one task uses **vision** | `CU-CANVAS` |
| At least one task uses the **Electron page path** | `CU-CURSOR` |
| At least one task completes with **zero vision calls** | `CU-CALC`, `CU-CURSOR` |
| Every run calls **start_recording** | All three tasks |

### Icons & UI

The web UI uses shadcn-style components, lucide-style SVG icons, and a consistent brand lockup (`app-icon.svg` in headers, chat welcome, and favicon).

Task icons live in `Images/`:

- `app-icon.svg` — app logo & favicon
- `icon-calc.svg`, `icon-cursor-app.svg`, `icon-canvas.svg` — task cards in the UI
- `cascade.svg`, `cursor-mark.svg` — cascade / agent cursor marks

### Sidebar & main views

| Tab | Purpose |
|-----|---------|
| **Overview** | Connection status, cascade strip, assignment checklist, how-it-works (scrollable) |
| **Tasks** | Run CU-CALC, CU-CURSOR, CU-CANVAS from the catalogue |
| **Evidence** | Checklist + run cards; open the full trajectory report |
| **DAG** | Live session graph — click nodes for skill, status, and actions |
| **Replay** | Browser/computer trajectory replay (steps, screenshots, files) |

Sidebar panels scroll independently when content exceeds the viewport.

## Five-Layer Cascade

| Layer | Path | Role |
|-------|------|------|
| Layer 1 | `read` | Read-only AX snapshot, no LLM |
| Layer 2a | `hotkey` | Deterministic hotkey/button scripts, no LLM |
| Layer 2b | `electron` | Electron apps through `electron_debugging_port` and page/CDP text |
| Layer 2b | `ax` | AX element indices with cheap text judgment |
| Layer 3 | `vision` | Screenshot + vision adapter + pixel clicks |

Escalation stops at the first layer that satisfies the goal. Tasks pin their expected layer in `corpus/dag/ASSIGNMENT.json` via `computer_metadata.force_path`.

## Evidence

Each `computer` run returns a `ComputerOutput` payload:

```json
{
  "app": "Calculator",
  "goal": "...",
  "path": "hotkey",
  "turns": 0,
  "result": "248171",
  "actions": [],
  "trajectory_dir": "state/sessions/<session>/computer/..."
}
```

Submit the `trajectory_dir` for each run as evidence. The YouTube demo should show the agent-cursor overlay while at least one computer-use task runs live.

## Important Files

| Purpose | Path |
|---------|------|
| Computer-use cascade | `computer_use_agent/computer/skill.py` |
| Layer implementations | `computer_use_agent/computer/layer*.py` |
| Trajectory replay & evidence API | `computer_use_agent/computer/replay.py` |
| Canvas fixture | `computer_use_agent/computer/fixtures/canvas_only.html` |
| Cursor debug launcher | `computer_use_agent/computer/scripts/launch_cursor_debug.ps1` |
| Task catalogue | `corpus/dag/ASSIGNMENT.json` |
| UI | `templates/index.html` |
| DAG graph (client) | `static/dag-graph.js` |
| Skill registration | `agent_config.yaml` |
| Computer prompt | `prompts/computer.md` |

## Failure Modes

- Cursor must be launched with `electron_debugging_port=9222` before `CU-CURSOR`.
- WSL2 must use the Windows `cua-driver.exe`. The app auto-starts `cua-driver serve` when needed; if clicks still fail, confirm the daemon manually.
- Stale evidence rows from old test runs can appear in the UI — use **Clear Durable State (state/)** on the Tasks tab or delete leftover `dag_CU-*` session folders.
- Calculator window discovery can vary by OS app name or locale.
- The canvas fixture depends on a local app window opening `computer_use_agent/computer/fixtures/canvas_only.html`.
- If `start_recording` fails, the skill returns a structured error instead of silently continuing.

## Evidence in the UI

After each computer-use run:

1. Open the **Evidence** sidebar tab — checklist for CU-CALC / CU-CURSOR / CU-CANVAS with path, action count, elapsed time, and recording status.
2. Click **Open full report** (or a run card) to open the **Trajectory evidence** main panel:
   - Action **timeline** from `turn-*/action.json` (tool, ms timestamp, sanitized summary)
   - Elapsed timer, layer path, planner DAG flow, result preview, `trajectory_dir`
   - Screenshot gallery when PNG artifacts exist in the trajectory (e.g. vision turns)
3. Use **Replay** for browser or computer trajectory reports (steps, screenshots, manifest).
4. Use **DAG** to inspect the live graph — each node shows actions taken at that step.
5. Copy `trajectory_dir` and submit it as assignment evidence.

The UI sanitizes long UI dumps (e.g. Cursor `get_text` noise) so evidence cards and timelines stay readable. Duplicate pytest temp paths under `/tmp/pytest` are filtered from the evidence list when they are not valid `state/` trajectories.

### DAG sidebar

- **Selected node** — skill, status, elapsed time, output preview, and **action summary** per node.
- **Memory hits (session start)** — collapsed expander by default; shows a count badge (e.g. `3 unique · 8 stored`) and deduplicated hits when expanded.
- DAG view preserves pan/zoom during live polling (no jumpy auto-fit on every node update).

### Replay tab

Full-page session replay (browser or computer): trajectory sections, screenshots when recorded, and copyable report text. Separate from the **Evidence** assignment checklist.

### API endpoints

| Endpoint | Purpose |
|----------|---------|
| `GET /api/dag/computer-evidence` | List computer-use runs across sessions |
| `GET /api/dag/computer-replay?session_id=…` | Full replay report (timeline, sections, markdown) |
| `GET /api/dag/computer-artifact?trajectory_dir=…&path=…` | Serve a file inside a trajectory directory |
| `GET /api/dag/graph?session_id=…` | DAG graph payload for the UI |

## Tests

```bash
uv run pytest tests/test_assignment_spec.py tests/test_dag_queries_api.py tests/test_computer_skill.py tests/test_computer_replay.py -q
uv run pytest
```
