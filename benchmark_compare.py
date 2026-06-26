#!/usr/bin/env python3
"""
Benchmark Neo4j (Cypher) vs Tentris (SPARQL) on the same logical queries.

Reports mean ± standard deviation. Simple queries default to 25 timed runs;
multi-hop queries default to 10 (each run is expensive).

Usage:
  export NEO4J_PASSWORD='...'
  export TENTRIS_URL=http://localhost:9080
  python3 benchmark_compare.py
  python3 benchmark_compare.py --runs-simple 30 --runs-multihop 10 --output results.json
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import time
import urllib.error
import urllib.request
from pathlib import Path

from neo4j import GraphDatabase

from sparql_queries import CYPHER_QUERIES, QUERIES

DEFAULT_NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
DEFAULT_NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
DEFAULT_NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "")
DEFAULT_TENTRIS_URL = os.environ.get("TENTRIS_URL", "http://localhost:9080")

BENCHMARK_QUERIES = [
    "judges",
    "court_stats",
    "criminal",
    "civil",
    "related",
    "usa_cases",
    "cocounsel",
    "judge_attorney",
    "attorney_courts",
]

# Simple queries: sub-15 ms — need more runs to beat laptop noise
SIMPLE_QUERIES = frozenset({
    "judges",
    "court_stats",
    "criminal",
    "civil",
    "related",
    "usa_cases",
})

MULTIHOP_QUERIES = frozenset({
    "cocounsel",
    "judge_attorney",
    "attorney_courts",
})


def stdev(values: list[float]) -> float:
    return statistics.stdev(values) if len(values) > 1 else 0.0


def fmt_ms(avg: float, sd: float) -> str:
    return f"{avg:.1f} ± {sd:.1f}"


def run_cypher(driver, name: str, party_name: str | None = None) -> tuple[list[dict], float]:
    cypher = CYPHER_QUERIES[name]
    params = {}
    if name == "party_search":
        params["name"] = party_name or "harris"

    t0 = time.perf_counter()
    with driver.session() as session:
        result = session.run(cypher, **params)
        rows = [dict(r) for r in result]
    elapsed_ms = (time.perf_counter() - t0) * 1000
    return rows, elapsed_ms


def run_sparql(url: str, name: str, party_name: str | None = None) -> tuple[list[dict], float, str | None]:
    query = QUERIES[name]["sparql"]
    if name == "party_search":
        safe = (party_name or "harris").replace("\\", "\\\\").replace('"', '\\"')
        query = query.replace("?name", f'"{safe}"')

    endpoint = url.rstrip("/") + "/sparql"
    data = query.encode("utf-8")
    req = urllib.request.Request(
        endpoint,
        data=data,
        headers={
            "Content-Type": "application/sparql-query",
            "Accept": "application/sparql-results+json",
        },
        method="POST",
    )

    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:500]
        elapsed_ms = (time.perf_counter() - t0) * 1000
        return [], elapsed_ms, f"HTTP {e.code}: {body}"
    except urllib.error.URLError as e:
        elapsed_ms = (time.perf_counter() - t0) * 1000
        return [], elapsed_ms, str(e)
    elapsed_ms = (time.perf_counter() - t0) * 1000

    rows: list[dict] = []
    for binding in payload.get("results", {}).get("bindings", []):
        row = {var: val.get("value", "") for var, val in binding.items()}
        rows.append(row)
    return rows, elapsed_ms, None


def runs_for_query(qname: str, runs_simple: int, runs_multihop: int, runs_override: int | None) -> int:
    if runs_override is not None:
        return runs_override
    if qname in MULTIHOP_QUERIES:
        return runs_multihop
    return runs_simple


def main() -> None:
    parser = argparse.ArgumentParser(description="Neo4j vs Tentris benchmark")
    parser.add_argument("--neo4j-uri", default=DEFAULT_NEO4J_URI)
    parser.add_argument("--neo4j-user", default=DEFAULT_NEO4J_USER)
    parser.add_argument("--neo4j-password", default=DEFAULT_NEO4J_PASSWORD)
    parser.add_argument("--tentris-url", default=DEFAULT_TENTRIS_URL)
    parser.add_argument(
        "--runs-simple",
        type=int,
        default=25,
        help="Timed runs for simple queries (default: 25)",
    )
    parser.add_argument(
        "--runs-multihop",
        type=int,
        default=10,
        help="Timed runs for multi-hop queries (default: 10)",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=None,
        help="Override: same run count for all queries (legacy flag)",
    )
    parser.add_argument("--party-name", default="harris")
    parser.add_argument("--output", type=Path, help="Write JSON results")
    parser.add_argument("--queries", nargs="*", default=BENCHMARK_QUERIES)
    args = parser.parse_args()

    if not args.neo4j_password:
        raise SystemExit("Set NEO4J_PASSWORD or pass --neo4j-password")

    driver = GraphDatabase.driver(args.neo4j_uri, auth=(args.neo4j_user, args.neo4j_password))

    results: list[dict] = []
    print(f"{'Query':<18} {'Neo4j (ms)':>16} {'Tentris (ms)':>16} {'Runs':>5} {'Rows':>9} {'Match':>6}")
    print("-" * 82)

    for qname in args.queries:
        if qname not in CYPHER_QUERIES or qname not in QUERIES:
            print(f"SKIP unknown query: {qname}")
            continue

        n_runs = runs_for_query(qname, args.runs_simple, args.runs_multihop, args.runs)

        try:
            neo_rows, _ = run_cypher(driver, qname)
            sparql_rows, _, sparql_err = run_sparql(args.tentris_url, qname)
            if sparql_err:
                print(f"{qname:<18} {'—':>16} {'ERROR':>16} {n_runs:>5} {len(neo_rows):>9} {'—':>6}")
                print(f"  Tentris error: {sparql_err[:120]}")
                results.append({
                    "query": qname,
                    "description": QUERIES[qname]["description"],
                    "timed_runs": n_runs,
                    "neo4j_rows": len(neo_rows),
                    "tentris_error": sparql_err,
                })
                continue

            neo_times: list[float] = []
            sparql_times: list[float] = []
            for _ in range(n_runs):
                _, t = run_cypher(driver, qname)
                neo_times.append(t)
                _, t, err = run_sparql(args.tentris_url, qname)
                if err:
                    raise RuntimeError(err)
                sparql_times.append(t)

            neo_avg = statistics.mean(neo_times)
            sparql_avg = statistics.mean(sparql_times)
            neo_sd = stdev(neo_times)
            sparql_sd = stdev(sparql_times)
            row_match = len(neo_rows) == len(sparql_rows)

            # Overlap of 95% CI (mean ± 1.96*SE) — rough significance hint
            neo_se = neo_sd / (len(neo_times) ** 0.5) if neo_times else 0
            sparql_se = sparql_sd / (len(sparql_times) ** 0.5) if sparql_times else 0
            ci_overlap = abs(neo_avg - sparql_avg) <= 1.96 * (neo_se + sparql_se)

            entry = {
                "query": qname,
                "description": QUERIES[qname]["description"],
                "query_class": "multihop" if qname in MULTIHOP_QUERIES else "simple",
                "timed_runs": n_runs,
                "neo4j_ms_avg": round(neo_avg, 2),
                "neo4j_ms_std": round(neo_sd, 2),
                "tentris_ms_avg": round(sparql_avg, 2),
                "tentris_ms_std": round(sparql_sd, 2),
                "neo4j_rows": len(neo_rows),
                "tentris_rows": len(sparql_rows),
                "row_count_match": row_match,
                "confidence_intervals_overlap_95pct": ci_overlap,
                "neo4j_faster": neo_avg < sparql_avg,
            }
            results.append(entry)

            match_str = "yes" if row_match else "NO"
            rows_str = f"{len(neo_rows)}/{len(sparql_rows)}"
            print(
                f"{qname:<18} {fmt_ms(neo_avg, neo_sd):>16} {fmt_ms(sparql_avg, sparql_sd):>16} "
                f"{n_runs:>5} {rows_str:>9} {match_str:>6}"
            )
            if ci_overlap and qname in SIMPLE_QUERIES:
                print(f"  ⚠ margins overlap at 95% CI — treat as noise unless gap >> std dev")
        except Exception as e:
            print(f"{qname:<18} {'ERROR':>16} {'—':>16} {'—':>5} {'—':>9} {'—':>6}")
            print(f"  {e}")
            results.append({"query": qname, "error": str(e)})

    driver.close()

    print(
        "\n--- Methodology notes ---"
        "\n• Row counts match partly BY CONSTRUCTION: Cypher and SPARQL pairs share the same LIMIT"
        " clauses (10/20/25/30/50), so equal counts are necessary but not sufficient for correctness."
        "\n• For semantic validation, compare top-k result values manually (not just row count)."
        "\n• Simple-query margins under ~2 ms with overlapping 95% CIs should be treated as noise."
        "\n• Multi-hop gaps (100 ms+) are large enough to be meaningful on this hardware."
    )

    if args.output:
        meta = {
            "runs_simple_default": args.runs_simple,
            "runs_multihop_default": args.runs_multihop,
            "methodology": (
                "Mean ± sample std dev over timed runs after one warmup. "
                "Row-count equality is partly guaranteed by shared LIMIT clauses."
            ),
        }
        payload = {"meta": meta, "results": results}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        print(f"\nWrote {args.output}")


if __name__ == "__main__":
    main()
