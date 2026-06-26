#!/usr/bin/env python3
"""
SPARQL query CLI — mirrors graphrag_local.py for Tentris.

Usage:
  export TENTRIS_URL=http://localhost:9080
  python3 graphrag_sparql.py
  python3 graphrag_sparql.py --query judges
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

from sparql_queries import QUERIES

DEFAULT_URL = os.environ.get("TENTRIS_URL", "http://localhost:9080")


def sparql_select(url: str, query: str) -> list[dict]:
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
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as e:
        raise SystemExit(f"Tentris not reachable at {endpoint}: {e}") from e

    rows: list[dict] = []
    for binding in payload.get("results", {}).get("bindings", []):
        row = {}
        for var, val in binding.items():
            row[var] = val.get("value", "")
        rows.append(row)
    return rows


def print_table(rows: list[dict]) -> None:
    if not rows:
        print("(no results)")
        return
    columns = list(rows[0].keys())
    widths = {col: len(col) for col in columns}
    str_rows: list[list[str]] = []
    for row in rows:
        str_row = [str(row.get(col, "")) for col in columns]
        str_rows.append(str_row)
        for col, cell in zip(columns, str_row):
            widths[col] = max(widths[col], len(cell))

    header = " | ".join(col.ljust(widths[col]) for col in columns)
    sep = "-+-".join("-" * widths[col] for col in columns)
    print(header)
    print(sep)
    for str_row in str_rows:
        print(" | ".join(cell.ljust(widths[col]) for cell, col in zip(str_row, columns)))


def run_query(url: str, name: str, arg: str | None = None) -> None:
    spec = QUERIES.get(name)
    if not spec:
        print(f"Unknown query: {name}")
        return

    query = spec["sparql"]
    if spec.get("needs_arg"):
        if not arg:
            print("Usage: party_search <name>")
            return
        safe = arg.replace("\\", "\\\\").replace('"', '\\"')
        query = query.replace("?name", f'"{safe}"')

    print(f"\n=== {name}: {spec['description']} ===\n")
    rows = sparql_select(url, query)
    print_table(rows)
    print(f"\n({len(rows)} rows)")


def print_help() -> None:
    print("\nAvailable SPARQL queries (Tentris):")
    for name, spec in QUERIES.items():
        if name == "triple_count":
            continue
        extra = " <name>" if spec.get("needs_arg") else ""
        print(f"  {name}{extra:<12} — {spec['description']}")
    print("  triple_count  — total RDF triple count")
    print("  help          — show this list")
    print("  quit          — exit\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="PACER KG — Tentris SPARQL CLI")
    parser.add_argument("--url", default=DEFAULT_URL, help="Tentris base URL")
    parser.add_argument("--query", "-q", help="Run one query and exit")
    parser.add_argument("arg", nargs="?", help="Argument for party_search")
    args = parser.parse_args()

    if args.query:
        run_query(args.url, args.query, args.arg)
        return

    print("PACER Knowledge Graph — Tentris SPARQL")
    print(f"Endpoint: {args.url}/sparql")
    print_help()

    while True:
        try:
            raw = input("sparql> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not raw:
            continue
        if raw.lower() in ("quit", "exit", "q"):
            break
        if raw.lower() == "help":
            print_help()
            continue

        parts = raw.split(maxsplit=1)
        qname = parts[0].lower()
        qarg = parts[1] if len(parts) > 1 else None
        run_query(args.url, qname, qarg)

    print("Goodbye.")


if __name__ == "__main__":
    main()
