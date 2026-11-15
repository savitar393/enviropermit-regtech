import json
from pathlib import Path

import pytest

from enviropermit.inference import infer, prepare_facts

EXPECTED = json.loads((Path(__file__).parents[2] / "cases/regression/water_spike/expected.json").read_text())


@pytest.mark.parametrize("name", list(EXPECTED))
def test_preserved_spike_outcomes(name, case, release):
    want = EXPECTED[name]
    result = infer(prepare_facts(case(name)), release)
    assert result.profiles["core"].in_owl2_dl_profile
    assert result.profiles["asserted"].in_owl2_dl_profile
    assert result.consistency_status == want["status"]
    assert list(result.project_obligations) == want["obligations"]
    assert [list(edge) for edge in result.precedence] == want["precedence"]
    assert set(want["evidence_gaps"]) <= set(result.evidence_gaps)
    conclusions = {c for classes in result.classifications.values() for c in classes}
    assert set(want["conclusions"]) - {"Case", "Thing"} <= conclusions
    if name == "C":
        assert not result.inferred_triples
        assert not result.fired_rules
    else:
        assert result.profiles["post_rules"].in_owl2_dl_profile


def test_incomplete_inventory_does_not_prove_identity_only(case, release):
    result = infer(prepare_facts(case("I", changes_complete=False)), release)
    assert not any("WithoutNewEnvironmentalDocumentation" in c for c in result.classifications.values())
    assert "complete_project_change_inventory" in result.evidence_gaps


def test_unknown_screening_does_not_copy_old_regime(case, release):
    result = infer(prepare_facts(case("A", screening=None)), release)
    assert ("submit_water_pertek_change", "submit_environmental_change") not in result.precedence
    assert "proposed_activity_screening" in result.evidence_gaps


def test_outsourcing_is_not_exemption(case, release):
    data = case().activities[0].model_dump()
    data["surface_discharge"] = False
    result = infer(prepare_facts(case(activities=[data], outsourcing_claim=True)), release)
    assert not any("ExemptFromWaterObligations" in c for c in result.classifications.values())
    assert "outsourced_wastewater_route_outside_verified_slice" in result.evidence_gaps
    assert not any(d.applicability == "NOT_APPLICABLE" for d in result.decisions)


def test_missing_prior_pertek_does_not_use_amendment_route(case, release):
    data = case().activities[0].model_dump()
    data["existing_water_pertek"] = False
    result = infer(prepare_facts(case(activities=[data])), release)
    assert "amend_water_pertek" not in result.project_obligations
    assert "prior_water_pertek_or_initial_application_route" in result.evidence_gaps


def test_inverse_hierarchy_and_provisions(case, release):
    facts = prepare_facts(case())
    result = infer(facts, release)
    assert any(t.predicate.endswith("#isActivityOf") for t in result.core_inferred_triples)
    assert any(t.predicate.endswith("#hasTechnicalChange") for t in result.core_inferred_triples)
    assert any("SupportingActivity" in c and "Activity" in c for c in result.classifications.values())
    sources = {s for trace in result.source_traces for s in trace["sources"]}
    assert {"PP22:89-90", "P5:15", "P5:16.1.a", "P5:3"} <= sources

