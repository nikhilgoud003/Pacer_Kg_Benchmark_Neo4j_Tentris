#!/usr/bin/env bash
# Start official Tentris Docker (works on Mac with license file).
#
# Usage:
#   ./start_tentris_docker.sh        # foreground
#   ./start_tentris_docker.sh --bg   # background
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
RDF_DIR="${RDF_DIR:-$ROOT_DIR/../kg_out/rdf}"
RDF_FILE="${RDF_FILE:-$RDF_DIR/pacer.nt}"
LICENSE="${TENTRIS_LICENSE:-$SCRIPT_DIR/tentris-license.toml}"
DATA_VOL="${TENTRIS_DATA:-$RDF_DIR/tentris-data}"
PORT="${TENTRIS_PORT:-9080}"
CONTAINER_NAME="${TENTRIS_CONTAINER:-tentris-pacer-bench}"
BG=0
[[ "${1:-}" == "--bg" ]] && BG=1

if [[ ! -f "$LICENSE" ]]; then
  echo "Missing license at $LICENSE"
  echo "Copy yours: cp ~/Downloads/tentris-license-Apah.toml $SCRIPT_DIR/tentris-license.toml"
  exit 1
fi

if [[ ! -f "$RDF_FILE" ]]; then
  python3 "$SCRIPT_DIR/convert_to_rdf.py" \
    --input "$ROOT_DIR/../kg_out/nikhil_test" \
    --output "$RDF_FILE" --format nt
fi

mkdir -p "$DATA_VOL"
docker rm -f "$CONTAINER_NAME" 2>/dev/null || true

echo "Pulling ghcr.io/tentris/tentris:latest ..."
docker pull ghcr.io/tentris/tentris:latest

echo "Starting Tentris (loading $RDF_FILE on first init) ..."
docker run -d --name "$CONTAINER_NAME" \
  -v "$LICENSE:/config/tentris-license.toml:ro" \
  -v "$DATA_VOL:/data" \
  -v "$RDF_DIR:/rdf:ro" \
  -e "TENTRIS_RDF_FILE=/rdf/$(basename "$RDF_FILE")" \
  -p "${PORT}:9080" \
  ghcr.io/tentris/tentris:latest

echo "Waiting for Tentris on port $PORT ..."
for i in $(seq 1 60); do
  if curl -sf "http://localhost:${PORT}/sparql" \
      -H "Content-Type: application/sparql-query" \
      -H "Accept: application/sparql-results+json" \
      --data "SELECT (COUNT(*) AS ?c) WHERE { ?s ?p ?o }" >/dev/null 2>&1; then
    echo "OK  Tentris ready at http://localhost:${PORT}/ui"
    exit 0
  fi
  sleep 5
  if [[ $((i % 6)) -eq 0 ]]; then
    echo "  still loading... (${i}x5s) — docker logs $CONTAINER_NAME"
    docker logs "$CONTAINER_NAME" 2>&1 | tail -3
  fi
done

echo "FAIL — check: docker logs $CONTAINER_NAME"
exit 1
