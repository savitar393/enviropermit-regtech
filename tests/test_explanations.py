from __future__ import annotations

import json
from pathlib import Path

from enviropermit.assessment import assess
from enviropermit.composition import compose
from enviropermit.contracts import CaseSnapshot
from enviropermit.explanations import (
    explain,
    explain_scenario_change,
    render_report,
    run_sparql_query,
)
from enviropermit.planning import build_plans
from enviropermit.sources import load_registry, select_release

ROOT = Path(__file__).resolve().parents[1]


def _load_snapshot(name: str) -> CaseSnapshot:
    return CaseSnapshot.model_validate(
        json.loads((ROOT / "cases/development" / name).read_text(encoding="utf-8"))
    )


def _assess_composed(snapshot: CaseSnapshot):
    release = select_release(snapshot, load_registry())
    return compose(assess(snapshot, release))


def test_explanation_reaches_input_and_source() -> None:
    res_a = _assess_composed(_load_snapshot("demo_a.json"))

    trace = explain(res_a, "water-1:outlet-1:prepare_technical_study")
    assert trace.conclusion_id == "water-1:outlet-1:prepare_technical_study"
    assert trace.subject_id == "water-1"
    assert trace.scope_id == "outlet-1"
    assert trace.obligation_kind == "prepare_technical_study"
    assert trace.derivation_kind == "SUPPORTING_PATH"

    assert "obs-water-a" in trace.supporting_fact_ids
    assert "configuration" in trace.supporting_fact_ids
    assert len(trace.supporting_triples) > 0
    assert "TechnicalStudyBranch" in trace.axiom_rule_ids
    assert "P5:16.1.a" in trace.provision_ids
    assert any(p.id == "P5:16.1.a" and p.source_url for p in trace.provisions)

    fact_to_rule = {
        (edge.from_node, edge.to_node)
        for edge in trace.support_edges
        if edge.relation == "FACT_SUPPORTS_RULE"
    }
    prov_to_rule = {
        (edge.from_node, edge.to_node)
        for edge in trace.support_edges
        if edge.relation == "PROVISION_BACKS_RULE"
    }
    rule_to_concl = {
        (edge.from_node, edge.to_node)
        for edge in trace.support_edges
        if edge.relation == "RULE_INFERS_CONCLUSION"
    }
    assert any(f == "fact:obs-water-a" for f, _ in fact_to_rule)
    assert any(p == "provision:P5:16.1.a" for p, _ in prov_to_rule)
    assert any(
        r == "rule:TechnicalStudyBranch" and c == "conclusion:water-1:outlet-1:prepare_technical_study"
        for r, c in rule_to_concl
    )

    ob_rows = run_sparql_query(ROOT / "kb/queries/obligations.rq", res_a)
    assert any(
        row["obligation"].endswith("#prepare_technical_study")
        and row["sourceId"] == "P5:16.1.a"
        for row in ob_rows
    )
    dep_rows = run_sparql_query(ROOT / "kb/queries/dependencies.rq", res_a)
    assert any(
        row["afterStep"].endswith("#environmental_change_issued")
        and row["beforeStep"].endswith("#water_pertek_change_issued")
        for row in dep_rows
    )


def test_model_assumption_is_labeled() -> None:
    res_a = _assess_composed(_load_snapshot("demo_a.json"))

    water_trace = explain(res_a, "water-1:outlet-1:prepare_technical_study")
    assert "MODEL:candidate-workflow" in water_trace.provision_ids
    assert len(water_trace.assumptions) > 0
    assert any("MODEL:candidate-workflow" in item for item in water_trace.assumptions)
    assert any(
        p.id == "MODEL:candidate-workflow" and p.review_status == "MODEL_ASSUMPTION"
        for p in water_trace.provisions
    )

    air_trace = explain(res_a, "air-1:boiler-stack-1:prepare_emission_technical_study")
    assert "MODEL:candidate-workflow" in air_trace.provision_ids
    assert any("MODEL:candidate-workflow" in item for item in air_trace.assumptions)

    plans = build_plans(res_a)
    html_report = render_report(res_a, plans)
    assert "<html" in html_report.lower()
    assert "MODEL_ASSUMPTION" in html_report
    assert "MODEL:candidate-workflow" in html_report
    assert "P5:16.1.a" in html_report


def test_changed_conclusion_explains_changed_fact() -> None:
    res_a = _assess_composed(_load_snapshot("demo_a.json"))
    res_b = _assess_composed(_load_snapshot("demo_b.json"))
    res_c = _assess_composed(_load_snapshot("demo_c.json"))

    air_change = explain_scenario_change(
        res_a, res_b, "air-1:boiler-stack-1:emission_pertek_required"
    )
    assert air_change["change_kind"] == "REMOVED"
    assert air_change["is_obligation_saving"] is True
    changed_fields = {item["field"] for item in air_change["changed_input_facts"]}
    assert "stationary_emission" in changed_fields or "non_emitting_source" in changed_fields
    assert "obs-air-b-electric" in air_change["right_evidence_ids"]

    water_change = explain_scenario_change(
        res_a, res_c, "water-1:outlet-1:prepare_technical_study"
    )
    assert water_change["change_kind"] == "BECAME_UNRESOLVED"
    assert water_change["is_obligation_saving"] is False
    assert len(water_change["unresolved_evidence_gaps"]) > 0
    water_changed_fields = {item["field"] for item in water_change["changed_input_facts"]}
    assert "extent_changes" in water_changed_fields or "water_change" in water_changed_fields
