"""Multi-activity obligation composition, SHACL input completeness, and fulfillment."""
from __future__ import annotations

from pathlib import Path
import re
from urllib.parse import unquote

from .contracts import (
    NS,
    RDF_TYPE,
    AssessmentResult,
    FactBundle,
    Fulfillment,
    FulfillmentFinding,
    ObligationAssessment,
    Triple,
)
from .inference import ROOT

_SHAPE_BLOCK_RE = re.compile(
    r"(?m)^:([A-Za-z0-9_]+)\s+a\s+sh:NodeShape\s*;(.*?\.)",
    re.DOTALL,
)
_TARGET_CLASS_RE = re.compile(r"sh:targetClass\s+:([A-Za-z0-9_]+)")
_PROPERTY_BLOCK_RE = re.compile(r"sh:property\s+\[(.*?)\]", re.DOTALL)
_PATH_RE = re.compile(r"sh:path\s+:([A-Za-z0-9_]+)")
_MIN_COUNT_RE = re.compile(r"sh:minCount\s+(\d+)")
_HAS_VALUE_RE = re.compile(r'sh:hasValue\s+"([^"]+)"')
_MESSAGE_RE = re.compile(r'sh:message\s+"([^"]+)"')

_SYSTEM_EVIDENCE_IDS = frozenset(
    {"configuration", "proposed-screening", "complete-change-inventory"}
)


def validate_shapes(
    facts: FactBundle,
    shapes_path: Path | str = ROOT / "kb/shapes.ttl",
    *,
    extra_triples: tuple[Triple, ...] = (),
) -> tuple[str, ...]:
    path = Path(shapes_path)
    if not path.is_file():
        return ()
    text = path.read_text(encoding="utf-8")
    all_triples = facts.asserted_triples + extra_triples

    exempt_subjects = {
        t.subject
        for t in all_triples
        if t.predicate == NS + "exemptFromDecision"
        or (t.predicate == NS + "hasEmissionAssessment")
    }

    violations: set[str] = set()
    for match in _SHAPE_BLOCK_RE.finditer(text):
        body = match.group(2)
        tc_match = _TARGET_CLASS_RE.search(body)
        if not tc_match:
            continue
        target_class_iri = NS + tc_match.group(1)
        targets = [
            t.subject
            for t in all_triples
            if t.predicate == RDF_TYPE and t.object == target_class_iri
        ]
        for prop_match in _PROPERTY_BLOCK_RE.finditer(body):
            prop_body = prop_match.group(1)
            path_match = _PATH_RE.search(prop_body)
            msg_match = _MESSAGE_RE.search(prop_body)
            if not path_match or not msg_match:
                continue
            predicate_iri = NS + path_match.group(1)
            message = msg_match.group(1)
            min_count_match = _MIN_COUNT_RE.search(prop_body)
            has_value_match = _HAS_VALUE_RE.search(prop_body)

            for subject in targets:
                if predicate_iri == NS + "emitsFrom" and subject in exempt_subjects:
                    continue
                values = [
                    t.object
                    for t in all_triples
                    if t.subject == subject and t.predicate == predicate_iri
                ]
                if min_count_match and len(values) < int(min_count_match.group(1)):
                    violations.add(message)
                if has_value_match and has_value_match.group(1) not in values:
                    violations.add(message)

    return tuple(sorted(violations))


def _build_evidence_scope_map(facts: FactBundle) -> dict[str, set[str]]:
    subject_scope: dict[str, str] = {}
    for triple in facts.asserted_triples:
        if triple.predicate == NS + "onScope" and ":scope-" in triple.object:
            scope_id = unquote(triple.object.rsplit(":scope-", 1)[-1])
            subject_scope[triple.subject] = scope_id

    child_to_activity: dict[str, str] = {}
    for triple in facts.asserted_triples:
        if triple.subject in subject_scope and triple.object.startswith(facts.namespace):
            child_to_activity[triple.object] = triple.subject

    prov_by_index = {p.fact_index: p.evidence_id for p in facts.provenance}
    allowed_scopes: dict[str, set[str]] = {}
    for idx, triple in enumerate(facts.asserted_triples):
        ev_id = prov_by_index.get(idx)
        if not ev_id or ev_id in _SYSTEM_EVIDENCE_IDS:
            continue
        owner = subject_scope.get(triple.subject)
        if owner is None and triple.subject in child_to_activity:
            owner = subject_scope.get(child_to_activity[triple.subject])
        if owner is not None:
            allowed_scopes.setdefault(ev_id, set()).add(owner)

    return allowed_scopes


def compose(result: AssessmentResult) -> AssessmentResult:
    if result.consistency_status != "CONSISTENT":
        return result

    allowed_scopes = _build_evidence_scope_map(result.facts) if result.facts else {}
    inferred_satisfied: set[tuple[str, str]] = set()
    if result.inference and result.facts:
        for triple in result.inference.inferred_triples:
            if triple.predicate == NS + "satisfiesObligation" and ":activity-" in triple.subject:
                subj_id = unquote(triple.subject.rsplit(":activity-", 1)[-1])
                ob_kind = triple.object.rsplit("#", 1)[-1]
                inferred_satisfied.add((subj_id, ob_kind))

    extra_gaps: set[str] = set()
    extra_issues: set[str] = set()
    if result.facts:
        inferred_triples = result.inference.inferred_triples if result.inference else ()
        extra_gaps.update(validate_shapes(result.facts, extra_triples=inferred_triples))

    composed_by_key: dict[tuple[str, str, str], ObligationAssessment] = {}
    for oa in result.obligation_assessments:
        valid_ev: list[str] = []
        had_scope_mismatch = False
        for ev_id in oa.evidence_ids:
            scopes = allowed_scopes.get(ev_id)
            if scopes is not None and oa.scope_id not in scopes:
                had_scope_mismatch = True
                mismatch_code = f"EVIDENCE_SCOPE_MISMATCH:{ev_id}"
                extra_gaps.add(mismatch_code)
                extra_issues.add(mismatch_code)
            else:
                valid_ev.append(ev_id)

        fulfillment = oa.fulfillment
        if (
            had_scope_mismatch
            and fulfillment == Fulfillment.SATISFIED
            and (oa.subject_id, oa.obligation_kind) not in inferred_satisfied
        ):
            fulfillment = Fulfillment.UNKNOWN

        cleaned = oa.model_copy(
            update={
                "evidence_ids": tuple(sorted(set(valid_ev))),
                "fulfillment": fulfillment,
            }
        )
        key = (cleaned.subject_id, cleaned.scope_id, cleaned.obligation_kind)
        existing = composed_by_key.get(key)
        if existing is None:
            composed_by_key[key] = cleaned
        else:
            merged_fulfillment = (
                Fulfillment.SATISFIED
                if Fulfillment.SATISFIED in (existing.fulfillment, cleaned.fulfillment)
                else existing.fulfillment
            )
            composed_by_key[key] = existing.model_copy(
                update={
                    "fulfillment": merged_fulfillment,
                    "evidence_ids": tuple(sorted(set(existing.evidence_ids + cleaned.evidence_ids))),
                    "provision_ids": tuple(sorted(set(existing.provision_ids + cleaned.provision_ids))),
                    "rule_ids": tuple(sorted(set(existing.rule_ids + cleaned.rule_ids))),
                }
            )

    sorted_assessments = tuple(
        sorted(
            composed_by_key.values(),
            key=lambda item: (item.subject_id, item.scope_id, item.obligation_kind),
        )
    )
    findings = tuple(
        FulfillmentFinding(
            subject_id=oa.subject_id,
            scope_id=oa.scope_id,
            obligation_kind=oa.obligation_kind,
            status=oa.fulfillment,
            evidence_ids=oa.evidence_ids,
            provision_ids=oa.provision_ids,
        )
        for oa in sorted_assessments
    )

    return result.model_copy(
        update={
            "obligation_assessments": sorted_assessments,
            "fulfillment_findings": findings,
            "evidence_gaps": tuple(sorted(set(result.evidence_gaps) | extra_gaps)),
            "input_issues": tuple(sorted(set(result.input_issues) | extra_issues)),
        }
    )
