"""Tests for T6: Approval planning, AND/OR prerequisite groups, and blocker diagnosis."""
from __future__ import annotations

from pathlib import Path

from enviropermit.assessment import assess
from enviropermit.composition import compose
from enviropermit.contracts import CaseSnapshot, Fulfillment, StepStatus
from enviropermit.inference import ROOT
from enviropermit.planning import build_plans
from enviropermit.sources import select_release

SPIKE_CASES = Path(ROOT) / "cases/regression/water_spike"
DEV_CASES = Path(ROOT) / "cases/development"


def _load_spike_case(name: str) -> CaseSnapshot:
    return CaseSnapshot.model_validate_json((SPIKE_CASES / f"{name}.json").read_text(encoding="utf-8"))


def _load_dev_case(filename: str) -> CaseSnapshot:
    return CaseSnapshot.model_validate_json((DEV_CASES / filename).read_text(encoding="utf-8"))


def test_or_group_does_not_require_all_options() -> None:
    # Case B: extent_changes=False -> only prepare_standard_technical_documentation is required
    snapshot_b = _load_spike_case("B")
    plans_b = build_plans(compose(assess(snapshot_b, select_release(snapshot_b))))
    assert len(plans_b) == 1
    plan_b = plans_b[0]
    step_ids_b = {s.template_id for s in plan_b.action_instances}
    assert "prepare_standard_technical_documentation" in step_ids_b
    assert "prepare_technical_study" not in step_ids_b
    assert any(rg.operator == "ANY_OF" for rg in plan_b.prerequisite_groups)
    assert all(edge.provision_ids for edge in plan_b.graph_edges)

    # Case U: extent_changes is unknown -> branches into finite OR candidates, never requiring both in one plan
    snapshot_u = _load_spike_case("U")
    plans_u = build_plans(compose(assess(snapshot_u, select_release(snapshot_u))))
    assert len(plans_u) == 2
    for candidate in plans_u:
        templates = {s.template_id for s in candidate.action_instances}
        assert len(
            templates.intersection(
                {"prepare_technical_study", "prepare_standard_technical_documentation"}
            )
        ) == 1


def test_application_does_not_imply_issuance() -> None:
    # Case D: AMDAL allows concurrent submission of water Pertek and environmental change,
    # but issuance of environmental change still requires issuance of water Pertek first.
    snapshot_d = _load_spike_case("D")
    plans_d = build_plans(compose(assess(snapshot_d, select_release(snapshot_d))))
    assert len(plans_d) == 1
    plan = plans_d[0]
    by_template = {s.template_id: s for s in plan.action_instances}

    submit_water = by_template["submit_water_pertek_change"]
    issued_water = by_template["water_pertek_change_issued"]
    submit_env = by_template["submit_environmental_change"]
    issued_env = by_template["environmental_change_issued"]

    assert submit_water.kind == "ACTION"
    assert issued_water.kind == "MILESTONE"
    assert issued_water.observed_fulfillment == Fulfillment.UNKNOWN
    assert issued_water.status == StepStatus.WAITING_FOR_PREDECESSOR
    assert submit_water.id in issued_water.predecessor_ids
    assert all(eff.startswith("EXPECTED_EFFECT:") for eff in submit_water.expected_effects)

    # Concurrent submission permitted in AMDAL: submit_env does not wait on submit_water
    assert submit_water.id not in submit_env.predecessor_ids
    # But environmental_change_issued MUST wait on water_pertek_change_issued (and transitively submit_water)
    assert issued_water.id in issued_env.predecessor_ids
    assert submit_water.id in issued_env.transitive_predecessor_ids
    assert issued_env.observed_fulfillment == Fulfillment.UNKNOWN


def test_unknown_prerequisite_requests_evidence() -> None:
    snapshot_u = _load_spike_case("U")
    plans = build_plans(compose(assess(snapshot_u, select_release(snapshot_u))))
    assert plans
    for plan in plans:
        evidence_steps = [s for s in plan.action_instances if s.stage == "EVIDENCE_ACQUISITION"]
        assert evidence_steps
        assert all(s.status == StepStatus.AVAILABLE_NOW for s in evidence_steps)

        assert plan.blockers
        water_blocker = next(
            b for b in plan.blockers if b.subject_id == "water-1" and b.scope_id == "outlet-1"
        )
        assert water_blocker.status == "NEEDS_EVIDENCE"
        assert "impact_extent_assessment" in water_blocker.missing_evidence
        assert water_blocker.reason
        assert set(water_blocker.provision_ids).intersection({"P5:16.1.a", "P5:16.1.b"})


def test_cycle_reports_conflicting_dependencies() -> None:
    snapshot_a = _load_spike_case("A")
    assessed = compose(assess(snapshot_a, select_release(snapshot_a)))
    # Inject a cyclic precedence edge opposite to ukl_application_order
    cyclic_precedence = assessed.precedence + (
        ("submit_environmental_change", "submit_water_pertek_change"),
    )
    cyclic_result = assessed.model_copy(update={"precedence": cyclic_precedence})

    plans = build_plans(cyclic_result)
    assert len(plans) == 1
    plan = plans[0]
    assert not plan.consistent
    assert plan.topological_order == ()
    assert any(b.status == "CONFLICTING_DEPENDENCIES" for b in plan.blockers)


def test_water_and_air_parallel_branches_converge_on_environmental_issuance() -> None:
    snapshot = _load_dev_case("media_water_and_air.json")
    plans = build_plans(compose(assess(snapshot, select_release(snapshot))))
    assert len(plans) == 1
    plan = plans[0]
    assert plan.consistent
    assert all(edge.provision_ids for edge in plan.graph_edges)

    by_template = {s.template_id: s for s in plan.action_instances}
    issued_env = by_template["environmental_change_issued"]
    assert by_template["water_pertek_change_issued"].id in issued_env.predecessor_ids
    assert by_template["emission_pertek_change_issued"].id in issued_env.predecessor_ids

    # Both technical studies are available immediately in the first parallel wave
    first_wave = set(plan.parallel_groups[0])
    assert by_template["prepare_technical_study"].id in first_wave
    assert by_template["prepare_emission_technical_study"].id in first_wave
