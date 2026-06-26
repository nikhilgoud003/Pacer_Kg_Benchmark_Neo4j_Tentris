# Tentris vs Neo4j — PACER Knowledge Graph

Rebuild the same PACER graph in **Tentris** (RDF/SPARQL) for comparison with **Neo4j** (property graph/Cypher).

## Why this is not a drop-in swap

| Neo4j (property graph) | Tentris (RDF triple store) |
|------------------------|----------------------------|
| Node + label + properties on one object | Every property is its own triple |
| `(:Case)-[:ASSIGNED_JUDGE]->(:Judge)` | `?case pacer:assignedJudge ?judge` + `?judge rdfs:label "..."` |
| Cypher pattern matching | SPARQL triple patterns |
| `nodes.csv` / `edges.csv` load directly | Must convert to `.nt` / `.ttl` first |

**~10k CSV node rows → ~35–45k RDF triples** (each property becomes its own fact).

## Folder layout

```
tentris/
├── ontology.ttl           # RDF schema (classes + predicates)
├── rdf_vocab.py           # Shared URI / mapping constants
├── convert_to_rdf.py      # nodes.csv + edges.csv → N-Triples
├── sparql_queries.py      # SPARQL mirrors of graphrag_local.py
├── graphrag_sparql.py     # Interactive SPARQL CLI
├── benchmark_compare.py   # Neo4j vs Tentris timing
├── load_tentris.sh        # Convert + Docker load
└── README.md
```

## RDF modeling decisions

### Node labels → `rdf:type`
```
<http://scales-kg.org/id/case/akd%3B%3B3%3A16-cr-00074> rdf:type pacer:Case .
```

### Node properties → datatype triples
```
... pacer:hasCaseName "USA v. Harris" .
... pacer:hasCaseType "cr" .
... rdfs:label "USA v. Harris" .    # when name-like field exists
```

### Simple relationships (no edge props) → direct object properties
| Neo4j | RDF predicate |
|-------|---------------|
| `FILED_IN` | `pacer:filedIn` |
| `ASSIGNED_JUDGE` | `pacer:assignedJudge` |
| `REFERRED_TO` | `pacer:referredTo` |
| `LEAD_CASE` | `pacer:leadCase` |
| `APPEAL_IN` | `pacer:appealIn` |
| `HAS_DOCKET_ENTRY` | `pacer:hasDocketEntry` |

### Relationships with properties → reified links
Neo4j stores `role` on `HAS_PARTY` edges. RDF uses a link node:

```
_:link rdf:type pacer:PartyLink .
_:link pacer:from <case-uri> .
_:link pacer:to <party-uri> .
_:link pacer:hasRole "Defendant" .
```

Same pattern for `REPRESENTED_BY` → `pacer:CounselLink`, `RELATED_CASE` → `pacer:RelatedCaseLink`.

## Quick start (pilot 1,000 cases)

### 1. Convert CSV → RDF
```bash
cd pacer_kg/tentris
python3 convert_to_rdf.py \
  --input ../kg_out/nikhil_test \
  --output ../kg_out/rdf/pacer.nt
```

### 2. Load Tentris
**Simple (no license):**
```bash
chmod +x load_tentris.sh
./load_tentris.sh --simple
```

**Official image (needs `tentris-license.toml`):**
```bash
./load_tentris.sh
```

### 3. Query Tentris (SPARQL)
```bash
export TENTRIS_URL=http://localhost:9080
python3 graphrag_sparql.py --query judges
python3 graphrag_sparql.py   # interactive menu
```

### 4. Benchmark Neo4j vs Tentris
```bash
export NEO4J_PASSWORD='your-password'
export TENTRIS_URL=http://localhost:9080
python3 benchmark_compare.py --runs 5 --output benchmark_results.json
```

## Query mapping (Cypher → SPARQL)

| `graphrag_local.py` | `graphrag_sparql.py` |
|---------------------|----------------------|
| `judges` | Top judges by caseload |
| `court_stats` | Cases per court |
| `usa_cases` | USA plaintiff cases |
| `cocounsel` | Co-counsel pairs |
| `judge_attorney` | Judge–attorney pairs |
| `attorney_courts` | Cross-court attorneys |
| `related` | Related-case counts |
| `criminal` / `civil` | Filter by case type |
| `party_search <name>` | Party name search |

Example — top judges:

**Cypher (Neo4j):**
```cypher
MATCH (j:Judge)<-[:ASSIGNED_JUDGE]-(c:Case)
RETURN j.name AS judge, count(c) AS cases
ORDER BY cases DESC LIMIT 10
```

**SPARQL (Tentris):**
```sparql
PREFIX pacer: <http://scales-kg.org/pacer#>
SELECT ?judgeName (COUNT(DISTINCT ?case) AS ?cases) WHERE {
  ?case rdf:type pacer:Case .
  ?case pacer:assignedJudge ?judge .
  ?judge rdfs:label ?judgeName .
}
GROUP BY ?judgeName
ORDER BY DESC(?cases) LIMIT 10
```

## Scaling to 1.2M cases

1. Run `build_kg_extract.py` + `convert_to_rdf.py` on full CSV output (streaming handles large files).
2. Use Tentris **offline loader** for large `.nt` files (faster than HTTP INSERT):
   ```bash
   tentris load < ../kg_out/rdf/pacer_full.nt
   ```
3. Re-run `benchmark_compare.py` on the same query set.

## What to report in your comparison

| Metric | Neo4j | Tentris |
|--------|-------|---------|
| Load time | `load_neo4j.py` wall clock | `convert_to_rdf.py` + Tentris load |
| Storage | Neo4j store size | `/data` volume size |
| Query latency | `benchmark_compare.py` | same script |
| Expressiveness | Cypher path patterns | SPARQL triple joins |
| Model fit | Natural for PACER JSON | Requires RDF explosion + reification |

## Notes

- **Row counts may differ slightly** between engines when edge reification changes join semantics; compare top-k results manually.
- **Tentris** excels at analytical SPARQL over large triple sets; **Neo4j** excels at traversals and property-graph patterns — your benchmark on real PACER queries is the right test.
- Re-convert after ER merges: point `--input` at post-ER CSV or re-export from Neo4j if you merge in-graph only.
