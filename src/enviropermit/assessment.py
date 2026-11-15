"""Project obligation assessment projection from OWL/SWRL inference results."""
from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

from .contracts import (
    NS,
    Applicability,
    AssessmentResult,
    CaseSnapshot,
    Fulfillment,
    KBRelease,
    ObligationAssessment,
)
from .inference import ROOT, infer, prepare_facts
from .sources import (
    audit_rule_sources,
    load_decision_sources,
    load_obligation_rules,
    select_release,
)


def _resolve_kb_path(release: KBRelease) -> Path:
    path = Path(release.knowledge_base_path)
    return path if path.is_absolute() else ROOT / path


def assess(
    snapshot: CaseSnapshot,
    release: KBRelease | None = None,
    *,
    artifact_dir: Path | str | None = None,
) -> AssessmentResult:
    selected_release = release or select_release(snapshot)
    facts = prepare_facts(snapshot)
    inference = infer(facts, selected_release, artifact_dir=artifact_dir)

    if inference.consistency_status != "CONSISTENT":
        return AssessmentResult(
            assessment_id=snapshot.context.assessment_id,
            context=snapshot.context,
            kb_version=selected_release.id,
            consistency_status=inference.consistency_status,
            obligation_assessments=(),
            project_obligations=inference.project_obligations,
            decisions=inference.decisions,
            precedence=inference.precedence,
            evidence_gaps=inference.evidence_gaps,
            conflicts=inference.conflicts,
            explanations=inference.source_traces,
            input_issues=inference.input_issues,
            inference=inference,
        )

    kb_path = _resolve_kb_path(selected_release)
    obligation_rules = load_obligation_rules(kb_path)
    rule_sources = audit_rule_sources(kb_path)
    decision_sources = load_decision_sources(kb_path)

    subject_lookup: dict[str, tuple[str, str]] = {
        f"{facts.namespace}scenario": (snapshot.context.scenario_id, snapshot.project_id),
    }
    candidate_to_subject: dict[str, str] = {}
    for activity in snapshot.activities:
        act_iri = f"{facts.namespace}activity-{quote(activity.id, safe='-_')}"
        subject_lookup[act_iri] = (activity.id, activity.scope_id)
        cand_iri = f"{facts.namespace}study-candidate-{quote(activity.id, safe='-_')}"
        candidate_to_subject[cand_iri] = act_iri

    prov_by_index = {p.fact_index: p.evidence_id for p in facts.provenance}
    subject_evidence: dict[str, set[str]] = {iri: set() for iri in subject_lookup}
    for idx, triple in enumerate(facts.asserted_triples):
        ev_id = prov_by_index.get(idx)
        if ev_id and triple.subject in subject_evidence:
            subject_evidence[triple.subject].add(ev_id)
    for closure in facts.closures:
        if closure.subject in subject_evidence:
            subject_evidence[closure.subject].add(closure.evidence_id)

    satisfied_pairs = {
        (t.subject, t.object.rsplit("#", 1)[-1])
        for t in inference.inferred_triples
        if t.predicate == NS + "satisfiesObligation"
    }
    exempt_decisions = {
        (t.subject, t.object.rsplit("#", 1)[-1])
        for t in inference.inferred_triples
        if t.predicate == NS + "exemptFromDecision"
    }

    fired_by_subject: dict[str, set[str]] = {}
    for fired in inference.fired_rules:
        for concl in fired.conclusions:
            owner = candidate_to_subject.get(concl.subject, concl.subject)
            fired_by_subject.setdefault(owner, set()).add(fired.rule_id)

    assessments: list[ObligationAssessment] = []
    seen_keys: set[tuple[str, str, str]] = set()

    for triple in inference.inferred_triples:
        if triple.predicate not in (NS + "activityObligation", NS + "scenarioObligation"):
            continue
        if triple.subject not in subject_lookup:
            continue
        ob_kind = triple.object.rsplit("#", 1)[-1]
        subj_classes = set(inference.classifications.get(triple.subject, ()))
        matching_rules = sorted(subj_classes.intersection(obligation_rules.get(ob_kind, ())))
        if not matching_rules:
            continue

        subj_id, scope_id = subject_lookup[triple.subject]
        dedup_key = (subj_id, scope_id, ob_kind)
        if dedup_key in seen_keys:
            continue
        seen_keys.add(dedup_key)

        provisions: set[str] = set()
        for r_id in matching_rules:
            provisions.update(rule_sources.get(r_id, ()))

        if triple.subject in fired_by_subject:
            for r_id in sorted(fired_by_subject[triple.subject]):
                r_sources = set(rule_sources.get(r_id, ()))
                if r_id not in matching_rules and r_sources.intersection(provisions):
                    matching_rules.append(r_id)
                    provisions.update(r_sources)

        fulfillment = (
            Fulfillment.SATISFIED
            if (triple.subject, ob_kind) in satisfied_pairs
            else Fulfillment.UNKNOWN
        )
        assessments.append(
            ObligationAssessment(
                assessment_id=snapshot.context.assessment_id,
                subject_id=subj_id,
                obligation_kind=ob_kind,
                scope_id=scope_id,
                applicability=Applicability.APPLICABLE,
                fulfillment=fulfillment,
                evidence_ids=tuple(sorted(subject_evidence.get(triple.subject, set()))),
                provision_ids=tuple(sorted(provisions)),
                rule_ids=tuple(matching_rules),
            )
        )

    for decision in inference.decisions:
        if decision.subject_id not in subject_lookup:
            continue
        subj_id, scope_id = subject_lookup[decision.subject_id]
        dedup_key = (subj_id, scope_id, decision.id)
        if decision.applicability == Applicability.UNRESOLVED and dedup_key not in seen_keys:
            seen_keys.add(dedup_key)
            assessments.append(
                ObligationAssessment(
                    assessment_id=snapshot.context.assessment_id,
                    subject_id=subj_id,
                    obligation_kind=decision.id,
                    scope_id=scope_id,
                    applicability=Applicability.UNRESOLVED,
                    fulfillment=Fulfillment.UNKNOWN,
                    evidence_ids=tuple(sorted(subject_evidence.get(decision.subject_id, set()))),
                    provision_ids=decision_sources.get(decision.id, ()),
                    rule_ids=(decision.id,),
                )
            )
        elif (decision.subject_id, decision.id) in exempt_decisions and dedup_key not in seen_keys:
            seen_keys.add(dedup_key)
            provisions = {
                src
                for branch in decision.branches
                for src in rule_sources.get(branch, ())
            }
            assessments.append(
                ObligationAssessment(
                    assessment_id=snapshot.context.assessment_id,
                    subject_id=subj_id,
                    obligation_kind=decision.id,
                    scope_id=scope_id,
                    applicability=Applicability.NOT_APPLICABLE,
                    fulfillment=Fulfillment.SATISFIED,
                    evidence_ids=tuple(sorted(subject_evidence.get(decision.subject_id, set()))),
                    provision_ids=tuple(sorted(provisions)),
                    rule_ids=decision.branches,
                )
            )

    assessments.sort(key=lambda oa: (oa.subject_id, oa.scope_id, oa.obligation_kind))

    return AssessmentResult(
        assessment_id=snapshot.context.assessment_id,
        context=snapshot.context,
        kb_version=selected_release.id,
        consistency_status=inference.consistency_status,
        obligation_assessments=tuple(assessments),
        project_obligations=inference.project_obligations,
        decisions=inference.decisions,
        precedence=inference.precedence,
        evidence_gaps=inference.evidence_gaps,
        conflicts=inference.conflicts,
        explanations=inference.source_traces,
        input_issues=inference.input_issues,
        facts=facts,
        inference=inference,
    )
