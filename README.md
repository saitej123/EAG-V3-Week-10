# Computer Use Agent

<p align="center">
  <img src="Images/app-icon.svg" alt="Computer Use Agent logo" width="72" height="72">
</p>

<p align="center">
  <strong>Computer Use Agent</strong> — a desktop automation skill for primary-OS computer-use tasks.<br>
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

Open `http://127.0.0.1:8080/` → **Tasks** sidebar → run the six computer-use task categories:

| Task | Layer | Target | Vision |
|------|-------|--------|--------|
| **CU-CALC** | 2a hotkey | Calculator · `847 × 293` | 0 calls |
| **CU-AX-NOTE** | 2b AX | Notepad · status note via AX tree | 0 calls |
| **CU-CURSOR** | 2b electron | Cursor · write evidence note | 0 calls |
| **CU-CANVAS** | 3 vision | Canvas fixture · red circle | ≥1 call |
| **CU-MSG** | 2b AX | Notepad · message draft with text verification | 0 calls |
| **CU-MULTI** | 2a hotkey | Calculator → Notepad result handoff | 0 calls |

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

## Task Coverage

The task catalogue covers the requested primary-OS computer-use categories. Each run goes through the DAG `computer` skill, records with `start_recording`, and returns a `trajectory_dir` for evidence.

### Computer-use tasks

| Id | Category from brief | Concrete task | Winning path | Vision |
|----|---------------------|---------------|--------------|--------|
| `CU-CALC` | Calculator / simple arithmetic with deterministic hotkeys | Open Calculator and compute `847 * 293` | `hotkey` | 0 |
| `CU-AX-NOTE` | Spreadsheet or notes-app task using AX + cheap text judgment | Open Notepad and write `AX layer verified for notes` | `ax` | 0 |
| `CU-CURSOR` | Electron app using page tool + `electron_debugging_port` | In Cursor, write `computer-use layer2b ok` to `notes/computer_use_evidence.txt` | `electron` | 0 |
| `CU-CANVAS` | Canvas-rendered target forcing vision | Open the local canvas fixture and click the red circle | `vision` | ≥1 |
| `CU-MSG` | Email/message draft composition with strong verification | Draft a review-ready message in Notepad and verify exact text | `ax` | 0 |
| `CU-MULTI` | Multi-app workflow moving data between apps | Compute in Calculator, then write the result in Notepad | `hotkey` | 0 |

### Constraint coverage

| Constraint | Satisfied by |
|------------|--------------|
| At least one task uses **vision** | `CU-CANVAS` |
| At least one task uses the **Electron page path** | `CU-CURSOR` |
| At least one task completes with **zero vision calls** | `CU-CALC`, `CU-AX-NOTE`, `CU-CURSOR`, `CU-MSG`, `CU-MULTI` |
| Layer 2b AX is exercised | `CU-AX-NOTE`, `CU-MSG` |
| Multi-app workflow is exercised | `CU-MULTI` |
| Every run calls **start_recording** | All six CU tasks |

### Icons & UI

The web UI uses shadcn-style components, lucide-style SVG icons, and a consistent brand lockup (`app-icon.svg` in headers, chat welcome, and favicon).

Task icons live in `Images/`:

- `app-icon.svg` — app logo & favicon
- `icon-calc.svg`, `icon-cursor-app.svg`, `icon-canvas.svg` — specialized task card icons
- `cascade.svg`, `cursor-mark.svg` — cascade / agent cursor marks

### Sidebar & main views

| Tab | Purpose |
|-----|---------|
| **Overview** | Connection status, cascade strip, task catalogue, how-it-works (scrollable) |
| **Tasks** | Run `CU-CALC`, `CU-AX-NOTE`, `CU-CURSOR`, `CU-CANVAS`, `CU-MSG`, or `CU-MULTI` from the catalogue |
| **DAG** | Unified workspace with three sub-tabs (see below) |

The **DAG** tab hosts three sub-views:

| Sub-tab | Purpose |
|---------|---------|
| **Graph** | Live session graph — click nodes for skill, status, and actions |
| **Evidence** | Constraint badges + task checklist + run cards; open the full trajectory report and `trajectory_dir` |
| **Replay** | Video-style trajectory playback — autoplay, scrubber, prev/next, and stage chapters, with the step log below |

Sidebar panels scroll independently when content exceeds the viewport.

## Five-Layer Cascade

| Layer | Path | Role |
|-------|------|------|
| Layer 1 | `read` | Read-only AX snapshot, no LLM |
| Layer 2a | `hotkey` | Deterministic hotkey/button scripts, no LLM |
| Layer 2b | `electron` | Electron apps through `electron_debugging_port` and page/CDP text |
| Layer 2b | `ax` | AX element indices with cheap text judgment |
| Layer 3 | `vision` | Screenshot + vision adapter + pixel clicks |

Escalation stops at the first layer that satisfies the goal. Catalogue rows pin their expected layer in `corpus/dag/ASSIGNMENT.json` via `computer_metadata.force_path`.

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

Use the `trajectory_dir` for each run as evidence. A demo recording can show the agent-cursor overlay while at least one computer-use task runs live.

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
- The canvas fixture opens `computer_use_agent/computer/fixtures/canvas_only.html`; under WSL the launcher prefers Windows Edge and falls back to the default Windows handler.
- For `CU-CANVAS`, Layer 3 first calls vision on the screenshot; if the model does not emit a usable click, the fixture-specific fallback clicks the detected red blob center and records that action.
- AX tasks (`CU-AX-NOTE`, `CU-MSG`) reuse an existing matching app window or wait briefly after launch so `pid/window_id` are resolved before element-index actions.
- If `start_recording` fails, the skill returns a structured error instead of silently continuing.

## Evidence in the UI

After each computer-use run, open the **DAG** tab and switch sub-tabs:

1. **Evidence** sub-tab — constraint badges (vision used / electron path / zero-vision run) plus a checklist for all six CU tasks with path, action count, elapsed time, and recording status.
2. Click a run card to slide in the **Trajectory evidence** detail panel:
   - Action **timeline** from `turn-*/action.json` (tool, ms timestamp, sanitized summary)
   - Elapsed timer, layer path, planner DAG flow, result preview, `trajectory_dir`
   - Screenshot gallery when PNG artifacts exist in the trajectory (e.g. vision turns)
3. **Replay** sub-tab — video-style trajectory playback (steps, screenshots, manifest).
4. **Graph** sub-tab — inspect the live graph; each node shows actions taken at that step.
5. Copy `trajectory_dir` and use it as recorded run evidence.

The UI sanitizes long UI dumps (e.g. Cursor `get_text` noise) so evidence cards and timelines stay readable. Duplicate pytest temp paths under `/tmp/pytest` are filtered from the evidence list when they are not valid `state/` trajectories.

### DAG Graph sub-tab

- **Selected node** — skill, status, elapsed time, output preview, and **action summary** per node.
- **Memory hits (session start)** — collapsed expander by default; shows a count badge (e.g. `3 unique · 8 stored`) and deduplicated hits when expanded.
- The graph centers and fits on first render and when the Graph sub-tab is shown; it preserves pan/zoom during live polling (no jumpy auto-fit on every node update).

### Replay sub-tab

Video-style session replay (browser or computer): a large stage image with Play/Pause, Prev/Next, a scrubber with chapter ticks, adjustable speed, and stage chapters grouped by cascade layer. The full trajectory sections (steps, screenshots, copyable report text) render below the player.

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
