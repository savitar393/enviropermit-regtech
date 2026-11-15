from __future__ import annotations

import json
from pathlib import Path

from enviropermit.assessment import assess
from enviropermit.composition import compose
from enviropermit.contracts import (
    Applicability,
    CaseSnapshot,
    Observation,
    ScenarioChange,
)
from enviropermit.scenarios import compare, fork_scenario
from enviropermit.sources import load_registry, select_release

ROOT = Path(__file__).resolve().parents[1]


def _load_snapshot(name: str) -> CaseSnapshot:
    return CaseSnapshot.model_validate(
        json.loads((ROOT / "cases/development" / name).read_text(encoding="utf-8"))
    )


def _assess_composed(snapshot: CaseSnapshot):
    release = select_release(snapshot, load_registry())
    return compose(assess(snapshot, release))


def test_removed_source_does_not_leave_stale_obligation() -> None:
    base = _load_snapshot("demo_a.json")
    base_result = _assess_composed(base)
    assert any(
        item.subject_id == "air-1" and item.applicability == Applicability.APPLICABLE
        for item in base_result.obligation_assessments
    )

    forked = fork_scenario(
        base,
        [
            ScenarioChange(
                subject_id="air-1",
                field="activity",
                operation="REMOVE",
                old_value="air-1",
                new_value=None,
            )
        ],
        scenario_id="scenario-demo-a-no-air",
        assessment_id="assessment-demo-a-no-air",
        evidence_snapshot_id="snapshot-demo-a-no-air",
    )

    assert forked.context.assessment_id != base.context.assessment_id
    assert forked.context.scenario_id != base.context.scenario_id
    assert forked.context.evidence_snapshot_id != base.context.evidence_snapshot_id
    assert all(act.id != "air-1" for act in forked.activities)
    assert all(obs.subject_id != "air-1" for obs in forked.observations)
    assert all(obs.context == forked.context for obs in forked.observations)
    assert all(meas.context == forked.context for meas in forked.measurements)

    forked_result = _assess_composed(forked)
    assert all(item.subject_id != "air-1" for item in forked_result.obligation_assessments)

    diff = compare(base_result, forked_result)
    assert any(
        change.subject_id == "air-1" and change.change_kind == "REMOVED"
        for change in diff.removed_obligations
    )


def test_shared_goal_different_configuration() -> None:
    base = _load_snapshot("demo_a.json")
    forked = fork_scenario(
        base,
        [
            ScenarioChange(
                subject_id="air-1",
                field="stationary_emission",
                operation="SET",
                old_value=True,
                new_value=False,
            ),
            ScenarioChange(
                subject_id="air-1",
                field="existing_emission_pertek",
                operation="SET",
                old_value=True,
                new_value=False,
            ),
            ScenarioChange(
                subject_id="air-1",
                field="emission_change",
                operation="SET",
                old_value="BoilerAddition",
                new_value=None,
            ),
            ScenarioChange(
                subject_id="air-1",
                field="observations",
                operation="REMOVE",
                old_value="obs-air-a",
                new_value=None,
            ),
            ScenarioChange(
                subject_id="air-1",
                field="observations",
                operation="ADD",
                old_value=None,
                new_value=Observation(
                    id="obs-air-fork-electric",
                    context=base.context,
                    subject_id="air-1",
                    scope_id="boiler-stack-1",
                    period_id=base.period_id,
                    non_emitting_source=(True,),
                    origin="OBSERVED",
                ),
                evidence_ids=("obs-air-fork-electric",),
            ),
        ],
        scenario_id="scenario-demo-b-forked",
        assessment_id="assessment-demo-b-forked",
        evidence_snapshot_id="snapshot-demo-b-forked",
    )

    assert forked.goal == base.goal
    base_result = _assess_composed(base)
    forked_result = _assess_composed(forked)
    diff = compare(base_result, forked_result)

    assert diff.shared_goal is True
    assert diff.same_kb_version is True
    assert len(diff.input_changes) > 0
    assert any(
        change.subject_id == "air-1"
        and change.obligation_kind == "emission_pertek_required"
        and change.right_applicability == Applicability.NOT_APPLICABLE
        and change.is_obligation_saving is True
        for change in diff.removed_obligations
    )
    assert any(
        change.subject_id == "water-1" and change.change_kind == "UNCHANGED"
        for change in diff.unchanged_obligations
    )
    assert any(
        change.subject_id == "food-project" and change.change_kind == "UNCHANGED"
        for change in diff.unchanged_obligations
    )


def test_different_kb_versions_are_flagged() -> None:
    demo_a = _load_snapshot("demo_a.json")
    demo_b = _load_snapshot("demo_b.json")
    res_a = _assess_composed(demo_a)
    res_b = _assess_composed(demo_b).model_copy(update={"kb_version": "t1-water-spike-v1"})

    diff = compare(res_a, res_b)
    assert diff.same_kb_version is False
    assert diff.left_kb_version == "t1-water-spike-v2"
    assert diff.right_kb_version == "t1-water-spike-v1"
    assert diff.kb_version_warning is not None
    assert "t1-water-spike-v2" in diff.kb_version_warning
    assert "t1-water-spike-v1" in diff.kb_version_warning


def test_demo_a_b_c_comparison_distinguishes_evidenced_reduction_from_unresolved() -> None:
    res_a = _assess_composed(_load_snapshot("demo_a.json"))
    res_b = _assess_composed(_load_snapshot("demo_b.json"))
    res_c = _assess_composed(_load_snapshot("demo_c.json"))

    diff_ab = compare(res_a, res_b)
    assert diff_ab.shared_goal is True
    assert any(
        change.subject_id == "air-1"
        and change.is_obligation_saving is True
        and "obs-air-b-electric" in change.evidence_ids
        for change in diff_ab.removed_obligations
    )

    diff_ac = compare(res_a, res_c)
    assert diff_ac.shared_goal is True
    water_study_changes = [
        change
        for change in diff_ac.obligation_changes
        if change.subject_id == "water-1" and change.obligation_kind == "prepare_technical_study"
    ]
    assert len(water_study_changes) == 1
    water_change = water_study_changes[0]
    assert water_change.change_kind == "BECAME_UNRESOLVED"
    assert water_change.is_obligation_saving is False
    assert water_change in diff_ac.unresolved_obligations
    assert water_change not in diff_ac.removed_obligations
    assert "UNRESOLVED" in water_change.reason or "belum" in water_change.reason.lower()
    assert len(diff_ac.added_evidence_gaps) > 0
