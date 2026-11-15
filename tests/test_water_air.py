"""Tests for T4: Wastewater and stationary air emission obligations."""
from __future__ import annotations

from pathlib import Path

from enviropermit.assessment import assess
from enviropermit.contracts import Applicability, CaseSnapshot, Fulfillment, Observation
from enviropermit.inference import ROOT
from enviropermit.sources import select_release

DEV_CASES = Path(ROOT) / "cases/development"


def _load_dev_case(filename: str) -> CaseSnapshot:
    return CaseSnapshot.model_validate_json((DEV_CASES / filename).read_text(encoding="utf-8"))


def test_water_and_air_coexist() -> None:
    snapshot = _load_dev_case("media_water_and_air.json")
    release = select_release(snapshot)
    result = assess(snapshot, release)

    assert result.consistency_status == "CONSISTENT"
    by_subject_kind = {(oa.subject_id, oa.obligation_kind): oa for oa in result.obligation_assessments}

    assert ("water-1", "water_pertek_required") in by_subject_kind
    assert ("water-1", "water_slo_required") in by_subject_kind
    assert ("water-1", "amend_water_pertek") in by_subject_kind
    assert ("water-1", "prepare_technical_study") in by_subject_kind

    water_study = by_subject_kind[("water-1", "prepare_technical_study")]
    assert water_study.scope_id == "outlet-1"
    assert water_study.applicability == Applicability.APPLICABLE
    assert "P5:16.1.a" in water_study.provision_ids
    assert "obs-water-1" in water_study.evidence_ids
    assert "TechnicalStudyBranch" in water_study.rule_ids

    assert ("air-1", "emission_pertek_required") in by_subject_kind
    assert ("air-1", "emission_slo_required") in by_subject_kind
    assert ("air-1", "amend_emission_pertek") in by_subject_kind
    assert ("air-1", "prepare_emission_technical_study") in by_subject_kind

    air_study = by_subject_kind[("air-1", "prepare_emission_technical_study")]
    assert air_study.scope_id == "boiler-stack-1"
    assert air_study.applicability == Applicability.APPLICABLE
    assert "P5:29.2-emisi-kajian" in air_study.provision_ids
    assert "obs-air-1" in air_study.evidence_ids
    assert "EmissionStudyBranch" in air_study.rule_ids


def test_outlet_one_evidence_does_not_satisfy_outlet_two() -> None:
    snapshot = _load_dev_case("media_two_outlets.json")
    release = select_release(snapshot)
    result = assess(snapshot, release)

    assert result.consistency_status == "CONSISTENT"
    by_subject_kind = {(oa.subject_id, oa.obligation_kind): oa for oa in result.obligation_assessments}

    assert ("water-1", "prepare_standard_technical_documentation") in by_subject_kind
    outlet_one_doc = by_subject_kind[("water-1", "prepare_standard_technical_documentation")]
    assert outlet_one_doc.scope_id == "outlet-1"
    assert outlet_one_doc.applicability == Applicability.APPLICABLE
    assert "obs-outlet-1" in outlet_one_doc.evidence_ids
    assert "P5:16.1.b" in outlet_one_doc.provision_ids

    assert ("water-2", "prepare_standard_technical_documentation") not in by_subject_kind
    assert ("water-2", "prepare_technical_study") not in by_subject_kind
    assert ("water-2", "water_document_route") in by_subject_kind
    outlet_two_route = by_subject_kind[("water-2", "water_document_route")]
    assert outlet_two_route.scope_id == "outlet-2"
    assert outlet_two_route.applicability == Applicability.UNRESOLVED
    assert "obs-outlet-1" not in outlet_two_route.evidence_ids
    assert "impact_extent_assessment" in result.evidence_gaps


def test_no_emission_fact_is_not_emission_exemption() -> None:
    snapshot = _load_dev_case("media_unverified_emission.json")
    release = select_release(snapshot)
    result = assess(snapshot, release)

    assert result.consistency_status == "CONSISTENT"
    air_assessments = [oa for oa in result.obligation_assessments if oa.subject_id == "air-1"]
    assert air_assessments
    assert not any(oa.applicability == Applicability.NOT_APPLICABLE for oa in air_assessments)
    assert any(
        oa.obligation_kind == "emission_obligation_status"
        and oa.applicability == Applicability.UNRESOLVED
        and oa.scope_id == "boiler-stack-1"
        and "P5:28-emisi" in oa.provision_ids
        for oa in air_assessments
    )
    assert "stationary_emission_or_exemption_evidence" in result.evidence_gaps


def test_existing_emission_pertek_without_change_does_not_require_reissuance() -> None:
    snapshot = _load_dev_case("media_existing_emission_pertek.json")
    release = select_release(snapshot)
    result = assess(snapshot, release)

    assert result.consistency_status == "CONSISTENT"
    by_subject_kind = {(oa.subject_id, oa.obligation_kind): oa for oa in result.obligation_assessments}

    assert ("air-1", "emission_pertek_required") in by_subject_kind
    assert ("air-1", "emission_slo_required") in by_subject_kind
    assert ("air-1", "amend_emission_pertek") not in by_subject_kind

    pertek = by_subject_kind[("air-1", "emission_pertek_required")]
    assert pertek.scope_id == "boiler-stack-1"
    assert pertek.applicability == Applicability.APPLICABLE
    assert pertek.fulfillment == Fulfillment.SATISFIED
    assert "P5:28-emisi" in pertek.provision_ids


def test_explicit_non_emitting_source_evidence_yields_not_applicable() -> None:
    snapshot = _load_dev_case("media_unverified_emission.json")
    obs = Observation(
        id="obs-electric-boiler",
        context=snapshot.context,
        subject_id="air-1",
        scope_id="boiler-stack-1",
        period_id=snapshot.period_id,
        non_emitting_source=(True,),
        origin="OBSERVED",
    )
    snapshot = snapshot.model_copy(update={"observations": (obs,)})
    release = select_release(snapshot)
    result = assess(snapshot, release)

    assert result.consistency_status == "CONSISTENT"
    by_subject_kind = {(oa.subject_id, oa.obligation_kind): oa for oa in result.obligation_assessments}
    assert ("air-1", "emission_obligation_status") in by_subject_kind
    status = by_subject_kind[("air-1", "emission_obligation_status")]
    assert status.applicability == Applicability.NOT_APPLICABLE
    assert "obs-electric-boiler" in status.evidence_ids
    assert "P5:28-emisi" in status.provision_ids
