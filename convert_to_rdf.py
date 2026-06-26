#!/usr/bin/env python3
"""
Convert Neo4j-style nodes.csv + edges.csv into RDF N-Triples for Tentris.

Property graph (one row per node/edge) → RDF (one triple per fact).

Usage:
  python3 convert_to_rdf.py --input ../kg_out/nikhil_test --output ../kg_out/rdf/pacer.nt
  python3 convert_to_rdf.py --input ../kg_out/nikhil_test --output pacer.nt --format turtle
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

from rdf_vocab import (
    CLASS_IRI,
    EDGE_PROP_PREDICATE,
    LABEL_MAP,
    NODE_PROP_PREDICATE,
    RDF,
    RDFS,
    REIFIED_FROM,
    REIFIED_REL,
    REIFIED_TO,
    REL_PREDICATE,
    XSD,
    node_uri,
    reified_uri,
)


def load_csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def person_to_label(props: dict) -> str:
    kind = (props.get("kind") or "").lower()
    return "Judge" if kind == "judge" else "Attorney"


def build_person_label_map(nodes: list[dict]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for row in nodes:
        if row["label"] == "Person":
            props = json.loads(row["props_json"])
            mapping[row["id"]] = person_to_label(props)
    return mapping


def resolve_label(csv_label: str, node_id: str, person_map: dict[str, str]) -> str:
    if csv_label == "Person":
        return person_map.get(node_id, "Attorney")
    return LABEL_MAP.get(csv_label, csv_label)


def nt_literal(value) -> str:
    if isinstance(value, bool):
        return f"\"{str(value).lower()}\"^^<{XSD}boolean>"
    if isinstance(value, int):
        return f"\"{value}\"^^<{XSD}integer>"
    if isinstance(value, float):
        return f"\"{value}\"^^<{XSD}double>"
    text = str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r")
    return f"\"{text}\"^^<{XSD}string>"


def emit_triple(subject: str, predicate: str, obj: str, *, obj_is_uri: bool = False) -> str:
    s = f"<{subject}>"
    p = f"<{predicate}>"
    o = f"<{obj}>" if obj_is_uri else obj
    return f"{s} {p} {o} .\n"


class TripleWriter:
    def __init__(self, path: Path, fmt: str) -> None:
        self.path = path
        self.fmt = fmt
        self.count = 0
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(path, "w", encoding="utf-8")
        if fmt == "turtle":
            self._fh.write("@prefix pacer: <http://scales-kg.org/pacer#> .\n")
            self._fh.write("@prefix rdf:   <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .\n")
            self._fh.write("@prefix rdfs:  <http://www.w3.org/2000/01/rdf-schema#> .\n\n")

    def write(self, subject: str, predicate: str, obj: str, *, obj_is_uri: bool = False) -> None:
        if self.fmt == "nt":
            self._fh.write(emit_triple(subject, predicate, obj, obj_is_uri=obj_is_uri))
        else:
            # Turtle: use prefixed names where possible
            subj = self._turtle_subj(subject)
            pred = self._turtle_pred(predicate)
            if obj_is_uri:
                obj_str = self._turtle_subj(obj)
            else:
                obj_str = obj  # already formatted literal for nt_literal output
            self._fh.write(f"{subj} {pred} {obj_str} .\n")
        self.count += 1

    def _turtle_subj(self, uri: str) -> str:
        if uri.startswith("http://scales-kg.org/id/"):
            return f"<{uri}>"
        return f"<{uri}>"

    def _turtle_pred(self, uri: str) -> str:
        if uri.startswith("http://scales-kg.org/pacer#"):
            return f"pacer:{uri.rsplit('#', 1)[-1]}"
        if uri == RDF + "type":
            return "rdf:type"
        if uri == RDFS + "label":
            return "rdfs:label"
        return f"<{uri}>"

    def close(self) -> None:
        self._fh.close()


def node_triples(writer: TripleWriter, label: str, node_id: str, props: dict) -> None:
    uri = node_uri(label, node_id)
    class_iri = CLASS_IRI.get(label)
    if not class_iri:
        return

    writer.write(uri, RDF + "type", class_iri, obj_is_uri=True)

    for key, val in props.items():
        if val is None or val == "":
            continue
        pred = NODE_PROP_PREDICATE.get(key)
        if not pred:
            continue
        writer.write(uri, pred, nt_literal(val))
        if key == "name":
            writer.write(uri, RDFS + "label", nt_literal(val))


def convert_nodes(writer: TripleWriter, nodes: list[dict], person_map: dict[str, str]) -> Counter:
    stats: Counter = Counter()
    for row in nodes:
        csv_label = row["label"]
        node_id = row["id"]
        props = json.loads(row["props_json"])

        if csv_label == "Person":
            label = person_map.get(node_id, person_to_label(props))
        else:
            label = LABEL_MAP.get(csv_label, csv_label)

        if csv_label == "Person" and node_id not in person_map:
            continue

        if label == "Court" and "code" not in props:
            props["code"] = node_id

        node_triples(writer, label, node_id, props)
        stats[label] += 1
    return stats


def convert_edges(
    writer: TripleWriter,
    edges: list[dict],
    person_map: dict[str, str],
) -> Counter:
    stats: Counter = Counter()
    reified_idx: Counter = Counter()

    for row in edges:
        rel = row["type"]
        from_label = resolve_label(row["from_label"], row["from_id"], person_map)
        to_label = resolve_label(row["to_label"], row["to_id"], person_map)
        from_uri = node_uri(from_label, row["from_id"])
        to_uri = node_uri(to_label, row["to_id"])
        props = json.loads(row["props_json"]) if row.get("props_json") else {}
        props = {k: v for k, v in props.items() if v is not None and v != ""}

        if rel in REL_PREDICATE:
            writer.write(from_uri, REL_PREDICATE[rel], to_uri, obj_is_uri=True)
            stats[rel] += 1
            continue

        if rel in REIFIED_REL:
            key = (rel, row["from_id"], row["to_id"])
            reified_idx[key] += 1
            link_class = REIFIED_REL[rel]
            link_uri = reified_uri(rel, from_label, row["from_id"], to_label, row["to_id"], reified_idx[key])

            writer.write(link_uri, RDF + "type", CLASS_IRI[link_class], obj_is_uri=True)
            writer.write(link_uri, REIFIED_FROM, from_uri, obj_is_uri=True)
            writer.write(link_uri, REIFIED_TO, to_uri, obj_is_uri=True)

            for pk, pv in props.items():
                pred = EDGE_PROP_PREDICATE.get(pk)
                if pred:
                    writer.write(link_uri, pred, nt_literal(pv))

            stats[rel] += 1
            continue

        stats[f"SKIP:{rel}"] += 1

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert property-graph CSVs to RDF for Tentris")
    parser.add_argument("--input", type=Path, required=True, help="Directory with nodes.csv + edges.csv")
    parser.add_argument("--output", type=Path, required=True, help="Output .nt or .ttl file")
    parser.add_argument(
        "--format",
        choices=("nt", "turtle", "auto"),
        default="auto",
        help="RDF serialization (default: infer from output extension)",
    )
    args = parser.parse_args()

    nodes_path = args.input / "nodes.csv"
    edges_path = args.input / "edges.csv"
    if not nodes_path.exists() or not edges_path.exists():
        raise SystemExit(f"Missing nodes.csv or edges.csv in {args.input}")

    fmt = args.format
    if fmt == "auto":
        fmt = "turtle" if args.output.suffix in (".ttl", ".turtle") else "nt"

    nodes = load_csv(nodes_path)
    edges = load_csv(edges_path)
    person_map = build_person_label_map(nodes)

    writer = TripleWriter(args.output, fmt)
    try:
        node_stats = convert_nodes(writer, nodes, person_map)
        edge_stats = convert_edges(writer, edges, person_map)
    finally:
        n_triples = writer.count
        writer.close()

    print(f"Wrote {n_triples:,} triples → {args.output}")
    print(f"  Nodes: {sum(node_stats.values()):,}")
    for label, n in sorted(node_stats.items()):
        print(f"    {label}: {n:,}")
    print(f"  Edges converted: {sum(v for k, v in edge_stats.items() if not k.startswith('SKIP')):,}")
    for rel, n in sorted(edge_stats.items()):
        print(f"    {rel}: {n:,}")
    print(f"  Expansion ratio: {n_triples / max(len(nodes), 1):.1f}x triples per CSV node row")


if __name__ == "__main__":
    main()
