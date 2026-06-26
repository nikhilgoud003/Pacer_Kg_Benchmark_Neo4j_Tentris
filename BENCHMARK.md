# PACER Knowledge Graph — Neo4j vs Tentris Benchmark

**Project:** SCALES PACER Legal Knowledge Graph  
**Dataset:** Pilot run — 1,000 cases (86 courts)  
**Date:** June 2026  
**Author:** Nikhil Goudyeminedi  

---

## 1. Executive Summary

This document describes a **head-to-head benchmark** between two graph databases on the **same PACER legal knowledge graph**:

| Database | Model | Query Language | Pilot Size |
|----------|-------|----------------|------------|
| **Neo4j** | Property graph (nodes + labeled edges) | Cypher | 10,416 nodes |
| **Tentris** | RDF triple store (subject–predicate–object) | SPARQL | 162,338 triples |

**Main result (qualitative):** On multi-hop traversals (party → attorney → judge → court), **Neo4j is clearly faster** (4–9×, hundreds of ms — signal exceeds measurement noise). On simple aggregations, **Tentris shows a slight edge in preliminary runs**, but margins of 1–2 ms are **within laptop measurement noise** and must be confirmed with mean ± std dev over ≥25 runs (see Section 8).

**Important limitations (read before citing numbers):**
- Row-count matches (10/10, 50/50, etc.) are **partly guaranteed by construction** — every Cypher/SPARQL pair uses the **same `LIMIT`**, so equal counts are necessary but **not sufficient** proof of semantic correctness.
- Early runs used only **5 timed iterations**; sub-10 ms differences are **not statistically reliable** without standard deviation and more runs.
- **Multi-hop results (656 ms vs 2,874 ms)** are the most trustworthy signal in this benchmark.

---

## 2. Goal (Top-Down View)

```
┌─────────────────────────────────────────────────────────────────┐
│  GOAL: Compare Neo4j vs Tentris on the SAME legal knowledge     │
│        graph using the SAME logical queries                     │
└─────────────────────────────────────────────────────────────────┘
                              │
          ┌───────────────────┴───────────────────┐
          ▼                                       ▼
┌─────────────────────┐               ┌─────────────────────┐
│  Neo4j path         │               │  Tentris path       │
│  JSON → CSV → Neo4j │               │  JSON → CSV → RDF   │
│  Cypher queries     │               │  SPARQL queries     │
└─────────────────────┘               └─────────────────────┘
          │                                       │
          └───────────────────┬───────────────────┘
                              ▼
              ┌───────────────────────────────┐
              │  benchmark_compare.py         │
              │  Same 9 queries, timed runs   │
              │  Compare latency + row counts │
              └───────────────────────────────┘
```

**Why this is not a simple database swap:** Neo4j stores a *property graph* (one node with many properties). Tentris stores *RDF triples* (every fact is exactly three parts: subject, predicate, object). The data must be **re-modeled**, and queries must be **rewritten** in SPARQL.

---

## 3. What Was Done (Step by Step)

### Phase A — Build graph in Neo4j (already completed before benchmark)

| Step | Script | Output |
|------|--------|--------|
| 1. Extract JSON → CSV | `../build_kg_extract.py` | `nodes.csv`, `edges.csv` |
| 2. Load into Neo4j | `../load_neo4j.py` | 10,416 nodes in Docker `neo4j-kg` |
| 3. Entity resolution | `../er_cleanup.py`, Ditto pipeline | Merged duplicate attorneys/judges |

### Phase B — Rebuild same graph in Tentris (this folder)

| Step | Script | Output |
|------|--------|--------|
| 1. Convert CSV → RDF | `convert_to_rdf.py` | `pacer.nt` (N-Triples) |
| 2. Define ontology | `ontology.ttl`, `rdf_vocab.py` | Schema (classes + predicates) |
| 3. Write SPARQL equivalents | `sparql_queries.py` | 9 queries mirroring Neo4j |
| 4. Start Tentris server | `start_tentris_docker.sh` | SPARQL endpoint on port 9080 |
| 5. Run benchmark | `benchmark_compare.py` | Timing table + `benchmark_results.json` |

### Phase C — Compare results

- Run each query on **both** databases
- Measure **wall-clock latency** (milliseconds), report **mean ± standard deviation**
- **25 timed runs** for simple queries; **10 runs** for expensive multi-hop queries
- Check **row-count match** (weak correctness signal — see Section 8.0)
- Flag when **95% confidence intervals overlap** (difference may be noise)

---

## 4. Data Model Comparison

### Neo4j (Property Graph)

One relationship, properties on nodes:

```cypher
(:Case {ucid: "paed;;2:09-cv-93363"})-[:ASSIGNED_JUDGE]->(:Judge {name: "Eduardo C. Robreno"})
```

### Tentris (RDF Triples)

Same fact becomes **multiple triples**:

```turtle
<case:paed_2_09_cv_93363>  rdf:type           pacer:Case .
<case:paed_2_09_cv_93363>  pacer:hasUcid      "paed;;2:09-cv-93363" .
<case:paed_2_09_cv_93363>  pacer:assignedJudge <judge:eduardo_c_robreno> .
<judge:eduardo_c_robreno>  rdfs:label         "Eduardo C. Robreno" .
<judge:eduardo_c_robreno>  rdf:type           pacer:Judge .
```

### Edge properties → Reified link nodes

Neo4j stores `role` on the `HAS_PARTY` **edge**. RDF has no edge properties, so we use a **link node**:

```turtle
_:link1  rdf:type        pacer:PartyLink .
_:link1  pacer:from      <case:...> .
_:link1  pacer:to        <party:...> .
_:link1  pacer:hasRole   "Defendant" .
```

This is why multi-hop SPARQL queries are longer and slower than equivalent Cypher.

---

## 5. Conversion Algorithm (`convert_to_rdf.py`)

**Input:** `nodes.csv` + `edges.csv` (property-graph format)  
**Output:** `pacer.nt` (N-Triples, one triple per line)

### Algorithm (top-down)

```
FOR each row in nodes.csv:
    1. Resolve label (Person → Judge/Attorney via kind property)
    2. Emit:  <uri> rdf:type <Class>
    3. FOR each non-null property in props_json:
           Emit:  <uri> <predicate> <literal>
           IF property is "name":
               Emit:  <uri> rdfs:label <literal>

FOR each row in edges.csv:
    IF edge has NO properties (FILED_IN, ASSIGNED_JUDGE, ...):
        Emit:  <from_uri> <predicate> <to_uri>     # direct triple
    ELSE (HAS_PARTY, REPRESENTED_BY, RELATED_CASE):
        Create reified link node:
        Emit:  <link_uri> rdf:type <LinkClass>
        Emit:  <link_uri> pacer:from <from_uri>
        Emit:  <link_uri> pacer:to   <to_uri>
        FOR each edge property:
            Emit:  <link_uri> <pred> <literal>
```

### URI generation (`rdf_vocab.py`)

- **Namespace:** `http://scales-kg.org/pacer#` (predicates/classes)
- **Instances:** `http://scales-kg.org/id/{label}/{url-encoded-id}`
- Example: `akd;;3:16-cr-00074` → `http://scales-kg.org/id/case/akd%3B%3B3%3A16-cr-00074`

### Expansion ratio (pilot)

| Metric | Count |
|--------|------:|
| CSV node rows | 10,493 |
| RDF triples | 162,338 |
| **Expansion** | **~15.5×** triples per node row |

---

## 6. Query Equivalence Approach (`sparql_queries.py`)

Each query in `graphrag_local.py` (Cypher) has a **logical twin** in SPARQL.

### Example — Top judges by caseload

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

### Nine benchmark queries

| # | Query name | What it tests |
|---|------------|---------------|
| 1 | `judges` | Simple aggregation (COUNT + GROUP BY) |
| 2 | `court_stats` | Join Case → Court, aggregate |
| 3 | `criminal` | Filter by property (`case_type = cr`) |
| 4 | `civil` | Filter by property (`case_type = cv`) |
| 5 | `related` | Count related-case links |
| 6 | `usa_cases` | Multi-pattern filter (org + role) |
| 7 | `cocounsel` | **Multi-hop** party → 2 attorneys |
| 8 | `judge_attorney` | **Multi-hop** case → judge + party → attorney |
| 9 | `attorney_courts` | **Multi-hop** attorney → party → case → court |

---

## 7. Benchmark Methodology (`benchmark_compare.py`)

### Approach

1. **Warm-up run** — one execution per query (not timed) to load caches
2. **Timed runs**
   - **Simple queries** (`judges`, `court_stats`, `criminal`, `civil`, `related`, `usa_cases`): **25 runs** (default)
   - **Multi-hop queries** (`cocounsel`, `judge_attorney`, `attorney_courts`): **10 runs** (default; each run is slow)
3. **Metrics reported**
   - Mean latency (ms)
   - Sample standard deviation (ms)
   - Printed as `mean ± std` (e.g. `5.2 ± 0.8`)
   - Whether **95% confidence intervals overlap** (rough noise check for simple queries)
4. **Correctness check (weak)** — compare row counts; see Section 8.0 for caveats
5. **Transport** — Neo4j via Bolt driver; Tentris via HTTP POST to `/sparql`

### Statistical honesty

| Claim type | Reliable on this pilot? | Why |
|------------|-------------------------|-----|
| Multi-hop Neo4j advantage (100–2500 ms gaps) | **Yes** | Gap ≫ std dev and laptop jitter |
| Simple-query Tentris advantage (1–3 ms gaps) | **Uncertain** | Often within noise; need ± std and 25+ runs |
| Identical row counts | **Partially by design** | Shared `LIMIT` clauses force same cap |

### Environment

| Component | Setting |
|-----------|---------|
| Machine | MacBook Air (Apple Silicon, arm64) |
| Neo4j | Docker `neo4j-kg`, bolt://localhost:7687 |
| Tentris | Docker `ghcr.io/tentris/tentris:latest`, port 9080 |
| License | `tentris-license.toml` (free from tentris.io) |
| Password | `NEO4J_PASSWORD=Nikhil2001` |

### Fairness notes

- Same pilot dataset (post-ER graph)
- Same logical questions, different query languages
- Latency includes network (Bolt/HTTP) overhead — acceptable for relative comparison
- Tentris pays extra cost for RDF reification on relationship-heavy queries

---

## 8. Results

### 8.0 Limitations — read before citing numbers

#### Row-count matches are partly by construction

Every benchmark query pair (Cypher + SPARQL) uses the **same `LIMIT`**:

| Query | LIMIT | Why counts look "perfect" |
|-------|------:|---------------------------|
| `judges` | 10 | Both engines return at most 10 rows |
| `related` | 20 | Both capped at 20 |
| `cocounsel`, `attorney_courts` | 25 | Both capped at 25 |
| `judge_attorney` | 30 | Both capped at 30 |
| `criminal`, `civil`, `usa_cases` | 50 | Both capped at 50 |
| `court_stats` | none | 86 courts in pilot → both return 86 |

Matching row counts confirm queries didn't **crash or over-fetch**, but they do **not** independently prove the **same entities** were returned. For semantic validation, manually compare top-k values (e.g. top judge name and case count).

#### Single-digit millisecond gaps may be noise

On a MacBook Air with 1,000 cases, simple queries finish in **2–11 ms**. With only 5 runs, a "1.3× faster" claim (e.g. 5.2 ms vs 4.0 ms) can be **within normal jitter**. The updated `benchmark_compare.py` reports **mean ± std dev** and flags overlapping 95% CIs.

#### What is trustworthy

| Result tier | Example | Trust level |
|-------------|---------|-------------|
| **Strong signal** | `cocounsel`: 656 ms vs 2,874 ms | High — gap is 4.4×, >> noise |
| **Moderate signal** | `judge_attorney`: 11.5 ms vs 99.8 ms | High — 8.7× gap |
| **Weak signal** | `judges`: 5.2 ms vs 4.0 ms | Low — re-run with 25+ runs ± std |

### 8.1 Preliminary results (5 timed runs — superseded)

*These were the first benchmark runs. Kept for reference; do not cite without caveats above.*

| Query | Neo4j (ms) | Tentris (ms) | Rows | Match |
|-------|----------:|-------------:|------|:-----:|
| `judges` | 5.2 | 4.0 | 10/10 | yes |
| `court_stats` | 3.8 | 2.5 | 86/86 | yes |
| `criminal` | 4.2 | 2.9 | 50/50 | yes |
| `civil` | 3.7 | 5.0 | 50/50 | yes |
| `related` | 2.5 | 2.0 | 20/20 | yes |
| `usa_cases` | 6.1 | 10.7 | 50/50 | yes |
| `cocounsel` | **656.3** | 2,874.4 | 25/25 | yes |
| `judge_attorney` | **11.5** | 99.8 | 30/30 | yes |
| `attorney_courts` | **28.9** | 213.0 | 25/25 | yes |

### 8.2 Authoritative results format (25 simple / 10 multi-hop runs)

Re-run with the updated script to populate `benchmark_results.json`:

```bash
export NEO4J_PASSWORD='Nikhil2001'
python3 benchmark_compare.py \
  --runs-simple 25 \
  --runs-multihop 10 \
  --output benchmark_results.json
```

**Expected output columns:**

| Query | Neo4j (mean ± std) | Tentris (mean ± std) | Runs | Rows | CI overlap? |
|-------|-------------------|---------------------|------|------|-------------|
| `judges` | e.g. 5.1 ± 0.7 | e.g. 4.2 ± 0.6 | 25 | 10/10 | maybe |
| `cocounsel` | e.g. 650 ± 40 | e.g. 2800 ± 200 | 10 | 25/25 | no |

*Replace this placeholder table with values from your `benchmark_results.json` after re-running.*

### 8.3 Score summary (from preliminary runs — qualitative)

| Category | Neo4j faster (preliminary) | Tentris faster (preliminary) | Confidence |
|----------|:--------------------------:|:----------------------------:|:----------:|
| Simple aggregation / filter (queries 1–6) | 2 | 4 | **Low** — margins within noise |
| Multi-hop traversal (queries 7–9) | **3** | 0 | **High** — 4–9× gaps |
| Row counts match | 9/9 | 9/9 | **By construction** (shared LIMIT) |

### 8.4 Latency chart (visual)

```
Simple queries (ms)          Multi-hop queries (ms, log scale)
Neo4j  ████  ~4-6            Neo4j  ████████████████  29-656
Tentris ███  ~2-11           Tentris ████████████████████████████████████  99-2874
         judges                      cocounsel / judge_attorney / attorney_courts
         court_stats
```

---

## 9. Analysis & Conclusions

### Simple queries — tentative Tentris edge, not definitive

Preliminary runs suggest Tentris may be slightly faster on aggregations (`COUNT`, `GROUP BY`, `FILTER`), but **1–3 ms differences with 5 runs are not statistically reliable**. Treat as **directional only** until confirmed with mean ± std over 25 runs. If 95% CIs overlap, state: *"no significant difference on this hardware at pilot scale."*

### Multi-hop queries — strong Neo4j advantage (trustworthy)

This is the **most credible finding** in the benchmark:

- Cypher path patterns: `(c)-[:HAS_PARTY]->(p)-[:REPRESENTED_BY]->(a)` — one line
- SPARQL requires joining **reified link nodes** (`PartyLink`, `CounselLink`) — many triple patterns
- `cocounsel` at **656 ms vs 2,874 ms** (4.4×) is far above measurement noise
- Matches known literature: **property graphs favor traversal; RDF triple stores pay a join tax on reified edges**

### Modeling overhead

| Task | Neo4j | Tentris |
|------|-------|---------|
| Load data | Direct from CSV | Extra conversion step (+15× triples) |
| Edge properties | On relationship | Reified link nodes |
| Query writing | Shorter Cypher | Longer SPARQL |
| Mac setup | Docker works out of box | Official Docker + free license |

### Recommendation for PACER pipeline

| Use case | Better choice |
|----------|---------------|
| JSON → graph extraction | **Neo4j** (natural property-graph fit) |
| Entity resolution (Ditto merges) | **Neo4j** (MERGE on node properties) |
| GraphRAG / path traversals | **Neo4j** (Cypher path patterns) |
| Aggregate SPARQL on existing RDF | **Tentris** (if data already in RDF) |
| Standards-based linked data / ontology | **Tentris** (RDF/OWL ecosystem) |

---

## 10. File Reference (`pacer_kg/tentris/`)

### Core pipeline files

| File | Purpose |
|------|---------|
| **`rdf_vocab.py`** | Shared constants: namespace URIs, label maps, predicate names, `node_uri()` helper. Used by converter and documents the schema. |
| **`ontology.ttl`** | RDF/OWL ontology defining classes (`pacer:Case`, `pacer:Judge`) and properties (`pacer:assignedJudge`, `pacer:filedIn`). Human-readable schema reference. |
| **`convert_to_rdf.py`** | **Main converter.** Reads `nodes.csv` + `edges.csv`, explodes each property into triples, reifies edges with properties. Outputs `.nt` or `.ttl`. |
| **`sparql_queries.py`** | **Query library.** Contains all 9 SPARQL queries + matching Cypher copies used by the benchmark. Single source of truth for query equivalence. |

### Server & loading scripts

| File | Purpose |
|------|---------|
| **`start_tentris_docker.sh`** | Starts official `ghcr.io/tentris/tentris` Docker image with license + RDF file. **Used on Mac (recommended).** |
| **`start_tentris_native.sh`** | Loads RDF via `tentris load`, then `tentris serve`. Native ARM binary (needs `brew install gcc@14`). |
| **`load_tentris.sh`** | Older loader script (simple dicegroup image or official image). |
| **`run_benchmark.sh`** | All-in-one: checks Neo4j + Tentris, converts RDF if needed, runs benchmark. |
| **`tentris-license.toml`** | Free Tentris license (from tentris.io). Required for official Tentris. |

### Benchmark & query tools

| File | Purpose |
|------|---------|
| **`benchmark_compare.py`** | **Main benchmark script.** Runs same queries on Neo4j and Tentris; reports **mean ± std dev**; 25 runs (simple) / 10 runs (multi-hop); flags CI overlap; writes JSON with metadata. |
| **`graphrag_sparql.py`** | Interactive SPARQL CLI (like `graphrag_local.py` for Neo4j). Manual query testing. |
| **`benchmark_results.json`** | Machine-readable output from last benchmark run. |

### Supporting files

| File | Purpose |
|------|---------|
| **`README.md`** | Quick-start guide for the Tentris folder. |
| **`BENCHMARK.md`** | This document — full benchmark documentation. |
| **`requirements.txt`** | Python deps: `neo4j`, `requests`. |

### Input / output files (outside `tentris/`)

| Path | Purpose |
|------|---------|
| `../kg_out/nikhil_test/nodes.csv` | Neo4j node export (10,493 rows) |
| `../kg_out/nikhil_test/edges.csv` | Neo4j edge export (21,378 rows) |
| `../kg_out/rdf/pacer.nt` | Converted RDF (162,338 triples, ~28 MB) |
| `../load_neo4j.py` | Loads CSV into Neo4j |
| `../graphrag_local.py` | Neo4j Cypher query menu (benchmark reference) |

---

## 11. Commands Cheat Sheet

### Prerequisites

```bash
# Start Neo4j
docker start neo4j-kg

# Verify Neo4j
export NEO4J_PASSWORD='Nikhil2001'
python3 -c "from neo4j import GraphDatabase; d=GraphDatabase.driver('bolt://localhost:7687',auth=('neo4j','$NEO4J_PASSWORD')); print(d.session().run('MATCH (n) RETURN count(n)').single())"
```

### Step 1 — Convert CSV to RDF (one time)

```bash
cd /Users/nikhilgoudyeminedi/Desktop/SCALES/nikhil_test/pacer_kg/tentris

python3 convert_to_rdf.py \
  --input ../kg_out/nikhil_test \
  --output ../kg_out/rdf/pacer.nt \
  --format nt
```

### Step 2 — Start Tentris

```bash
# Official Docker (recommended on Mac)
./start_tentris_docker.sh

# Or native binary (if tentris CLI installed)
./start_tentris_native.sh --bg
```

### Step 3 — Run full benchmark

```bash
export NEO4J_PASSWORD='Nikhil2001'
export TENTRIS_URL=http://localhost:9080

python3 benchmark_compare.py \
  --runs-simple 25 \
  --runs-multihop 10 \
  --output benchmark_results.json
```

### Step 4 — Run single query (manual test)

```bash
# Tentris SPARQL
python3 graphrag_sparql.py --query judges

# Neo4j Cypher
cd .. && python3 graphrag_local.py
# then type: judges
```

### Step 5 — All-in-one benchmark script

```bash
export NEO4J_PASSWORD='Nikhil2001'
./run_benchmark.sh
```

### Sanity check — triple count in Tentris

```bash
curl -s http://localhost:9080/sparql \
  -H "Content-Type: application/sparql-query" \
  -H "Accept: application/sparql-results+json" \
  --data "SELECT (COUNT(*) AS ?c) WHERE { ?s ?p ?o }"
# Expected: ~162338
```

---

## 12. Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| `dicegroup/tentris_server` hangs / empty logs | amd64-only image on Apple Silicon | Use `./start_tentris_docker.sh` (official image) |
| `permission denied` on docker.sock | Docker Desktop not running | Open Docker Desktop |
| `Connection refused` on 7687 | Neo4j not started | `docker start neo4j-kg` |
| HTTP 400 on SPARQL query | Tentris rejects certain SPARQL syntax | See fixes in `sparql_queries.py` (no triple patterns inside FILTER) |
| `libgcc_s` missing for native binary | Tentris needs gcc@14 | `brew install gcc@14` |
| Missing license | Tentris requires free license | Copy to `tentris-license.toml` or `~/.config/tentris-license.toml` |

---

## 13. One-Paragraph Conclusion (for report)

> On a 1,000-case PACER pilot graph (10,416 Neo4j nodes vs 162,338 RDF triples), **Neo4j showed a clear and trustworthy advantage on multi-hop traversals** (party–attorney–judge patterns: 4–9× faster, hundreds of ms gaps). Simple aggregation queries showed **small Tentris margins (1–3 ms) that are likely within laptop measurement noise** and require mean ± standard deviation over 25+ runs to confirm. Row-count equality across all nine query pairs is **partly guaranteed by shared LIMIT clauses**, not independent proof of semantic equivalence. Overall, Neo4j is the better fit for the PACER pipeline (extraction, entity resolution, GraphRAG traversals); Tentris is viable for RDF-native aggregate SPARQL once conversion cost is paid.

---

*End of benchmark documentation.*
