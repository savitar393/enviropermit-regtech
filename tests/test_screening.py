from pathlib import Path
import pytest

from enviropermit.contracts import CaseSnapshot
from enviropermit.inference import ROOT, infer, prepare_facts
from enviropermit.sources import select_release

DEV_DIR = ROOT / "cases/development"


def load_dev_case(name: str, **overrides) -> CaseSnapshot:
    snapshot = CaseSnapshot.model_validate_json((DEV_DIR / f"{name}.json").read_text(encoding="utf-8"))
    if overrides:
        snapshot = snapshot.model_copy(update=overrides)
    return snapshot


def _decision(result, decision_id: str):
    return next(d for d in result.decisions if d.id == decision_id)


def _trace_locators(result, conclusion: str) -> set[str]:
    return {
        prov.get("locator", "")
        for trace in result.source_traces
        if trace.get("conclusion") == conclusion
        for prov in trace.get("provisions", ())
    }


def test_below_sppl_threshold_infers_sppl_route():
    snapshot = load_dev_case("screening_below_sppl")
    facts = prepare_facts(snapshot)
    assert facts.normalized_values[0]["normalized_value"] == "200.0"
    assert facts.normalized_values[0]["canonical_unit"] == "ton/year"

    result = infer(facts, select_release(snapshot))
    assert result.consistency_status == "CONSISTENT"
    route = _decision(result, "screening_document_route")
    assert route.applicability == "APPLICABLE"
    assert route.branches == ("FoodManufacturingSpplScale",)
    assert "register_sppl" in result.project_obligations
    assert any("Lampiran I Bidang Perindustrian" in loc for loc in _trace_locators(result, "FoodManufacturingSpplScale"))


def test_exact_ambiguous_boundary_250_is_unresolved_with_source_issue():
    snapshot = load_dev_case("screening_boundary_250")
    result = infer(prepare_facts(snapshot), select_release(snapshot))
    assert result.consistency_status == "CONSISTENT"
    route = _decision(result, "screening_document_route")
    assert route.applicability == "UNRESOLVED"
    assert not route.branches
    assert "source_boundary_issue:P4:lampiran-i-pangan-batas:250_ton_per_year" in result.evidence_gaps
    assert "register_sppl" not in result.project_obligations
    assert "prepare_ukl_upl" not in result.project_obligations
    assert any("Lampiran I Bidang Perindustrian" in loc for loc in _trace_locators(result, "FoodManufacturingBoundaryAmbiguous"))


def test_equivalent_unit_kg_per_year_normalizes_and_infers_ukl_route():
    snapshot = load_dev_case("screening_ukl_equivalent_unit")
    facts = prepare_facts(snapshot)
    assert facts.normalized_values[0]["raw_value"] == 500000.0
    assert facts.normalized_values[0]["raw_unit"] == "kg/tahun"
    assert facts.normalized_values[0]["normalized_value"] == "500.0"
    assert facts.normalized_values[0]["canonical_unit"] == "ton/year"

    result = infer(facts, select_release(snapshot))
    assert result.consistency_status == "CONSISTENT"
    route = _decision(result, "screening_document_route")
    assert route.applicability == "APPLICABLE"
    assert route.branches == ("FoodManufacturingUklScale",)
    assert "prepare_ukl_upl" in result.project_obligations
    assert any("Lampiran I Bidang Perindustrian" in loc for loc in _trace_locators(result, "FoodManufacturingUklScale"))


@pytest.mark.parametrize("case_name", ["screening_boundary_10000_amdal", "screening_above_amdal"])
def test_at_and_above_explicit_amdal_threshold_infers_amdal_route(case_name):
    snapshot = load_dev_case(case_name)
    result = infer(prepare_facts(snapshot), select_release(snapshot))
    assert result.consistency_status == "CONSISTENT"
    route = _decision(result, "screening_document_route")
    assert route.applicability == "APPLICABLE"
    assert route.branches == ("FoodManufacturingAmdalScale",)
    assert "prepare_amdal" in result.project_obligations
    assert any("Lampiran I Bidang Perindustrian" in loc for loc in _trace_locators(result, "FoodManufacturingAmdalScale"))


def test_protected_area_triggers_amdal_unless_explicitly_exempt():
    snapshot = load_dev_case("screening_protected_area")
    result = infer(prepare_facts(snapshot), select_release(snapshot))
    assert result.consistency_status == "CONSISTENT"
    route = _decision(result, "screening_document_route")
    assert route.applicability == "APPLICABLE"
    assert route.branches == ("ProtectedAreaActivity",)
    assert "prepare_amdal" in result.project_obligations
    assert any("Pasal 3" in loc for loc in _trace_locators(result, "ProtectedAreaActivity"))

    exempt_obs = snapshot.observations[0].model_copy(update={"protected_area_exception": (True,)})
    exempt_snapshot = snapshot.model_copy(update={"observations": (exempt_obs,)})
    exempt_result = infer(prepare_facts(exempt_snapshot), select_release(exempt_snapshot))
    exempt_route = _decision(exempt_result, "screening_document_route")
    assert exempt_route.applicability == "APPLICABLE"
    assert exempt_route.branches == ("FoodManufacturingSpplScale",)
    assert "register_sppl" in exempt_result.project_obligations
    assert any("Pasal 4" in loc for loc in _trace_locators(exempt_result, "ProtectedAreaExemptActivity"))


def test_unknown_location_produces_unresolved_and_location_gap():
    snapshot = load_dev_case("screening_unknown_location")
    result = infer(prepare_facts(snapshot), select_release(snapshot))
    assert result.consistency_status == "CONSISTENT"
    route = _decision(result, "screening_document_route")
    assert route.applicability == "UNRESOLVED"
    assert not route.branches
    assert "protected_area_location_verification" in result.evidence_gaps
    assert "prepare_ukl_upl" not in result.project_obligations


def test_incompatible_unit_is_rejected_without_guessing():
    snapshot = load_dev_case("screening_below_sppl")
    bad_measurement = snapshot.measurements[0].model_copy(update={"unit": "m3/day"})
    bad_snapshot = snapshot.model_copy(update={"measurements": (bad_measurement,)})
    facts = prepare_facts(bad_snapshot)
    assert any(issue.startswith("UNIT_MISMATCH:") for issue in facts.input_issues)

    result = infer(facts, select_release(bad_snapshot))
    route = _decision(result, "screening_document_route")
    assert route.applicability == "UNRESOLVED"
    assert "production_capacity_measurement" in result.evidence_gaps


def test_mixed_identity_and_capacity_changes_with_inferred_screening():
    snapshot = load_dev_case("screening_mixed_changes")
    result = infer(prepare_facts(snapshot), select_release(snapshot))
    assert result.consistency_status == "CONSISTENT"
    assert "prepare_amdal" in result.project_obligations
    assert "amend_environmental_approval" in result.project_obligations
    assert "prepare_new_environmental_documentation" in result.project_obligations
    assert "amend_water_pertek" in result.project_obligations
    assert "prepare_technical_study" in result.project_obligations
    assert "water_pertek_required" in result.project_obligations
    assert "water_slo_required" in result.project_obligations
    conclusions = {c for classes in result.classifications.values() for c in classes}
    assert "WithNewEnvironmentalDocumentation" in conclusions
    assert "WithoutNewEnvironmentalDocumentation" not in conclusions
    assert "ConcurrentSubmissionPermitted" in conclusions
    assert any("Pasal 89" in loc for loc in _trace_locators(result, "WithNewEnvironmentalDocumentation"))
