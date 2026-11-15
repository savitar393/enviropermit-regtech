"""Scenario forking and side-by-side comparison without cross-snapshot leakage."""
from __future__ import annotations

from collections.abc import Sequence
from uuid import uuid4

from .contracts import (
    Activity,
    Applicability,
    AssessmentResult,
    CaseSnapshot,
    Fulfillment,
    Measurement,
    ObligationAssessment,
    ObligationChange,
    Observation,
    PlanDiffSummary,
    ReasoningContext,
    ScenarioChange,
    ScenarioDiff,
)
from .planning import build_plans


def fork_scenario(
    base: CaseSnapshot,
    changes: Sequence[ScenarioChange],
    *,
    scenario_id: str | None = None,
    assessment_id: str | None = None,
    evidence_snapshot_id: str | None = None,
) -> CaseSnapshot:
    suffix = uuid4().hex[:8]
    new_scenario_id = scenario_id or f"{base.context.scenario_id}-fork-{suffix}"
    new_assessment_id = assessment_id or f"{base.context.assessment_id}-fork-{suffix}"
    new_snapshot_id = evidence_snapshot_id or f"{base.context.evidence_snapshot_id}-fork-{suffix}"

    if new_scenario_id == base.context.scenario_id:
        new_scenario_id = f"{new_scenario_id}-fork-{suffix}"
    if new_assessment_id == base.context.assessment_id:
        new_assessment_id = f"{new_assessment_id}-fork-{suffix}"
    if new_snapshot_id == base.context.evidence_snapshot_id:
        new_snapshot_id = f"{new_snapshot_id}-fork-{suffix}"

    new_context = ReasoningContext(
        assessment_id=new_assessment_id,
        scenario_id=new_scenario_id,
        evidence_snapshot_id=new_snapshot_id,
        assessed_on=base.context.assessed_on,
        kb_release_id=base.context.kb_release_id,
    )

    activities: list[Activity] = list(base.activities)
    observations: list[Observation] = list(base.observations)
    measurements: list[Measurement] = list(base.measurements)
    top_updates: dict[str, object] = {}

    for change in changes:
        field = change.field
        op = change.operation
        subj = change.subject_id

        if field in ("activity", "activities"):
            if op == "REMOVE":
                target_id = str(change.old_value) if change.old_value is not None else subj
                activities = [act for act in activities if act.id != target_id and act.id != subj]
                observations = [
                    obs for obs in observations if obs.subject_id != target_id and obs.subject_id != subj
                ]
                measurements = [
                    meas
                    for meas in measurements
                    if meas.subject_id != target_id and meas.subject_id != subj
                ]
            elif op == "ADD":
                new_act = (
                    change.new_value
                    if isinstance(change.new_value, Activity)
                    else Activity.model_validate(change.new_value)
                )
                activities.append(new_act)
            elif op == "SET":
                new_act = (
                    change.new_value
                    if isinstance(change.new_value, Activity)
                    else Activity.model_validate(change.new_value)
                )
                activities = [new_act if act.id == subj else act for act in activities]
            continue

        if field in ("observation", "observations"):
            if op == "REMOVE":
                target_obs_id = str(change.old_value) if change.old_value is not None else None
                if target_obs_id is not None:
                    observations = [obs for obs in observations if obs.id != target_obs_id]
                else:
                    observations = [obs for obs in observations if obs.subject_id != subj]
            elif op == "ADD":
                raw_obs = (
                    change.new_value
                    if isinstance(change.new_value, Observation)
                    else Observation.model_validate(change.new_value)
                )
                observations.append(raw_obs.model_copy(update={"context": new_context}))
            elif op == "SET":
                raw_obs = (
                    change.new_value
                    if isinstance(change.new_value, Observation)
                    else Observation.model_validate(change.new_value)
                )
                updated_obs = raw_obs.model_copy(update={"context": new_context})
                target_obs_id = str(change.old_value) if change.old_value is not None else updated_obs.id
                replaced = False
                new_obs_list: list[Observation] = []
                for obs in observations:
                    if obs.id == target_obs_id or (change.old_value is None and obs.subject_id == subj):
                        new_obs_list.append(updated_obs)
                        replaced = True
                    else:
                        new_obs_list.append(obs)
                if not replaced:
                    new_obs_list.append(updated_obs)
                observations = new_obs_list
            continue

        if field in ("measurement", "measurements"):
            if op == "REMOVE":
                target_meas_id = str(change.old_value) if change.old_value is not None else None
                if target_meas_id is not None:
                    measurements = [meas for meas in measurements if meas.id != target_meas_id]
                else:
                    measurements = [meas for meas in measurements if meas.subject_id != subj]
            elif op == "ADD":
                raw_meas = (
                    change.new_value
                    if isinstance(change.new_value, Measurement)
                    else Measurement.model_validate(change.new_value)
                )
                measurements.append(raw_meas.model_copy(update={"context": new_context}))
            elif op == "SET":
                raw_meas = (
                    change.new_value
                    if isinstance(change.new_value, Measurement)
                    else Measurement.model_validate(change.new_value)
                )
                updated_meas = raw_meas.model_copy(update={"context": new_context})
                target_meas_id = (
                    str(change.old_value) if change.old_value is not None else updated_meas.id
                )
                replaced = False
                new_meas_list: list[Measurement] = []
                for meas in measurements:
                    if meas.id == target_meas_id or (
                        change.old_value is None and meas.subject_id == subj
                    ):
                        new_meas_list.append(updated_meas)
                        replaced = True
                    else:
                        new_meas_list.append(meas)
                if not replaced:
                    new_meas_list.append(updated_meas)
                measurements = new_meas_list
            continue

        matched_activity = False
        for idx, act in enumerate(activities):
            if act.id == subj and hasattr(act, field):
                activities[idx] = act.model_copy(update={field: change.new_value})
                matched_activity = True
                break
        if matched_activity:
            continue

        if hasattr(base, field):
            if op == "SET":
                top_updates[field] = change.new_value
            elif op == "ADD":
                current = list(getattr(base, field) or ())
                if change.new_value not in current:
                    current.append(change.new_value)
                top_updates[field] = tuple(current)
            elif op == "REMOVE":
                current = [item for item in (getattr(base, field) or ()) if item != change.old_value]
                top_updates[field] = tuple(current)

    scoped_observations = tuple(obs.model_copy(update={"context": new_context}) for obs in observations)
    scoped_measurements = tuple(
        meas.model_copy(update={"context": new_context}) for meas in measurements
    )

    update_payload: dict[str, object] = {
        **top_updates,
        "context": new_context,
        "activities": tuple(activities),
        "observations": scoped_observations,
        "measurements": scoped_measurements,
    }
    return base.model_copy(update=update_payload)


def _diff_snapshots(left: CaseSnapshot | None, right: CaseSnapshot | None) -> tuple[ScenarioChange, ...]:
    if left is None or right is None:
        return ()

    changes: list[ScenarioChange] = []
    for top_field in (
        "goal",
        "location",
        "project_changes",
        "changes_complete",
        "screening",
        "existing_environmental_approval",
        "outsourcing_claim",
    ):
        l_val = getattr(left, top_field)
        r_val = getattr(right, top_field)
        if l_val != r_val:
            changes.append(
                ScenarioChange(
                    subject_id=left.project_id,
                    field=top_field,
                    operation="SET",
                    old_value=l_val,
                    new_value=r_val,
                )
            )

    left_acts = {act.id: act for act in left.activities}
    right_acts = {act.id: act for act in right.activities}
    for act_id in sorted(set(left_acts) | set(right_acts)):
        l_act = left_acts.get(act_id)
        r_act = right_acts.get(act_id)
        if l_act is not None and r_act is None:
            changes.append(
                ScenarioChange(
                    subject_id=act_id,
                    field="activity",
                    operation="REMOVE",
                    old_value=act_id,
                    new_value=None,
                )
            )
        elif l_act is None and r_act is not None:
            changes.append(
                ScenarioChange(
                    subject_id=act_id,
                    field="activity",
                    operation="ADD",
                    old_value=None,
                    new_value=act_id,
                )
            )
        elif l_act is not None and r_act is not None:
            for act_field in (
                "kind",
                "scope_id",
                "kbli",
                "surface_discharge",
                "existing_water_pertek",
                "water_change",
                "stationary_emission",
                "existing_emission_pertek",
                "emission_change",
            ):
                lv = getattr(l_act, act_field)
                rv = getattr(r_act, act_field)
                if lv != rv:
                    changes.append(
                        ScenarioChange(
                            subject_id=act_id,
                            field=act_field,
                            operation="SET",
                            old_value=lv,
                            new_value=rv,
                        )
                    )

    obs_fields = (
        "extent_changes",
        "in_protected_area",
        "protected_area_exception",
        "non_emitting_source",
    )
    all_subjects = sorted(
        {obs.subject_id for obs in left.observations}
        | {obs.subject_id for obs in right.observations}
    )
    for subj_id in all_subjects:
        l_subj_obs = [obs for obs in left.observations if obs.subject_id == subj_id]
        r_subj_obs = [obs for obs in right.observations if obs.subject_id == subj_id]
        for obs_field in obs_fields:
            l_vals = tuple(v for obs in l_subj_obs for v in getattr(obs, obs_field))
            r_vals = tuple(v for obs in r_subj_obs for v in getattr(obs, obs_field))
            if l_vals != r_vals:
                ev_ids = tuple(
                    sorted(
                        {
                            obs.id
                            for obs in (*l_subj_obs, *r_subj_obs)
                            if getattr(obs, obs_field)
                        }
                    )
                )
                op = "SET"
                if not l_vals and r_vals:
                    op = "ADD"
                elif l_vals and not r_vals:
                    op = "REMOVE"
                changes.append(
                    ScenarioChange(
                        subject_id=subj_id,
                        field=obs_field,
                        operation=op,
                        old_value=l_vals or None,
                        new_value=r_vals or None,
                        evidence_ids=ev_ids,
                    )
                )

    return tuple(changes)


def _compare_plans(left: AssessmentResult, right: AssessmentResult) -> PlanDiffSummary:
    left_plans = build_plans(left)
    right_plans = build_plans(right)
    if not left_plans and not right_plans:
        return PlanDiffSummary()

    left_steps = {
        step.id: step.status
        for plan in left_plans[:1]
        for step in plan.action_instances
    }
    right_steps = {
        step.id: step.status
        for plan in right_plans[:1]
        for step in plan.action_instances
    }
    added_steps = tuple(sorted(set(right_steps) - set(left_steps)))
    removed_steps = tuple(sorted(set(left_steps) - set(right_steps)))
    changed_statuses = {
        step_id: (left_steps[step_id], right_steps[step_id])
        for step_id in sorted(set(left_steps) & set(right_steps))
        if left_steps[step_id] != right_steps[step_id]
    }

    left_blockers = {
        f"{b.step_id}:{b.status}" for plan in left_plans[:1] for b in plan.blockers
    }
    right_blockers = {
        f"{b.step_id}:{b.status}" for plan in right_plans[:1] for b in plan.blockers
    }
    return PlanDiffSummary(
        added_steps=added_steps,
        removed_steps=removed_steps,
        changed_step_statuses=changed_statuses,
        added_blockers=tuple(sorted(right_blockers - left_blockers)),
        removed_blockers=tuple(sorted(left_blockers - right_blockers)),
    )


def compare(left: AssessmentResult, right: AssessmentResult) -> ScenarioDiff:
    same_kb_version = left.kb_version == right.kb_version
    kb_version_warning = None
    if not same_kb_version:
        kb_version_warning = (
            f"Peringatan versi KB: skenario kiri menggunakan '{left.kb_version}' sedangkan "
            f"skenario kanan menggunakan '{right.kb_version}'. Perbedaan hasil dapat berasal "
            "dari perubahan aturan, bukan semata-mata perubahan konfigurasi proyek."
        )

    shared_goal = True
    if left.snapshot is not None and right.snapshot is not None:
        shared_goal = left.snapshot.goal == right.snapshot.goal

    input_changes = _diff_snapshots(left.snapshot, right.snapshot)

    def _norm_subj(oa: ObligationAssessment, res: AssessmentResult) -> str:
        return oa.scope_id if oa.subject_id == res.context.scenario_id else oa.subject_id

    left_map: dict[tuple[str, str, str], ObligationAssessment] = {
        (_norm_subj(oa, left), oa.scope_id, oa.obligation_kind): oa
        for oa in left.obligation_assessments
    }
    right_map: dict[tuple[str, str, str], ObligationAssessment] = {
        (_norm_subj(oa, right), oa.scope_id, oa.obligation_kind): oa
        for oa in right.obligation_assessments
    }

    right_exempt_by_scope: dict[tuple[str, str], list[ObligationAssessment]] = {}
    right_unresolved_by_scope: dict[tuple[str, str], list[ObligationAssessment]] = {}
    for oa in right.obligation_assessments:
        norm_s = _norm_subj(oa, right)
        if oa.applicability == Applicability.NOT_APPLICABLE:
            right_exempt_by_scope.setdefault((norm_s, oa.scope_id), []).append(oa)
        elif oa.applicability == Applicability.UNRESOLVED:
            right_unresolved_by_scope.setdefault((norm_s, oa.scope_id), []).append(oa)

    left_unresolved_by_scope: dict[tuple[str, str], list[ObligationAssessment]] = {}
    for oa in left.obligation_assessments:
        norm_s = _norm_subj(oa, left)
        if oa.applicability == Applicability.UNRESOLVED:
            left_unresolved_by_scope.setdefault((norm_s, oa.scope_id), []).append(oa)

    right_decision_branches: dict[str, tuple[str, ...]] = {
        d.id: d.branches for d in right.decisions if d.applicability == Applicability.UNRESOLVED
    }
    left_decision_branches: dict[str, tuple[str, ...]] = {
        d.id: d.branches for d in left.decisions if d.applicability == Applicability.UNRESOLVED
    }

    consumed_right_synthetic: set[tuple[str, str, str]] = set()
    consumed_left_synthetic: set[tuple[str, str, str]] = set()

    obligation_changes: list[ObligationChange] = []
    added_obligations: list[ObligationChange] = []
    removed_obligations: list[ObligationChange] = []
    changed_obligations: list[ObligationChange] = []
    unresolved_obligations: list[ObligationChange] = []
    unchanged_obligations: list[ObligationChange] = []

    all_keys = sorted(set(left_map) | set(right_map))
    for key in all_keys:
        subj_id, scope_id, ob_kind = key
        l_oa = left_map.get(key)
        r_oa = right_map.get(key)

        if l_oa is not None and r_oa is not None:
            provisions = tuple(sorted(set(l_oa.provision_ids) | set(r_oa.provision_ids)))
            evidences = tuple(sorted(set(l_oa.evidence_ids) | set(r_oa.evidence_ids)))
            if (
                l_oa.applicability == r_oa.applicability
                and l_oa.fulfillment == r_oa.fulfillment
            ):
                change = ObligationChange(
                    subject_id=subj_id,
                    scope_id=scope_id,
                    obligation_kind=ob_kind,
                    change_kind="UNCHANGED",
                    left_applicability=l_oa.applicability,
                    right_applicability=r_oa.applicability,
                    left_fulfillment=l_oa.fulfillment,
                    right_fulfillment=r_oa.fulfillment,
                    reason=(
                        f"Status kewajiban '{ob_kind}' pada {subj_id} ({scope_id}) "
                        f"tetap {r_oa.applicability}/{r_oa.fulfillment}."
                    ),
                    is_obligation_saving=False,
                    provision_ids=provisions,
                    evidence_ids=evidences,
                )
                obligation_changes.append(change)
                unchanged_obligations.append(change)
                if r_oa.applicability == Applicability.UNRESOLVED:
                    unresolved_obligations.append(change)
            elif r_oa.applicability == Applicability.UNRESOLVED:
                change = ObligationChange(
                    subject_id=subj_id,
                    scope_id=scope_id,
                    obligation_kind=ob_kind,
                    change_kind="BECAME_UNRESOLVED",
                    left_applicability=l_oa.applicability,
                    right_applicability=r_oa.applicability,
                    left_fulfillment=l_oa.fulfillment,
                    right_fulfillment=r_oa.fulfillment,
                    reason=(
                        f"Kewajiban '{ob_kind}' pada {subj_id} ({scope_id}) menjadi UNRESOLVED "
                        "karena bukti prasyarat cabang keputusan belum tersedia; bukan penghematan kewajiban."
                    ),
                    is_obligation_saving=False,
                    provision_ids=provisions,
                    evidence_ids=evidences,
                )
                obligation_changes.append(change)
                unresolved_obligations.append(change)
            elif (
                l_oa.applicability == Applicability.UNRESOLVED
                and r_oa.applicability != Applicability.UNRESOLVED
            ):
                is_saving = r_oa.applicability == Applicability.NOT_APPLICABLE
                change = ObligationChange(
                    subject_id=subj_id,
                    scope_id=scope_id,
                    obligation_kind=ob_kind,
                    change_kind="RESOLVED_FROM_UNRESOLVED",
                    left_applicability=l_oa.applicability,
                    right_applicability=r_oa.applicability,
                    left_fulfillment=l_oa.fulfillment,
                    right_fulfillment=r_oa.fulfillment,
                    reason=(
                        f"Keputusan '{ob_kind}' pada {subj_id} ({scope_id}) yang semula UNRESOLVED "
                        f"kini terkonfirmasi menjadi {r_oa.applicability}."
                    ),
                    is_obligation_saving=is_saving,
                    provision_ids=provisions,
                    evidence_ids=evidences,
                )
                obligation_changes.append(change)
                changed_obligations.append(change)
            else:
                is_saving = (
                    l_oa.applicability == Applicability.APPLICABLE
                    and r_oa.applicability == Applicability.NOT_APPLICABLE
                )
                change = ObligationChange(
                    subject_id=subj_id,
                    scope_id=scope_id,
                    obligation_kind=ob_kind,
                    change_kind="CHANGED_STATUS",
                    left_applicability=l_oa.applicability,
                    right_applicability=r_oa.applicability,
                    left_fulfillment=l_oa.fulfillment,
                    right_fulfillment=r_oa.fulfillment,
                    reason=(
                        f"Status '{ob_kind}' pada {subj_id} ({scope_id}) berubah dari "
                        f"{l_oa.applicability}/{l_oa.fulfillment} menjadi "
                        f"{r_oa.applicability}/{r_oa.fulfillment}."
                    ),
                    is_obligation_saving=is_saving,
                    provision_ids=provisions,
                    evidence_ids=evidences,
                )
                obligation_changes.append(change)
                changed_obligations.append(change)
            continue

        if l_oa is not None and r_oa is None:
            if l_oa.applicability in (Applicability.UNRESOLVED, Applicability.NOT_APPLICABLE):
                if key in consumed_left_synthetic:
                    continue

            scope_unresolved = right_unresolved_by_scope.get((subj_id, scope_id), [])
            matching_unresolved: list[ObligationAssessment] = []
            for unres_oa in scope_unresolved:
                branches = set(right_decision_branches.get(unres_oa.obligation_kind, ()))
                if branches and set(l_oa.rule_ids).intersection(branches):
                    matching_unresolved.append(unres_oa)
            if not matching_unresolved and scope_unresolved and l_oa.obligation_kind.startswith("prepare_"):
                matching_unresolved = list(scope_unresolved)

            if matching_unresolved:
                for unres_oa in matching_unresolved:
                    consumed_right_synthetic.add(
                        (_norm_subj(unres_oa, right), unres_oa.scope_id, unres_oa.obligation_kind)
                    )
                provisions = tuple(
                    sorted(
                        set(l_oa.provision_ids)
                        | {p for u in matching_unresolved for p in u.provision_ids}
                    )
                )
                evidences = tuple(
                    sorted(
                        set(l_oa.evidence_ids)
                        | {e for u in matching_unresolved for e in u.evidence_ids}
                    )
                )
                change = ObligationChange(
                    subject_id=subj_id,
                    scope_id=scope_id,
                    obligation_kind=ob_kind,
                    change_kind="BECAME_UNRESOLVED",
                    left_applicability=l_oa.applicability,
                    right_applicability=Applicability.UNRESOLVED,
                    left_fulfillment=l_oa.fulfillment,
                    right_fulfillment=Fulfillment.UNKNOWN,
                    reason=(
                        f"Kewajiban '{ob_kind}' pada {subj_id} ({scope_id}) belum dapat ditentukan "
                        "(UNRESOLVED) pada skenario kanan karena bukti penentu cabang keputusan "
                        "belum tersedia; tidak dihitung sebagai penghematan kewajiban."
                    ),
                    is_obligation_saving=False,
                    provision_ids=provisions,
                    evidence_ids=evidences,
                )
                obligation_changes.append(change)
                unresolved_obligations.append(change)
                continue

            scope_exempt = right_exempt_by_scope.get((subj_id, scope_id), [])
            if scope_exempt:
                for ex_oa in scope_exempt:
                    consumed_right_synthetic.add(
                        (_norm_subj(ex_oa, right), ex_oa.scope_id, ex_oa.obligation_kind)
                    )
                provisions = tuple(
                    sorted(
                        set(l_oa.provision_ids)
                        | {p for ex in scope_exempt for p in ex.provision_ids}
                    )
                )
                evidences = tuple(
                    sorted(
                        set(l_oa.evidence_ids)
                        | {e for ex in scope_exempt for e in ex.evidence_ids}
                    )
                )
                change = ObligationChange(
                    subject_id=subj_id,
                    scope_id=scope_id,
                    obligation_kind=ob_kind,
                    change_kind="REMOVED",
                    left_applicability=l_oa.applicability,
                    right_applicability=Applicability.NOT_APPLICABLE,
                    left_fulfillment=l_oa.fulfillment,
                    right_fulfillment=Fulfillment.SATISFIED,
                    reason=(
                        f"Kewajiban '{ob_kind}' pada {subj_id} ({scope_id}) tidak lagi berlaku "
                        "(NOT_APPLICABLE) karena terbukti memenuhi syarat pengecualian eksplisit."
                    ),
                    is_obligation_saving=True,
                    provision_ids=provisions,
                    evidence_ids=evidences,
                )
                obligation_changes.append(change)
                removed_obligations.append(change)
                continue

            change = ObligationChange(
                subject_id=subj_id,
                scope_id=scope_id,
                obligation_kind=ob_kind,
                change_kind="REMOVED",
                left_applicability=l_oa.applicability,
                right_applicability=None,
                left_fulfillment=l_oa.fulfillment,
                right_fulfillment=None,
                reason=(
                    f"Kewajiban '{ob_kind}' pada {subj_id} ({scope_id}) tidak lagi muncul karena "
                    "kegiatan atau pemicu teknis terkait dihapus pada skenario kanan."
                ),
                is_obligation_saving=l_oa.applicability == Applicability.APPLICABLE,
                provision_ids=l_oa.provision_ids,
                evidence_ids=l_oa.evidence_ids,
            )
            obligation_changes.append(change)
            removed_obligations.append(change)
            continue

        if l_oa is None and r_oa is not None:
            if key in consumed_right_synthetic:
                continue

            if r_oa.applicability == Applicability.UNRESOLVED:
                change = ObligationChange(
                    subject_id=subj_id,
                    scope_id=scope_id,
                    obligation_kind=ob_kind,
                    change_kind="BECAME_UNRESOLVED",
                    left_applicability=None,
                    right_applicability=Applicability.UNRESOLVED,
                    left_fulfillment=None,
                    right_fulfillment=Fulfillment.UNKNOWN,
                    reason=(
                        f"Keputusan '{ob_kind}' pada {subj_id} ({scope_id}) masih UNRESOLVED "
                        "karena bukti belum lengkap."
                    ),
                    is_obligation_saving=False,
                    provision_ids=r_oa.provision_ids,
                    evidence_ids=r_oa.evidence_ids,
                )
                obligation_changes.append(change)
                unresolved_obligations.append(change)
                continue

            scope_left_unres = left_unresolved_by_scope.get((subj_id, scope_id), [])
            matching_left_unres: list[ObligationAssessment] = []
            for unres_oa in scope_left_unres:
                branches = set(left_decision_branches.get(unres_oa.obligation_kind, ()))
                if branches and set(r_oa.rule_ids).intersection(branches):
                    matching_left_unres.append(unres_oa)
            if matching_left_unres:
                for unres_oa in matching_left_unres:
                    consumed_left_synthetic.add(
                        (_norm_subj(unres_oa, left), unres_oa.scope_id, unres_oa.obligation_kind)
                    )
                provisions = tuple(
                    sorted(
                        set(r_oa.provision_ids)
                        | {p for u in matching_left_unres for p in u.provision_ids}
                    )
                )
                evidences = tuple(
                    sorted(
                        set(r_oa.evidence_ids)
                        | {e for u in matching_left_unres for e in u.evidence_ids}
                    )
                )
                change = ObligationChange(
                    subject_id=subj_id,
                    scope_id=scope_id,
                    obligation_kind=ob_kind,
                    change_kind="RESOLVED_FROM_UNRESOLVED",
                    left_applicability=Applicability.UNRESOLVED,
                    right_applicability=r_oa.applicability,
                    left_fulfillment=Fulfillment.UNKNOWN,
                    right_fulfillment=r_oa.fulfillment,
                    reason=(
                        f"Kewajiban '{ob_kind}' pada {subj_id} ({scope_id}) terkonfirmasi setelah "
                        "bukti yang semula kurang dilengkapi pada skenario kanan."
                    ),
                    is_obligation_saving=r_oa.applicability == Applicability.NOT_APPLICABLE,
                    provision_ids=provisions,
                    evidence_ids=evidences,
                )
                obligation_changes.append(change)
                changed_obligations.append(change)
                continue

            change = ObligationChange(
                subject_id=subj_id,
                scope_id=scope_id,
                obligation_kind=ob_kind,
                change_kind="ADDED",
                left_applicability=None,
                right_applicability=r_oa.applicability,
                left_fulfillment=None,
                right_fulfillment=r_oa.fulfillment,
                reason=(
                    f"Kewajiban baru '{ob_kind}' pada {subj_id} ({scope_id}) muncul akibat "
                    "konfigurasi kegiatan/perubahan pada skenario kanan."
                ),
                is_obligation_saving=False,
                provision_ids=r_oa.provision_ids,
                evidence_ids=r_oa.evidence_ids,
            )
            obligation_changes.append(change)
            added_obligations.append(change)

    left_gaps = set(left.evidence_gaps)
    right_gaps = set(right.evidence_gaps)
    added_evidence_gaps = tuple(sorted(right_gaps - left_gaps))
    removed_evidence_gaps = tuple(sorted(left_gaps - right_gaps))

    plan_changes = _compare_plans(left, right)

    explanation_links = tuple(
        {
            "subject_id": ch.subject_id,
            "scope_id": ch.scope_id,
            "obligation_kind": ch.obligation_kind,
            "change_kind": ch.change_kind,
            "provision_ids": list(ch.provision_ids),
            "evidence_ids": list(ch.evidence_ids),
        }
        for ch in obligation_changes
        if ch.change_kind != "UNCHANGED"
    )

    return ScenarioDiff(
        left_assessment_id=left.assessment_id,
        right_assessment_id=right.assessment_id,
        left_scenario_id=left.context.scenario_id,
        right_scenario_id=right.context.scenario_id,
        shared_goal=shared_goal,
        same_kb_version=same_kb_version,
        left_kb_version=left.kb_version,
        right_kb_version=right.kb_version,
        kb_version_warning=kb_version_warning,
        input_changes=input_changes,
        obligation_changes=tuple(obligation_changes),
        added_obligations=tuple(added_obligations),
        removed_obligations=tuple(removed_obligations),
        changed_obligations=tuple(changed_obligations),
        unresolved_obligations=tuple(unresolved_obligations),
        unchanged_obligations=tuple(unchanged_obligations),
        added_evidence_gaps=added_evidence_gaps,
        removed_evidence_gaps=removed_evidence_gaps,
        plan_changes=plan_changes,
        explanation_links=explanation_links,
    )
