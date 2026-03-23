#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Dependency checks
if ! command -v python3 &>/dev/null; then
  echo "ERROR: python3 not found. Install Python 3.11+."; exit 1
fi
if ! command -v node &>/dev/null; then
  echo "ERROR: node not found. Install Node.js 20+."; exit 1
fi

# Load .env
if [ -f .env ]; then
  set -a; source .env; set +a
else
  echo "WARNING: .env not found. Copy .env.example to .env to enable generative decoding."
fi

# Install dependencies if requested
if [[ "${1:-}" == "--install" ]]; then
  echo "Installing Python dependencies..."
  pip3 install -r backend/requirements.txt
  echo "Installing Node dependencies..."
  cd frontend && npm install && cd ..
fi

BACKEND_PORT="${PORT_BACKEND:-8000}"
FRONTEND_PORT="${PORT_FRONTEND:-3000}"

# Port checks
for port in $BACKEND_PORT $FRONTEND_PORT; do
  if command -v lsof &>/dev/null && lsof -i ":$port" &>/dev/null 2>&1; then
    echo "WARNING: Port $port already in use."
  fi
done

echo ""
echo "  Latent Language Explorer V2"
echo "  Backend:  http://localhost:${BACKEND_PORT}/api/docs"
echo "  Frontend: http://localhost:${FRONTEND_PORT}"
echo "  Press Ctrl+C to stop both servers."
echo ""

# Start backend
python3 -m uvicorn backend.app.main:app \
  --host 0.0.0.0 \
  --port "$BACKEND_PORT" \
  --reload \
  --reload-dir backend &
BACKEND_PID=$!

# Start frontend
cd frontend && npm run dev &
FRONTEND_PID=$!

# Cleanup on exit
trap "echo 'Stopping...'; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit 0" EXIT INT TERM

wait
