#!/usr/bin/env python3
"""
SPARQL equivalents of graphrag_local.py Cypher queries.

Each query mirrors the Neo4j predefined menu for apples-to-apples benchmarking.
"""

from __future__ import annotations

PREFIXES = """
PREFIX pacer: <http://scales-kg.org/pacer#>
PREFIX rdf:   <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs:  <http://www.w3.org/2000/01/rdf-schema#>
"""

QUERIES: dict[str, dict] = {
    "judges": {
        "description": "Top 10 judges by caseload",
        "sparql": PREFIXES
        + """
SELECT ?judgeName (COUNT(DISTINCT ?case) AS ?cases) WHERE {
  ?case rdf:type pacer:Case .
  ?case pacer:assignedJudge ?judge .
  ?judge rdfs:label ?judgeName .
}
GROUP BY ?judgeName
ORDER BY DESC(?cases)
LIMIT 10
""",
    },
    "attorney_courts": {
        "description": "Attorneys appearing in more than one court",
        "sparql": PREFIXES
        + """
SELECT ?attorneyName (COUNT(DISTINCT ?courtCode) AS ?court_count) (COUNT(DISTINCT ?case) AS ?cases) WHERE {
  ?link rdf:type pacer:CounselLink .
  ?link pacer:from ?party .
  ?link pacer:to ?attorney .
  ?attorney rdf:type pacer:Attorney .
  ?attorney rdfs:label ?attorneyName .

  ?partyLink rdf:type pacer:PartyLink .
  ?partyLink pacer:from ?case .
  ?partyLink pacer:to ?party .

  ?case rdf:type pacer:Case .
  ?case pacer:filedIn ?court .
  ?court pacer:hasCode ?courtCode .
}
GROUP BY ?attorneyName
HAVING (COUNT(DISTINCT ?courtCode) > 1)
ORDER BY DESC(?cases)
LIMIT 25
""",
    },
    "court_stats": {
        "description": "Case count per court (descending)",
        "sparql": PREFIXES
        + """
SELECT ?court (COUNT(DISTINCT ?case) AS ?cases) WHERE {
  ?case rdf:type pacer:Case .
  ?case pacer:filedIn ?courtNode .
  ?courtNode pacer:hasCode ?court .
}
GROUP BY ?court
ORDER BY DESC(?cases)
""",
    },
    "usa_cases": {
        "description": "Cases where USA is plaintiff",
        "sparql": PREFIXES
        + """
SELECT ?ucid ?case_name ?filing_date ?org WHERE {
  ?link rdf:type pacer:PartyLink .
  ?link pacer:from ?case .
  ?link pacer:to ?orgNode .
  ?link pacer:hasRole ?role .
  FILTER(CONTAINS(LCASE(?role), "plaintiff"))

  ?orgNode rdf:type pacer:Organization .
  ?orgNode rdfs:label ?org .
  OPTIONAL { ?orgNode pacer:isCanonical ?canonical . }

  FILTER(
    (?canonical = true) ||
    LCASE(?org) = "usa" ||
    LCASE(?org) = "united states" ||
    LCASE(?org) = "united states of america"
  )

  ?case pacer:hasUcid ?ucid .
  ?case pacer:hasCaseName ?case_name .
  OPTIONAL { ?case pacer:hasFilingDate ?filing_date . }
}
ORDER BY DESC(?filing_date)
LIMIT 50
""",
    },
    "cocounsel": {
        "description": "Attorney pairs sharing 2+ cases (co-counsel)",
        "sparql": PREFIXES
        + """
SELECT ?attorney_a ?attorney_b (COUNT(DISTINCT ?case) AS ?shared_cases) WHERE {
  ?pl rdf:type pacer:PartyLink .
  ?pl pacer:from ?case .
  ?pl pacer:to ?party .

  ?cl1 rdf:type pacer:CounselLink .
  ?cl1 pacer:from ?party .
  ?cl1 pacer:to ?a1 .
  ?a1 rdfs:label ?attorney_a .

  ?cl2 rdf:type pacer:CounselLink .
  ?cl2 pacer:from ?party .
  ?cl2 pacer:to ?a2 .
  ?a2 rdfs:label ?attorney_b .

  FILTER(?a1 != ?a2)
  BIND(STR(?a1) AS ?a1s)
  BIND(STR(?a2) AS ?a2s)
  FILTER(?a1s < ?a2s)
}
GROUP BY ?attorney_a ?attorney_b ?a1 ?a2
HAVING (COUNT(DISTINCT ?case) >= 2)
ORDER BY DESC(?shared_cases)
LIMIT 25
""",
    },
    "judge_attorney": {
        "description": "Attorney appearances before each judge (min 2 cases)",
        "sparql": PREFIXES
        + """
SELECT ?judge ?attorney (COUNT(DISTINCT ?case) AS ?cases) WHERE {
  ?case rdf:type pacer:Case .
  ?case pacer:assignedJudge ?judgeNode .
  ?judgeNode rdfs:label ?judge .

  ?pl rdf:type pacer:PartyLink .
  ?pl pacer:from ?case .
  ?pl pacer:to ?party .

  ?cl rdf:type pacer:CounselLink .
  ?cl pacer:from ?party .
  ?cl pacer:to ?attorneyNode .
  ?attorneyNode rdfs:label ?attorney .
}
GROUP BY ?judge ?attorney
HAVING (COUNT(DISTINCT ?case) >= 2)
ORDER BY DESC(?cases)
LIMIT 30
""",
    },
    "related": {
        "description": "Cases with the most related-case links",
        "sparql": PREFIXES
        + """
SELECT ?ucid ?case_name (COUNT(?related) AS ?related_count) WHERE {
  ?case rdf:type pacer:Case .
  ?case pacer:hasUcid ?ucid .
  OPTIONAL { ?case pacer:hasCaseName ?case_name . }

  ?link rdf:type pacer:RelatedCaseLink .
  ?link pacer:from ?case .
  ?link pacer:to ?related .
}
GROUP BY ?ucid ?case_name
ORDER BY DESC(?related_count)
LIMIT 20
""",
    },
    "criminal": {
        "description": "Criminal cases (case_type = cr)",
        "sparql": PREFIXES
        + """
SELECT ?ucid ?case_name ?court ?filing_date WHERE {
  ?case rdf:type pacer:Case .
  ?case pacer:hasCaseType "cr" .
  ?case pacer:hasUcid ?ucid .
  ?case pacer:hasCaseName ?case_name .
  OPTIONAL { ?case pacer:hasFilingDate ?filing_date . }
  ?case pacer:filedIn ?courtNode .
  ?courtNode pacer:hasCode ?court .
}
ORDER BY DESC(?filing_date)
LIMIT 50
""",
    },
    "civil": {
        "description": "Civil cases (case_type = cv)",
        "sparql": PREFIXES
        + """
SELECT ?ucid ?case_name ?court ?filing_date WHERE {
  ?case rdf:type pacer:Case .
  ?case pacer:hasCaseType "cv" .
  ?case pacer:hasUcid ?ucid .
  ?case pacer:hasCaseName ?case_name .
  OPTIONAL { ?case pacer:hasFilingDate ?filing_date . }
  ?case pacer:filedIn ?courtNode .
  ?courtNode pacer:hasCode ?court .
}
ORDER BY DESC(?filing_date)
LIMIT 50
""",
    },
    "party_search": {
        "description": "Search parties by name (usage: party_search <name>)",
        "sparql": PREFIXES
        + """
SELECT ?party ?type ?ucid ?case_name WHERE {
  {
    ?p rdf:type pacer:Party .
    ?p rdfs:label ?party .
    BIND("Party" AS ?type)
  } UNION {
    ?p rdf:type pacer:Organization .
    ?p rdfs:label ?party .
    BIND("Organization" AS ?type)
  }
  FILTER(CONTAINS(LCASE(?party), LCASE(?name)))

  ?link rdf:type pacer:PartyLink .
  ?link pacer:from ?case .
  ?link pacer:to ?p .
  ?case pacer:hasUcid ?ucid .
  OPTIONAL { ?case pacer:hasCaseName ?case_name . }
}
ORDER BY DESC(?case_name)
LIMIT 50
""",
        "needs_arg": True,
    },
    "triple_count": {
        "description": "Total triple count (Tentris sanity check)",
        "sparql": "SELECT (COUNT(*) AS ?triples) WHERE { ?s ?p ?o }",
    },
}

# Neo4j Cypher copies for benchmark_compare.py (from graphrag_local.py)
CYPHER_QUERIES: dict[str, str] = {
    "judges": """
        MATCH (j:Judge)<-[:ASSIGNED_JUDGE]-(c:Case)
        RETURN j.name AS judge, count(c) AS cases
        ORDER BY cases DESC LIMIT 10
    """,
    "attorney_courts": """
        MATCH (a:Attorney)<-[:REPRESENTED_BY]-()<-[:HAS_PARTY]-(c:Case)-[:FILED_IN]->(court:Court)
        WITH a, collect(DISTINCT court.code) AS courts, count(DISTINCT c) AS cases
        WHERE size(courts) > 1
        RETURN a.name AS attorney, courts, cases
        ORDER BY cases DESC LIMIT 25
    """,
    "court_stats": """
        MATCH (c:Case)-[:FILED_IN]->(court:Court)
        RETURN court.code AS court, count(c) AS cases
        ORDER BY cases DESC
    """,
    "usa_cases": """
        MATCH (c:Case)-[r:HAS_PARTY]->(o:Organization)
        WHERE o.canonical = true
           OR toLower(o.name) IN ['usa', 'united states', 'united states of america']
        WITH c, r, o
        WHERE toLower(coalesce(r.role, '')) CONTAINS 'plaintiff'
        RETURN c.ucid AS ucid, c.case_name AS case_name, c.filing_date AS filing_date, o.name AS org
        ORDER BY c.filing_date DESC LIMIT 50
    """,
    "cocounsel": """
        MATCH (p)<-[:HAS_PARTY]-(c:Case)
        MATCH (p)-[:REPRESENTED_BY]->(a1:Attorney)
        MATCH (p)-[:REPRESENTED_BY]->(a2:Attorney)
        WHERE a1.id < a2.id
        WITH a1, a2, count(DISTINCT c) AS shared_cases
        WHERE shared_cases >= 2
        RETURN a1.name AS attorney_a, a2.name AS attorney_b, shared_cases
        ORDER BY shared_cases DESC LIMIT 25
    """,
    "judge_attorney": """
        MATCH (c:Case)-[:ASSIGNED_JUDGE]->(j:Judge)
        MATCH (c)-[:HAS_PARTY]->(p)-[:REPRESENTED_BY]->(a:Attorney)
        WITH j, a, count(DISTINCT c) AS cases
        WHERE cases >= 2
        RETURN j.name AS judge, a.name AS attorney, cases
        ORDER BY cases DESC LIMIT 30
    """,
    "related": """
        MATCH (c:Case)-[:RELATED_CASE]->(rc:Case)
        WITH c, count(rc) AS related_count
        RETURN c.ucid AS ucid, c.case_name AS case_name, related_count
        ORDER BY related_count DESC LIMIT 20
    """,
    "criminal": """
        MATCH (c:Case)-[:FILED_IN]->(court:Court)
        WHERE c.case_type = 'cr'
        RETURN c.ucid AS ucid, c.case_name AS case_name, court.code AS court, c.filing_date AS filing_date
        ORDER BY c.filing_date DESC LIMIT 50
    """,
    "civil": """
        MATCH (c:Case)-[:FILED_IN]->(court:Court)
        WHERE c.case_type = 'cv'
        RETURN c.ucid AS ucid, c.case_name AS case_name, court.code AS court, c.filing_date AS filing_date
        ORDER BY c.filing_date DESC LIMIT 50
    """,
    "party_search": """
        MATCH (p)
        WHERE (p:Party OR p:Organization)
          AND toLower(p.name) CONTAINS toLower($name)
        MATCH (c:Case)-[:HAS_PARTY]->(p)
        RETURN p.name AS party, labels(p)[0] AS type, c.ucid AS ucid, c.case_name AS case_name
        ORDER BY c.filing_date DESC LIMIT 50
    """,
}
