"""Shared RDF vocabulary for PACER KG (Neo4j property graph → RDF triples)."""

from __future__ import annotations

from urllib.parse import quote

# Base IRIs
PACER = "http://scales-kg.org/pacer#"
PACER_ID = "http://scales-kg.org/id/"
RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
RDFS = "http://www.w3.org/2000/01/rdf-schema#"
XSD = "http://www.w3.org/2001/XMLSchema#"

LABEL_MAP = {
    "Court": "Court",
    "Case": "Case",
    "Party": "Party",
    "Organization": "Organization",
    "Judge": "Judge",
    "Attorney": "Attorney",
    "Person": "Attorney",
    "ExternalCourtRef": "ExternalCourtRef",
    "DocketEntry": "DocketEntry",
}

CLASS_IRI = {
    "Court": f"{PACER}Court",
    "Case": f"{PACER}Case",
    "Party": f"{PACER}Party",
    "Organization": f"{PACER}Organization",
    "Judge": f"{PACER}Judge",
    "Attorney": f"{PACER}Attorney",
    "ExternalCourtRef": f"{PACER}ExternalCourtRef",
    "DocketEntry": f"{PACER}DocketEntry",
    "PartyLink": f"{PACER}PartyLink",
    "CounselLink": f"{PACER}CounselLink",
    "RelatedCaseLink": f"{PACER}RelatedCaseLink",
}

# Direct edge predicates (no edge properties)
REL_PREDICATE = {
    "FILED_IN": f"{PACER}filedIn",
    "ASSIGNED_JUDGE": f"{PACER}assignedJudge",
    "REFERRED_TO": f"{PACER}referredTo",
    "LEAD_CASE": f"{PACER}leadCase",
    "APPEAL_IN": f"{PACER}appealIn",
    "HAS_DOCKET_ENTRY": f"{PACER}hasDocketEntry",
}

# Reified edge types (edge carries properties in Neo4j)
REIFIED_REL = {
    "HAS_PARTY": "PartyLink",
    "REPRESENTED_BY": "CounselLink",
    "RELATED_CASE": "RelatedCaseLink",
}

# Node property → predicate IRI (None = skip)
NODE_PROP_PREDICATE = {
    "code": f"{PACER}hasCode",
    "ucid": f"{PACER}hasUcid",
    "case_id": f"{PACER}hasCaseId",
    "case_name": f"{PACER}hasCaseName",
    "case_type": f"{PACER}hasCaseType",
    "filing_date": f"{PACER}hasFilingDate",
    "terminating_date": f"{PACER}hasTerminatingDate",
    "case_status": f"{PACER}hasCaseStatus",
    "nature_suit": f"{PACER}hasNatureSuit",
    "cause": f"{PACER}hasCause",
    "jurisdiction": f"{PACER}hasJurisdiction",
    "header_case_id": f"{PACER}hasHeaderCaseId",
    "name": f"{PACER}hasName",
    "role": f"{PACER}hasRole",
    "party_type": f"{PACER}hasPartyType",
    "kind": f"{PACER}hasKind",
    "canonical": f"{PACER}isCanonical",
    "stub": f"{PACER}isStub",
    "email": f"{PACER}hasEmail",
    "office": f"{PACER}hasOffice",
    "ref": f"{PACER}hasRef",
    "ind": f"{PACER}hasInd",
    "date_filed": f"{PACER}hasDateFiled",
    "docket_text": f"{PACER}hasDocketText",
}

# Edge property → predicate on reified link
EDGE_PROP_PREDICATE = {
    "role": f"{PACER}hasRole",
    "party_type": f"{PACER}hasPartyType",
    "is_lead": f"{PACER}isLead",
    "is_pro_se": f"{PACER}isProSe",
    "raw_ref": f"{PACER}hasRawRef",
}

REIFIED_FROM = f"{PACER}from"
REIFIED_TO = f"{PACER}to"


def node_uri(label: str, node_id: str) -> str:
    """Stable instance IRI from CSV label + id."""
    slug = quote(node_id, safe="")
    return f"{PACER_ID}{label.lower()}/{slug}"


def reified_uri(rel_type: str, from_label: str, from_id: str, to_label: str, to_id: str, idx: int) -> str:
    base = f"{rel_type.lower()}_{quote(from_id, safe='')}_{quote(to_id, safe='')}_{idx}"
    return f"{PACER_ID}link/{base}"
