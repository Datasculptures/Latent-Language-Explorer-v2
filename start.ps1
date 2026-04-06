# start.ps1 — Launch LLE V2 on Windows
# Usage: .\start.ps1         (start servers)
#        .\start.ps1 -Install (install dependencies first)

param([switch]$Install)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

# Dependency checks
if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    Write-Error "ERROR: py launcher not found. Install Python 3.11+ from python.org."; exit 1
}
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    Write-Error "ERROR: node not found. Install Node.js 20+."; exit 1
}

# Load .env
if (Test-Path ".env") {
    Get-Content ".env" | Where-Object { $_ -match "^[A-Z_]+=.+" } | ForEach-Object {
        $parts = $_ -split "=", 2
        [System.Environment]::SetEnvironmentVariable($parts[0], $parts[1], "Process")
    }
} else {
    Write-Warning ".env not found. Copy .env.example to .env to enable generative decoding."
}

if ($Install) {
    Write-Host "Installing Python dependencies..."
    py -m pip install -r backend/requirements.txt
    Write-Host "Installing Node dependencies..."
    Set-Location frontend; npm install; Set-Location ..
}

$BackendPort  = if ($env:PORT_BACKEND)  { $env:PORT_BACKEND }  else { "8000" }
$FrontendPort = if ($env:PORT_FRONTEND) { $env:PORT_FRONTEND } else { "3000" }

Write-Host ""
Write-Host "  Latent Language Explorer V2"
Write-Host "  Backend:  http://localhost:$BackendPort/api/docs"
Write-Host "  Frontend: http://localhost:$FrontendPort"
Write-Host "  Press Ctrl+C to stop."
Write-Host ""

# Start backend — set PYTHONPATH so py 3.14 can find packages in the local venv
$SitePackages = Join-Path (Split-Path $ScriptDir -Parent) "Lib\site-packages"
$env:PYTHONPATH = $SitePackages
$BackendJob = Start-Process -FilePath "py" `
    -ArgumentList "-m uvicorn backend.app.main:app --host 0.0.0.0 --port $BackendPort --reload --reload-dir backend" `
    -WorkingDirectory $ScriptDir `
    -NoNewWindow -PassThru

# Start frontend
$FrontendJob = Start-Process -FilePath "cmd" `
    -ArgumentList "/c cd frontend && npm run dev" `
    -NoNewWindow -PassThru

Write-Host "Backend PID:  $($BackendJob.Id)"
Write-Host "Frontend PID: $($FrontendJob.Id)"
Write-Host "Press Enter to stop both servers."
Read-Host

Stop-Process -Id $BackendJob.Id  -ErrorAction SilentlyContinue
Stop-Process -Id $FrontendJob.Id -ErrorAction SilentlyContinue
Write-Host "Stopped."
