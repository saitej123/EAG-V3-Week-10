# Launch Cursor with Chrome DevTools Protocol for Layer 2b electron tasks.
# Run this BEFORE the orchestrator task that uses electron_debugging_port=9222.
$port = 9222
if ($env:CURSOR_ELECTRON_DEBUG_PORT) { $port = $env:CURSOR_ELECTRON_DEBUG_PORT }

Write-Host "Starting Cursor with --remote-debugging-port=$port" -ForegroundColor Cyan
$cursor = Get-Command cursor -ErrorAction SilentlyContinue
if (-not $cursor) {
    Write-Host "ERROR: cursor not on PATH. Install Cursor or add it to PATH." -ForegroundColor Red
    exit 1
}
Start-Process -FilePath $cursor.Source -ArgumentList "--remote-debugging-port=$port"
Write-Host "Cursor started. CDP endpoint: http://127.0.0.1:$port" -ForegroundColor Green
