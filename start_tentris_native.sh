#!/usr/bin/env bash
# Start Tentris on Apple Silicon Mac (native ARM binary — NOT dicegroup docker).
#   1. Free license from https://tentris.io → save as ~/.config/tentris-license.toml
#   2. Install: curl -sSf https://raw.githubusercontent.com/tentris/tentris/refs/heads/main/install.sh | sh
#
# Usage:
#   ./start_tentris_native.sh          # load RDF + start server (foreground)
#   ./start_tentris_native.sh --bg     # load RDF + start server in background
#
set -euo pipefail

export PATH="$HOME/.local/bin:$PATH"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
RDF_FILE="${RDF_FILE:-$ROOT_DIR/../kg_out/rdf/pacer.nt}"
DATASTORE="${TENTRIS_DATASTORE:-$SCRIPT_DIR/tentris_data}"
PORT="${TENTRIS_PORT:-9080}"
LICENSE="${TENTRIS_LICENSE:-$HOME/.config/tentris-license.toml}"
# Fallback: project-local or Downloads copy
if [[ ! -f "$LICENSE" && -f "$SCRIPT_DIR/tentris-license.toml" ]]; then
  LICENSE="$SCRIPT_DIR/tentris-license.toml"
fi
if [[ ! -f "$LICENSE" && -f "$HOME/Downloads/tentris-license-Apah.toml" ]]; then
  LICENSE="$HOME/Downloads/tentris-license-Apah.toml"
fi
BG=0
[[ "${1:-}" == "--bg" ]] && BG=1

red()  { printf '\033[0;31m%s\033[0m\n' "$*"; }
grn()  { printf '\033[0;32m%s\033[0m\n' "$*"; }
ylw()  { printf '\033[0;33m%s\033[0m\n' "$*"; }

if ! command -v tentris >/dev/null 2>&1; then
  red "tentris CLI not found."
  echo ""
  echo "Install (native ARM Mac — recommended):"
  echo '  curl --proto https --tlsv1.2 -sSf https://raw.githubusercontent.com/tentris/tentris/refs/heads/main/install.sh | sh'
  echo ""
  echo "If install fails with libgcc_s missing, run: brew install gcc@14"
  echo "Or use official Docker: ./start_tentris_docker.sh"
  echo "License should be at ~/.config/tentris-license.toml"
  exit 1
fi

if [[ ! -f "$LICENSE" ]]; then
  red "Missing license: $LICENSE"
  echo "Request free license at https://tentris.io"
  echo "Then: mv ~/Downloads/tentris-license.toml ~/.config/tentris-license.toml"
  exit 1
fi

if [[ ! -f "$RDF_FILE" ]]; then
  ylw "RDF not found — converting..."
  python3 "$SCRIPT_DIR/convert_to_rdf.py" \
    --input "$ROOT_DIR/../kg_out/nikhil_test" \
    --output "$RDF_FILE" --format nt
fi

# Stop anything on port 9080
if lsof -ti:"$PORT" >/dev/null 2>&1; then
  ylw "Port $PORT in use — stopping existing process..."
  kill "$(lsof -ti:"$PORT")" 2>/dev/null || true
  sleep 2
fi

echo "=== Loading RDF into Tentris (offline) ==="
echo "  Input:     $RDF_FILE"
echo "  Datastore: $DATASTORE"
rm -rf "$DATASTORE"
mkdir -p "$DATASTORE"

tentris --license "$LICENSE" --datastore-path "$DATASTORE" load < "$RDF_FILE"
grn "Load complete."

echo ""
echo "=== Starting Tentris server on port $PORT ==="

if [[ $BG -eq 1 ]]; then
  nohup tentris --license "$LICENSE" --datastore-path "$DATASTORE" serve \
    > "$SCRIPT_DIR/tentris_server.log" 2>&1 &
  echo $! > "$SCRIPT_DIR/tentris_server.pid"
  echo "PID: $(cat "$SCRIPT_DIR/tentris_server.pid")"
  echo "Log: $SCRIPT_DIR/tentris_server.log"

  for i in $(seq 1 30); do
    if curl -sf "http://localhost:${PORT}/sparql" \
        -H "Content-Type: application/sparql-query" \
        -H "Accept: application/sparql-results+json" \
        --data "SELECT (COUNT(*) AS ?c) WHERE { ?s ?p ?o }" >/dev/null 2>&1; then
      grn "Tentris ready at http://localhost:${PORT}"
      exit 0
    fi
    sleep 2
  done
  red "Server did not become ready — check tentris_server.log"
  exit 1
else
  grn "Server starting (Ctrl+C to stop). UI: http://localhost:${PORT}/ui"
  exec tentris --license "$LICENSE" --datastore-path "$DATASTORE" serve
fi
