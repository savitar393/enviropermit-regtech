"""Tests for T5: Multi-activity obligation composition, scope isolation, and fulfillment."""
from __future__ import annotations

from pathlib import Path

from enviropermit.assessment import assess
from enviropermit.composition import compose, validate_shapes
from enviropermit.contracts import Applicability, CaseSnapshot, Fulfillment, Observation
from enviropermit.inference import ROOT, prepare_facts
from enviropermit.sources import select_release

DEV_CASES = Path(ROOT) / "cases/development"


def _load_dev_case(filename: str) -> CaseSnapshot:
    return CaseSnapshot.model_validate_json((DEV_CASES / filename).read_text(encoding="utf-8"))


def test_same_obligation_kind_different_scope_stays_separate() -> None:
    snapshot = _load_dev_case("media_two_outlets.json")
    release = select_release(snapshot)
    composed = compose(assess(snapshot, release))

    pertek_obligations = [
        oa for oa in composed.obligation_assessments if oa.obligation_kind == "water_pertek_required"
    ]
    assert len(pertek_obligations) == 2
    assert {(oa.subject_id, oa.scope_id) for oa in pertek_obligations} == {
        ("water-1", "outlet-1"),
        ("water-2", "outlet-2"),
    }

    amend_obligations = [
        oa for oa in composed.obligation_assessments if oa.obligation_kind == "amend_water_pertek"
    ]
    assert len(amend_obligations) == 2
    assert {(oa.subject_id, oa.scope_id) for oa in amend_obligations} == {
        ("water-1", "outlet-1"),
        ("water-2", "outlet-2"),
    }


def test_shared_evidence_requires_matching_scope() -> None:
    snapshot = _load_dev_case("media_two_outlets.json")
    cross_scope_obs = Observation(
        id="obs-cross-scope",
        context=snapshot.context,
        subject_id="water-2",
        scope_id="outlet-1",
        period_id=snapshot.period_id,
        extent_changes=(False,),
        origin="OBSERVED",
    )
    snapshot = snapshot.model_copy(
        update={"observations": snapshot.observations + (cross_scope_obs,)}
    )
    release = select_release(snapshot)
    raw = assess(snapshot, release)

    # Also test that compose() rejects any injected cross-scope evidence on an ObligationAssessment
    injected_assessments = tuple(
        oa.model_copy(
            update={
                "evidence_ids": oa.evidence_ids + ("obs-outlet-1",),
                "fulfillment": Fulfillment.SATISFIED,
            }
        )
        if oa.subject_id == "water-2" and oa.obligation_kind == "water_pertek_required"
        else oa
        for oa in raw.obligation_assessments
    )
    composed = compose(raw.model_copy(update={"obligation_assessments": injected_assessments}))

    water_two_pertek = next(
        oa
        for oa in composed.obligation_assessments
        if oa.subject_id == "water-2" and oa.obligation_kind == "water_pertek_required"
    )
    assert "obs-outlet-1" not in water_two_pertek.evidence_ids
    assert "obs-cross-scope" not in water_two_pertek.evidence_ids
    assert water_two_pertek.fulfillment == Fulfillment.UNKNOWN
    assert "EVIDENCE_SCOPE_MISMATCH:obs-cross-scope" in composed.evidence_gaps
    assert "EVIDENCE_SCOPE_MISMATCH:obs-outlet-1" in composed.evidence_gaps

    water_two_finding = next(
        ff
        for ff in composed.fulfillment_findings
        if ff.subject_id == "water-2" and ff.obligation_kind == "water_pertek_required"
    )
    assert water_two_finding.status == Fulfillment.UNKNOWN
    assert "obs-outlet-1" not in water_two_finding.evidence_ids


def test_incomplete_inventory_cannot_prove_no_other_changes() -> None:
    snapshot = _load_dev_case("media_existing_emission_pertek.json")
    incomplete_snapshot = snapshot.model_copy(update={"changes_complete": False})
    release = select_release(incomplete_snapshot)
    composed = compose(assess(incomplete_snapshot, release))

    assert "complete_project_change_inventory" in composed.evidence_gaps
    shape_gaps = validate_shapes(prepare_facts(incomplete_snapshot))
    assert "complete_project_change_inventory" in shape_gaps

    air_pertek = next(
        oa
        for oa in composed.obligation_assessments
        if oa.subject_id == "air-1" and oa.obligation_kind == "emission_pertek_required"
    )
    assert air_pertek.applicability == Applicability.APPLICABLE
    assert air_pertek.fulfillment == Fulfillment.UNKNOWN

    air_finding = next(
        ff
        for ff in composed.fulfillment_findings
        if ff.subject_id == "air-1" and ff.obligation_kind == "emission_pertek_required"
    )
    assert air_finding.status == Fulfillment.UNKNOWN


def test_water_and_air_keep_two_scopes_and_single_project_context() -> None:
    snapshot = _load_dev_case("media_water_and_air.json")
    release = select_release(snapshot)
    composed = compose(assess(snapshot, release))

    media_scopes = {
        oa.scope_id
        for oa in composed.obligation_assessments
        if oa.subject_id in ("water-1", "air-1")
    }
    assert media_scopes == {"outlet-1", "boiler-stack-1"}

    project_amendments = [
        oa
        for oa in composed.obligation_assessments
        if oa.obligation_kind == "amend_environmental_approval"
    ]
    assert len(project_amendments) == 1
    assert project_amendments[0].subject_id == snapshot.context.scenario_id
    assert project_amendments[0].scope_id == snapshot.project_id
    assert composed.fulfillment_findings
    assert composed.inference is not None
    all_classes = {c for classes in composed.inference.classifications.values() for c in classes}
    assert "MultiMediaAmendmentScenario" in all_classes
    assert ("water_pertek_change_issued", "environmental_change_issued") in composed.precedence
    assert ("emission_pertek_change_issued", "environmental_change_issued") in composed.precedence
