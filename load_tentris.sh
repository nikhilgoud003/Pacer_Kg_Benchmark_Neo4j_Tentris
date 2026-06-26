#!/usr/bin/env bash
# Load PACER KG into Tentris: convert CSV → RDF, then start Tentris with data.
#
# Option A — dicegroup/tentris_server (simple, no license, loads .nt at startup):
#   ./load_tentris.sh --simple
#
# Option B — official Tentris image (needs tentris-license.toml):
#   ./load_tentris.sh
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
INPUT_DIR="${INPUT_DIR:-$ROOT_DIR/../kg_out/nikhil_test}"
RDF_DIR="${RDF_DIR:-$ROOT_DIR/../kg_out/rdf}"
RDF_FILE="${RDF_FILE:-$RDF_DIR/pacer.nt}"
PORT="${TENTRIS_PORT:-9080}"
MODE="${1:-}"

mkdir -p "$RDF_DIR"

echo "=== Step 1: Convert property graph CSV → RDF N-Triples ==="
python3 "$SCRIPT_DIR/convert_to_rdf.py" \
  --input "$INPUT_DIR" \
  --output "$RDF_FILE" \
  --format nt

echo ""
echo "=== Step 2: Start Tentris ==="

if [[ "$MODE" == "--simple" ]]; then
  echo "Using dicegroup/tentris_server (loads RDF at startup, port $PORT)"
  docker pull dicegroup/tentris_server 2>/dev/null || true
  docker run --rm \
    -v "$RDF_DIR:/datasets:ro" \
    -p "${PORT}:9080" \
    dicegroup/tentris_server \
    -f "/datasets/$(basename "$RDF_FILE")"
else
  LICENSE="${TENTRIS_LICENSE:-$SCRIPT_DIR/tentris-license.toml}"
  DATA_VOL="${TENTRIS_DATA:-$RDF_DIR/tentris-data}"
  mkdir -p "$DATA_VOL"

  if [[ ! -f "$LICENSE" ]]; then
    echo "ERROR: Missing Tentris license at $LICENSE"
    echo "  Request one at https://tentris.io/ or use: ./load_tentris.sh --simple"
    exit 1
  fi

  echo "Using ghcr.io/tentris/tentris (official image, port $PORT)"
  docker run --rm \
    -v "$LICENSE:/config/tentris-license.toml:ro" \
    -v "$DATA_VOL:/data" \
    -v "$RDF_DIR:/rdf:ro" \
    -e "TENTRIS_RDF_FILE=/rdf/$(basename "$RDF_FILE")" \
    -p "${PORT}:9080" \
    ghcr.io/tentris/tentris:latest
fi
