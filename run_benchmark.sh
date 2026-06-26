#!/usr/bin/env bash
# Prereq check + Neo4j vs Tentris benchmark.
#
# On Apple Silicon Mac: use native Tentris binary (dicegroup docker image is amd64-only).
#
#   cd pacer_kg/tentris
#   export NEO4J_PASSWORD='Nikhil2001'
#   ./run_benchmark.sh
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
INPUT_DIR="${INPUT_DIR:-$ROOT_DIR/../kg_out/nikhil_test}"
RDF_DIR="${RDF_DIR:-$ROOT_DIR/../kg_out/rdf}"
RDF_FILE="${RDF_FILE:-$RDF_DIR/pacer.nt}"
PORT="${TENTRIS_PORT:-9080}"
NEO4J_PASSWORD="${NEO4J_PASSWORD:-Nikhil2001}"
RUNS="${BENCHMARK_RUNS:-25}"
RUNS_MULTIHOP="${BENCHMARK_RUNS_MULTIHOP:-10}"
CONTAINER_NAME="${TENTRIS_CONTAINER:-tentris-pacer-bench}"
ARCH="$(uname -m)"

red()  { printf '\033[0;31m%s\033[0m\n' "$*"; }
grn()  { printf '\033[0;32m%s\033[0m\n' "$*"; }
ylw()  { printf '\033[0;33m%s\033[0m\n' "$*"; }

check_port() {
  local host=$1 port=$2 name=$3
  if nc -z "$host" "$port" 2>/dev/null; then
    grn "OK  $name listening on $host:$port"
    return 0
  fi
  red "FAIL $name not reachable on $host:$port"
  return 1
}

check_docker() {
  if docker info >/dev/null 2>&1; then
    grn "OK  Docker daemon reachable"
    return 0
  fi
  red "FAIL Docker daemon not reachable"
  return 1
}

wait_for_tentris() {
  local max=${1:-60}
  for i in $(seq 1 "$max"); do
    if curl -sf "http://localhost:${PORT}/sparql" \
        -H "Content-Type: application/sparql-query" \
        -H "Accept: application/sparql-results+json" \
        --data "SELECT (COUNT(*) AS ?c) WHERE { ?s ?p ?o }" >/dev/null 2>&1; then
      grn "OK  Tentris ready (${i} attempts)"
      return 0
    fi
    sleep 5
  done
  return 1
}

start_tentris_native() {
  if [[ -x "$SCRIPT_DIR/start_tentris_native.sh" ]]; then
    "$SCRIPT_DIR/start_tentris_native.sh" --bg
    return $?
  fi
  red "start_tentris_native.sh not found"
  return 1
}

start_tentris_official_docker() {
  local LICENSE="${TENTRIS_LICENSE:-$SCRIPT_DIR/tentris-license.toml}"
  local DATA_VOL="${TENTRIS_DATA:-$RDF_DIR/tentris-data}"
  if [[ ! -f "$LICENSE" ]]; then
    red "Missing license: $LICENSE (request at https://tentris.io)"
    return 1
  fi
  mkdir -p "$DATA_VOL"
  docker rm -f "$CONTAINER_NAME" 2>/dev/null || true
  docker pull ghcr.io/tentris/tentris:latest
  docker run -d --name "$CONTAINER_NAME" \
    -v "$LICENSE:/config/tentris-license.toml:ro" \
    -v "$DATA_VOL:/data" \
    -v "$RDF_DIR:/rdf:ro" \
    -e "TENTRIS_RDF_FILE=/rdf/$(basename "$RDF_FILE")" \
    -p "${PORT}:9080" \
    ghcr.io/tentris/tentris:latest
  wait_for_tentris 60
}

start_tentris_legacy_docker() {
  ylw "WARNING: dicegroup/tentris_server is linux/amd64 only — often fails on Apple Silicon."
  docker rm -f "$CONTAINER_NAME" 2>/dev/null || true
  docker pull dicegroup/tentris_server
  docker run -d --name "$CONTAINER_NAME" \
    --platform linux/amd64 \
    -v "$RDF_DIR:/datasets:ro" \
    -p "${PORT}:9080" \
    dicegroup/tentris_server \
    -f "/datasets/$(basename "$RDF_FILE")"
  wait_for_tentris 60
}

echo "=== PACER KG: Neo4j vs Tentris benchmark ==="
echo "  Architecture: $ARCH"
echo ""

BLOCKED=0
check_port localhost 7687 "Neo4j" || BLOCKED=1

if [[ $BLOCKED -eq 1 ]]; then
  ylw "Start Neo4j: docker start neo4j-kg"
  exit 1
fi

python3 - <<PY
from neo4j import GraphDatabase
d = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "$NEO4J_PASSWORD"))
with d.session() as s:
    n = s.run("MATCH (n) RETURN count(n) AS c").single()["c"]
    print(f"OK  Neo4j graph has {n:,} nodes")
d.close()
PY

mkdir -p "$RDF_DIR"
if [[ ! -f "$RDF_FILE" ]]; then
  echo "=== Converting CSV → RDF ==="
  python3 "$SCRIPT_DIR/convert_to_rdf.py" --input "$INPUT_DIR" --output "$RDF_FILE" --format nt
else
  grn "OK  RDF file exists: $RDF_FILE"
fi

# Start Tentris if needed
if check_port localhost "$PORT" "Tentris" 2>/dev/null; then
  grn "OK  Tentris already running"
else
  echo ""
  echo "=== Starting Tentris ==="
  STARTED=0

  if command -v tentris >/dev/null 2>&1; then
    ylw "Trying native Tentris binary (best for Apple Silicon)..."
    if start_tentris_native; then STARTED=1; fi
  fi

  if [[ $STARTED -eq 0 ]] && check_docker 2>/dev/null; then
    if [[ -f "${TENTRIS_LICENSE:-$SCRIPT_DIR/tentris-license.toml}" ]]; then
      ylw "Trying official ghcr.io/tentris/tentris Docker image..."
      if start_tentris_official_docker; then STARTED=1; fi
    fi
  fi

  if [[ $STARTED -eq 0 ]] && [[ "$ARCH" == "arm64" ]]; then
    echo ""
    red "Tentris could not start on Apple Silicon."
    echo ""
    echo "The old dicegroup/tentris_server image does NOT work on M-series Macs."
    echo ""
    echo "Fix (recommended — takes ~5 min):"
    echo "  1. Request free license: https://tentris.io"
    echo "  2. mv ~/Downloads/tentris-license.toml ~/.config/tentris-license.toml"
    echo '  3. curl -sSf https://raw.githubusercontent.com/tentris/tentris/refs/heads/main/install.sh | sh'
    echo "  4. ./start_tentris_native.sh --bg"
    echo "  5. ./run_benchmark.sh"
    echo ""
    echo "Clean up failed docker container:"
    echo "  docker rm -f $CONTAINER_NAME"
    exit 1
  fi

  if [[ $STARTED -eq 0 ]] && check_docker 2>/dev/null; then
    ylw "Trying legacy dicegroup docker (x86 emulation)..."
    if ! start_tentris_legacy_docker; then STARTED=0; fi
    [[ $? -eq 0 ]] && STARTED=1
  fi

  if [[ $STARTED -eq 0 ]]; then
    red "FAIL Tentris did not become ready."
    echo "Check: docker logs $CONTAINER_NAME  OR  cat tentris_server.log"
    exit 1
  fi
fi

TRIPLES=$(curl -sf "http://localhost:${PORT}/sparql" \
  -H "Content-Type: application/sparql-query" \
  -H "Accept: application/sparql-results+json" \
  --data "SELECT (COUNT(*) AS ?c) WHERE { ?s ?p ?o }" \
  | python3 -c "import sys,json; b=json.load(sys.stdin)['results']['bindings'][0]['c']; print(b['value'])")
echo "OK  Tentris triple count: $TRIPLES"

echo ""
echo "=== Running benchmark ($RUNS timed runs per query) ==="
export NEO4J_PASSWORD
export TENTRIS_URL="http://localhost:${PORT}"
python3 "$SCRIPT_DIR/benchmark_compare.py" \
  --runs-simple "$RUNS" \
  --runs-multihop "$RUNS_MULTIHOP" \
  --output "$SCRIPT_DIR/benchmark_results.json"

echo ""
grn "Done. Results: $SCRIPT_DIR/benchmark_results.json"
