"""Evidence-aware approval planning, AND/OR prerequisite groups, and blocker diagnosis."""
from __future__ import annotations

from collections import deque
from itertools import product
import json
from pathlib import Path

from .composition import compose
from .contracts import (
    ActionInstance,
    ActionTemplate,
    Applicability,
    AssessmentResult,
    Fulfillment,
    PlanBlocker,
    PlanCandidate,
    PlanEdgeSpec,
    RequirementGroup,
    StepStatus,
)
from .inference import ROOT

_STAGE_ORDER = {
    "EVIDENCE_ACQUISITION": 0,
    "TECHNICAL_DOCUMENTATION": 1,
    "ENVIRONMENTAL_DOCUMENTATION": 2,
    "TECHNICAL_APPROVAL": 3,
    "ENVIRONMENTAL_APPROVAL": 4,
    "POST_APPROVAL_SLO": 5,
}


def load_action_templates(
    path: Path | str = ROOT / "kb/action_templates.json",
) -> tuple[tuple[ActionTemplate, ...], dict[str, dict[str, tuple[str, ...]]]]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    templates = tuple(ActionTemplate.model_validate(item) for item in raw.get("templates", ()))
    edge_sources: dict[str, dict[str, tuple[str, ...]]] = {}
    for key, val in raw.get("precedence_edge_sources", {}).items():
        edge_sources[key] = {
            "provision_ids": tuple(val.get("provision_ids", ())),
            "rule_ids": tuple(val.get("rule_ids", ())),
        }
    return templates, edge_sources


def _compute_topological_waves(
    step_ids: tuple[str, ...],
    stage_by_id: dict[str, str],
    edges: tuple[PlanEdgeSpec, ...],
) -> tuple[bool, tuple[str, ...], tuple[tuple[str, ...], ...], tuple[str, ...]]:
    in_degree = {sid: 0 for sid in step_ids}
    adj: dict[str, list[str]] = {sid: [] for sid in step_ids}
    for edge in edges:
        if edge.before_step_id in adj and edge.after_step_id in in_degree:
            adj[edge.before_step_id].append(edge.after_step_id)
            in_degree[edge.after_step_id] += 1

    def sort_key(sid: str) -> tuple[int, str]:
        return (_STAGE_ORDER.get(stage_by_id.get(sid, ""), 99), sid)

    available = sorted([sid for sid, deg in in_degree.items() if deg == 0], key=sort_key)
    order: list[str] = []
    waves: list[tuple[str, ...]] = []

    while available:
        current_wave = tuple(available)
        waves.append(current_wave)
        next_wave: list[str] = []
        for sid in current_wave:
            order.append(sid)
            for neighbor in adj[sid]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    next_wave.append(neighbor)
        available = sorted(next_wave, key=sort_key)

    if len(order) < len(step_ids):
        cycle_nodes = tuple(sorted(sid for sid in step_ids if sid not in set(order)))
        return False, (), (), cycle_nodes

    return True, tuple(order), tuple(waves), ()


def _compute_transitive_predecessors(
    step_ids: tuple[str, ...],
    edges: tuple[PlanEdgeSpec, ...],
) -> dict[str, tuple[str, ...]]:
    direct_preds: dict[str, set[str]] = {sid: set() for sid in step_ids}
    for edge in edges:
        if edge.after_step_id in direct_preds and edge.before_step_id in direct_preds:
            direct_preds[edge.after_step_id].add(edge.before_step_id)

    transitive: dict[str, tuple[str, ...]] = {}
    for sid in step_ids:
        visited: set[str] = set()
        queue = deque(direct_preds[sid])
        while queue:
            curr = queue.popleft()
            if curr in visited:
                continue
            visited.add(curr)
            queue.extend(direct_preds.get(curr, ()))
        transitive[sid] = tuple(sorted(visited))
    return transitive


def build_plans(result: AssessmentResult, max_candidates: int = 8) -> list[PlanCandidate]:
    if result.consistency_status != "CONSISTENT":
        return []
    if not result.fulfillment_findings:
        result = compose(result)

    templates, precedence_edge_sources = load_action_templates()
    template_by_id = {t.id: t for t in templates}

    applicable_by_scope: dict[tuple[str, str], dict[str, tuple[str, ...]]] = {}
    fulfillment_by_scope: dict[tuple[str, str], dict[str, Fulfillment]] = {}
    unresolved_by_scope: dict[tuple[str, str], dict[str, tuple[str, ...]]] = {}

    for oa in result.obligation_assessments:
        scope_key = (oa.subject_id, oa.scope_id)
        if oa.applicability == Applicability.APPLICABLE:
            applicable_by_scope.setdefault(scope_key, {})[oa.obligation_kind] = oa.provision_ids
            fulfillment_by_scope.setdefault(scope_key, {})[oa.obligation_kind] = oa.fulfillment
        elif oa.applicability == Applicability.UNRESOLVED:
            unresolved_by_scope.setdefault(scope_key, {})[oa.obligation_kind] = oa.provision_ids

    # Identify ANY_OF requirement groups across active (subject_id, scope_id) pairs
    branch_dimensions: list[tuple[tuple[str, str], RequirementGroup, list[str], bool]] = []
    for scope_key, obs_map in sorted(applicable_by_scope.items()):
        for tpl in templates:
            if not set(tpl.for_obligations).intersection(obs_map):
                continue
            for rg in tpl.requirement_groups:
                if rg.operator != "ANY_OF":
                    continue
                matched = [
                    member_id
                    for member_id in rg.member_step_ids
                    if member_id in template_by_id
                    and set(template_by_id[member_id].for_obligations).intersection(obs_map)
                ]
                if matched:
                    branch_dimensions.append((scope_key, rg, matched, False))
                else:
                    branch_dimensions.append((scope_key, rg, list(rg.member_step_ids), True))

    choice_lists = [dim[2] for dim in branch_dimensions] if branch_dimensions else [[]]
    all_combinations = list(product(*choice_lists)) if branch_dimensions else [()]
    truncated = len(all_combinations) > max_candidates
    selected_combinations = all_combinations[:max_candidates]

    candidates: list[PlanCandidate] = []
    for idx, combo in enumerate(selected_combinations, start=1):
        chosen_or_member: dict[tuple[tuple[str, str], str], tuple[str, bool]] = {}
        branch_parts: list[str] = []
        for dim_idx, choice_tpl_id in enumerate(combo):
            scope_key, rg, _, is_unresolved = branch_dimensions[dim_idx]
            chosen_or_member[(scope_key, rg.id)] = (choice_tpl_id, is_unresolved)
            branch_parts.append(f"{scope_key[0]}:{choice_tpl_id}")

        branch_label = ",".join(branch_parts) if branch_parts else "default"

        # Determine which (scope_key, template_id, is_unresolved_choice) pairs are active
        planned_items: list[tuple[tuple[str, str], ActionTemplate, bool]] = []
        or_member_all_ids = {
            m_id for tpl in templates for rg in tpl.requirement_groups for m_id in rg.member_step_ids
        }

        for scope_key, obs_map in sorted(applicable_by_scope.items()):
            for tpl in templates:
                if tpl.id in or_member_all_ids:
                    continue
                if set(tpl.for_obligations).intersection(obs_map):
                    # Skip verify_*_slo if no corresponding amendment is active and pertek is already satisfied
                    if tpl.id == "verify_water_slo" and "amend_water_pertek" not in obs_map:
                        if fulfillment_by_scope.get(scope_key, {}).get("water_pertek_required") == Fulfillment.SATISFIED:
                            continue
                    if tpl.id == "verify_emission_slo" and "amend_emission_pertek" not in obs_map:
                        if fulfillment_by_scope.get(scope_key, {}).get("emission_pertek_required") == Fulfillment.SATISFIED:
                            continue
                    planned_items.append((scope_key, tpl, False))

            for tpl in templates:
                if not set(tpl.for_obligations).intersection(obs_map):
                    continue
                for rg in tpl.requirement_groups:
                    choice_info = chosen_or_member.get((scope_key, rg.id))
                    if choice_info is not None:
                        choice_tpl = template_by_id[choice_info[0]]
                        planned_items.append((scope_key, choice_tpl, choice_info[1]))

        # Count occurrences of each template_id to decide canonical vs scoped step ID
        tpl_counts: dict[str, int] = {}
        for _, tpl, _ in planned_items:
            tpl_counts[tpl.id] = tpl_counts.get(tpl.id, 0) + 1

        def make_step_id(tpl_id: str, scope_key: tuple[str, str]) -> str:
            return tpl_id if tpl_counts.get(tpl_id, 0) <= 1 else f"{tpl_id}:{scope_key[1]}"

        step_map: dict[tuple[tuple[str, str], str], str] = {}
        raw_steps: dict[str, dict] = {}
        prereq_groups: list[RequirementGroup] = []

        for scope_key, tpl, is_unresolved_choice in planned_items:
            sid = make_step_id(tpl.id, scope_key)
            step_map[(scope_key, tpl.id)] = sid
            obs_map = applicable_by_scope.get(scope_key, {})
            provs = set(tpl.supported_by)
            for ob in tpl.for_obligations:
                provs.update(obs_map.get(ob, ()))

            for rg in tpl.requirement_groups:
                scoped_members = tuple(
                    step_map.get((scope_key, m_id), m_id) for m_id in rg.member_step_ids
                )
                prereq_groups.append(
                    RequirementGroup(
                        id=f"{rg.id}:{scope_key[1]}" if tpl_counts.get(tpl.id, 0) > 1 else rg.id,
                        operator=rg.operator,
                        member_step_ids=scoped_members,
                        provision_ids=rg.provision_ids,
                    )
                )

            raw_steps[sid] = {
                "id": sid,
                "template_id": tpl.id,
                "title": tpl.title,
                "subject_id": scope_key[0],
                "scope_id": scope_key[1],
                "stage": tpl.stage,
                "kind": tpl.kind,
                "expected_effects": tpl.expected_effects,
                "required_evidence": tpl.required_evidence,
                "provision_ids": tuple(sorted(provs)),
                "is_unresolved_choice": is_unresolved_choice,
            }

        # Add EVIDENCE_ACQUISITION steps for missing required evidence on planned steps
        edges_dict: dict[tuple[str, str], PlanEdgeSpec] = {}
        gaps_set = set(result.evidence_gaps)

        for sid, sdata in list(raw_steps.items()):
            scope_key = (sdata["subject_id"], sdata["scope_id"])
            missing_for_step = [
                req_ev for req_ev in sdata["required_evidence"] if req_ev in gaps_set
            ]
            if sdata["is_unresolved_choice"] and not missing_for_step:
                # Attach unresolved decision evidence gaps for this subject
                for dec in result.decisions:
                    if dec.subject_id.endswith(f"activity-{scope_key[0]}") and dec.evidence_gaps:
                        missing_for_step.extend(dec.evidence_gaps)
            missing_for_step = sorted(set(missing_for_step))
            sdata["missing_evidence"] = tuple(missing_for_step)

            for gap in missing_for_step:
                acq_id = f"acquire_evidence:{gap}:{scope_key[0]}"
                if acq_id not in raw_steps:
                    raw_steps[acq_id] = {
                        "id": acq_id,
                        "template_id": f"acquire_evidence:{gap}",
                        "title": f"Lengkapi bukti: {gap}",
                        "subject_id": scope_key[0],
                        "scope_id": scope_key[1],
                        "stage": "EVIDENCE_ACQUISITION",
                        "kind": "ACTION",
                        "expected_effects": (f"EXPECTED_EFFECT:evidence_available:{gap}",),
                        "required_evidence": (),
                        "missing_evidence": (),
                        "provision_ids": sdata["provision_ids"],
                        "is_unresolved_choice": False,
                    }
                edge_key = (acq_id, sid)
                edges_dict[edge_key] = PlanEdgeSpec(
                    before_step_id=acq_id,
                    after_step_id=sid,
                    provision_ids=sdata["provision_ids"],
                    rule_ids=(sdata["template_id"],),
                )

        # Add template precondition and requirement group edges
        for scope_key, tpl, _ in planned_items:
            after_sid = step_map[(scope_key, tpl.id)]
            for pre_tpl_id in tpl.preconditions:
                before_sid = step_map.get((scope_key, pre_tpl_id))
                if before_sid:
                    edges_dict[(before_sid, after_sid)] = PlanEdgeSpec(
                        before_step_id=before_sid,
                        after_step_id=after_sid,
                        provision_ids=tpl.supported_by,
                        rule_ids=(tpl.id,),
                    )
            for rg in tpl.requirement_groups:
                choice_info = chosen_or_member.get((scope_key, rg.id))
                if choice_info is not None:
                    before_sid = step_map.get((scope_key, choice_info[0]))
                    if before_sid:
                        edges_dict[(before_sid, after_sid)] = PlanEdgeSpec(
                            before_step_id=before_sid,
                            after_step_id=after_sid,
                            provision_ids=rg.provision_ids or tpl.supported_by,
                            rule_ids=(rg.id,),
                        )

        # Add cross-activity / scenario precedence edges from OWL reasoning
        by_template_id: dict[str, list[str]] = {}
        for sid, sdata in raw_steps.items():
            by_template_id.setdefault(sdata["template_id"], []).append(sid)

        for before_tpl, after_tpl in result.precedence:
            edge_meta = precedence_edge_sources.get(f"{before_tpl}->{after_tpl}", {})
            for b_sid in by_template_id.get(before_tpl, ()):
                for a_sid in by_template_id.get(after_tpl, ()):
                    fallback_provs = tuple(
                        sorted(
                            set(raw_steps[b_sid]["provision_ids"])
                            | set(raw_steps[a_sid]["provision_ids"])
                        )
                    )
                    provs = edge_meta.get("provision_ids") or fallback_provs
                    rules = edge_meta.get("rule_ids") or ("PlanPrecedence",)
                    edges_dict[(b_sid, a_sid)] = PlanEdgeSpec(
                        before_step_id=b_sid,
                        after_step_id=a_sid,
                        provision_ids=provs,
                        rule_ids=rules,
                    )

        sorted_edges = tuple(
            sorted(edges_dict.values(), key=lambda e: (e.before_step_id, e.after_step_id))
        )
        all_step_ids = tuple(sorted(raw_steps))
        stage_by_id = {sid: raw_steps[sid]["stage"] for sid in all_step_ids}

        consistent, topo_order, parallel_waves, cycle_nodes = _compute_topological_waves(
            all_step_ids, stage_by_id, sorted_edges
        )
        trans_preds = (
            _compute_transitive_predecessors(all_step_ids, sorted_edges)
            if consistent
            else {sid: () for sid in all_step_ids}
        )
        direct_preds: dict[str, tuple[str, ...]] = {
            sid: tuple(
                sorted(
                    e.before_step_id for e in sorted_edges if e.after_step_id == sid
                )
            )
            for sid in all_step_ids
        }

        blockers: list[PlanBlocker] = []
        if not consistent:
            cycle_provs = sorted(
                {
                    p
                    for e in sorted_edges
                    if e.before_step_id in cycle_nodes and e.after_step_id in cycle_nodes
                    for p in e.provision_ids
                }
            )
            first_cycle = raw_steps[cycle_nodes[0]]
            blockers.append(
                PlanBlocker(
                    step_id=cycle_nodes[0],
                    subject_id=first_cycle["subject_id"],
                    scope_id=first_cycle["scope_id"],
                    status="CONFLICTING_DEPENDENCIES",
                    reason=f"Dependency cycle detected among steps: {', '.join(cycle_nodes)}",
                    missing_evidence=(),
                    provision_ids=tuple(cycle_provs),
                )
            )

        action_instances: list[ActionInstance] = []
        step_statuses: dict[str, StepStatus] = {}
        ordered_iter = topo_order if consistent else all_step_ids

        for sid in ordered_iter:
            sdata = raw_steps[sid]
            preds = direct_preds[sid]
            missing_ev = sdata.get("missing_evidence", ())

            # Observed fulfillment is strictly separated from expected_effects
            observed = Fulfillment.UNKNOWN
            if sdata["kind"] == "ACTION" and sdata["template_id"] in template_by_id:
                tpl_obs = template_by_id[sdata["template_id"]].for_obligations
                scope_fulfillments = fulfillment_by_scope.get(
                    (sdata["subject_id"], sdata["scope_id"]), {}
                )
                if tpl_obs and all(
                    scope_fulfillments.get(ob) == Fulfillment.SATISFIED for ob in tpl_obs
                ):
                    observed = Fulfillment.SATISFIED

            if any(
                g.startswith("source_boundary_issue:") or g.startswith("outsourced_")
                for g in missing_ev
            ):
                status = StepStatus.BLOCKED_BY_KNOWN_CONDITION
                blockers.append(
                    PlanBlocker(
                        step_id=sid,
                        subject_id=sdata["subject_id"],
                        scope_id=sdata["scope_id"],
                        status="BLOCKED_BY_KNOWN_CONDITION",
                        reason=f"Step {sid} is blocked by condition: {', '.join(missing_ev)}",
                        missing_evidence=missing_ev,
                        provision_ids=sdata["provision_ids"],
                    )
                )
            elif missing_ev or sdata["is_unresolved_choice"]:
                status = StepStatus.NEEDS_EVIDENCE
                blockers.append(
                    PlanBlocker(
                        step_id=sid,
                        subject_id=sdata["subject_id"],
                        scope_id=sdata["scope_id"],
                        status="NEEDS_EVIDENCE",
                        reason=(
                            f"Step {sid} on {sdata['subject_id']} ({sdata['scope_id']}) "
                            f"requires missing evidence: {', '.join(missing_ev)}"
                        ),
                        missing_evidence=missing_ev,
                        provision_ids=sdata["provision_ids"],
                    )
                )
            elif observed == Fulfillment.SATISFIED:
                status = StepStatus.SATISFIED
            elif not preds or all(step_statuses.get(p) == StepStatus.SATISFIED for p in preds):
                status = StepStatus.AVAILABLE_NOW
            else:
                status = StepStatus.WAITING_FOR_PREDECESSOR

            step_statuses[sid] = status
            action_instances.append(
                ActionInstance(
                    id=sid,
                    template_id=sdata["template_id"],
                    title=sdata["title"],
                    subject_id=sdata["subject_id"],
                    scope_id=sdata["scope_id"],
                    stage=sdata["stage"],
                    kind=sdata["kind"],
                    status=status,
                    predecessor_ids=preds,
                    transitive_predecessor_ids=trans_preds[sid],
                    expected_effects=sdata["expected_effects"],
                    observed_fulfillment=observed,
                    required_evidence=sdata["required_evidence"],
                    missing_evidence=missing_ev,
                    provision_ids=sdata["provision_ids"],
                )
            )

        candidates.append(
            PlanCandidate(
                id=f"plan-{idx}",
                assessment_id=result.assessment_id,
                branch_label=branch_label,
                consistent=consistent,
                truncated=truncated,
                action_instances=tuple(action_instances),
                prerequisite_groups=tuple(prereq_groups),
                graph_edges=sorted_edges,
                topological_order=topo_order,
                parallel_groups=parallel_waves,
                step_statuses=step_statuses,
                blockers=tuple(blockers),
                source_trace=result.explanations,
            )
        )

    return candidates
