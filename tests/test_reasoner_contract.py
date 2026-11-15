import json
import subprocess

import pytest

from enviropermit.contracts import NS, RDF_TYPE, FactProvenance, InferenceResult, ReasoningRequest, Triple
from enviropermit.inference import java_command
from enviropermit.inference import infer, prepare_facts


def test_unknown_extent_has_no_default_branch(case, release):
    result = infer(prepare_facts(case("U")), release)
    assert "amend_water_pertek" in result.project_obligations
    assert "prepare_standard_technical_documentation" not in result.project_obligations
    assert "prepare_technical_study" not in result.project_obligations
    route = next(d for d in result.decisions if d.id == "water_document_route")
    assert route.applicability == "UNRESOLVED"
    assert route.fulfillment == "UNKNOWN"
    assert "impact_extent_assessment" in route.evidence_gaps


def test_distinct_snapshots_conflict(case, release):
    facts = prepare_facts(case())
    other = facts.namespace + "snapshot-other"
    original = facts.namespace + "snapshot"
    facts = facts.model_copy(update={
        "named_candidates": facts.named_candidates + (other,),
        "provenance": facts.provenance + tuple(FactProvenance(fact_index=len(facts.asserted_triples) + i,
            evidence_id="two-distinct-snapshots-fixture", origin="HYPOTHETICAL", context=facts.context) for i in range(3)),
        "asserted_triples": facts.asserted_triples + (
            Triple(subject=other, predicate=RDF_TYPE, object=NS + "EvidenceSnapshot"),
            Triple(subject=facts.assessment_iri, predicate=NS + "hasSnapshot", object=other),
            Triple(subject=original, predicate="http://www.w3.org/2002/07/owl#differentFrom", object=other),
        ),
    })
    result = infer(facts, release)
    assert result.consistency_status == "INCONSISTENT"
    assert not result.project_obligations
    assert not result.inferred_triples
    assert not result.classifications


def test_two_cases_are_isolated(case, release):
    first = infer(prepare_facts(case("A")), release)
    second = infer(prepare_facts(case("U")), release)
    assert "prepare_technical_study" in first.project_obligations
    assert "prepare_technical_study" not in second.project_obligations
    assert not set(first.classifications).intersection(second.classifications)


def test_project_obligation_is_inferred_through_activity(case, release):
    facts = prepare_facts(case())
    expected = Triple(subject=facts.project_iri, predicate=NS + "projectObligation",
                      object=NS + "water_slo_required")
    assert expected not in facts.asserted_triples
    result = infer(facts, release, run_rules=False)
    assert expected in result.core_inferred_triples
    assert result.profiles["core"].in_owl2_dl_profile
    assert result.profiles["asserted"].in_owl2_dl_profile


def test_swrl_materializes_candidate_and_core_reclassifies(case, release, tmp_path):
    result = infer(prepare_facts(case()), release, artifact_dir=tmp_path)
    assert result.fired_rules
    assert any(t.object == NS + "TechnicalStudyAttachmentCandidate"
               for r in result.fired_rules for t in r.conclusions)
    assert any("ReviewableCandidate" in c for c in result.classifications.values())
    assert (tmp_path / "swrl-delta.owl").is_file()
    assert result.profiles["post_rules"].in_owl2_dl_profile
    assert not any(t.object == NS + "TechnicalStudyAttachmentCandidate" for t in result.core_inferred_triples)
    assert result.stage_iterations == 2


@pytest.mark.parametrize("dimension", ["scenario_id", "evidence_snapshot_id", "assessment_id", "assessed_on", "kb_release_id", "scope_id", "subject_id", "period_id", "origin"])
def test_mismatched_or_expected_evidence_cannot_select_branch(dimension, case, release):
    snapshot = case()
    data = snapshot.observations[0].model_dump(mode="json")
    if dimension in data["context"]:
        data["context"][dimension] = "2026-11-13" if dimension == "assessed_on" else "another-context"
    else:
        data[dimension] = "EXPECTED_EFFECT" if dimension == "origin" else "another-scope"
    snapshot = case(observations=[data])
    result = infer(prepare_facts(snapshot), release)
    assert "prepare_technical_study" not in result.project_obligations
    assert "prepare_standard_technical_documentation" not in result.project_obligations
    assert result.decisions[0].applicability == "UNRESOLVED"
    assert result.input_issues


def test_other_outlet_is_not_satisfied_by_first_outlet_evidence(case, release):
    snapshot = case()
    second = snapshot.activities[0].model_copy(update={"id": "water-2", "scope_id": "outlet-2"})
    snapshot = snapshot.model_copy(update={"activities": snapshot.activities + (second,)})
    result = infer(prepare_facts(snapshot), release)
    by_subject = {d.subject_id.rsplit(":", 1)[1]: d for d in result.decisions}
    assert by_subject["activity-water-1"].applicability == "APPLICABLE"
    assert by_subject["activity-water-2"].applicability == "UNRESOLVED"
    assert all(d.fulfillment == "UNKNOWN" for d in result.decisions)


def test_reused_entity_ids_do_not_keep_previous_branch(case, release):
    snapshot = case()
    first = infer(prepare_facts(snapshot), release)
    updated = snapshot.observations[0].model_copy(update={"extent_changes": (False,)})
    second = infer(prepare_facts(snapshot.model_copy(update={"observations": (updated,)})), release)
    assert "prepare_technical_study" in first.project_obligations
    assert "prepare_technical_study" not in second.project_obligations
    assert "prepare_standard_technical_documentation" in second.project_obligations
    assert not second.fired_rules


def test_raw_cross_snapshot_reference_is_rejected(case, release):
    facts = prepare_facts(case())
    invalid = Triple(subject=facts.project_iri, predicate=NS + "hasScenario", object="urn:other:scenario")
    with pytest.raises(RuntimeError, match="Cross-snapshot object"):
        infer(facts.model_copy(update={"asserted_triples": facts.asserted_triples + (invalid,)}), release)


def test_nonconvergence_quarantines_partial_results(case, release):
    result = infer(prepare_facts(case()), release, max_iterations=1)
    assert result.consistency_status == "NONCONVERGENT"
    assert result.conflicts == ("FIXED_POINT_LIMIT",)
    assert not result.inferred_triples
    assert not result.project_obligations


def test_release_integrity_is_enforced(case, release):
    bad = release.model_copy(update={"checksums": {**release.checksums, "knowledge_base": "0" * 64}})
    with pytest.raises(RuntimeError, match="checksum mismatch"):
        infer(prepare_facts(case()), bad)


def test_direct_cli_matches_python_contract(case, release, tmp_path):
    adapter_dir = tmp_path / "adapter"
    expected = infer(prepare_facts(case()), release, artifact_dir=adapter_dir)
    direct_dir = tmp_path / "direct"
    direct_dir.mkdir()
    completed = subprocess.run(java_command("infer", str(adapter_dir / "request.json"),
                                             str(direct_dir / "response.json")), capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    actual = InferenceResult.model_validate_json((direct_dir / "response.json").read_text())
    assert actual == expected


def test_artifacts_cannot_be_overwritten(case, release, tmp_path):
    facts = prepare_facts(case())
    infer(facts, release, artifact_dir=tmp_path)
    with pytest.raises(FileExistsError):
        infer(facts, release, artifact_dir=tmp_path)
    direct = subprocess.run(java_command("infer", str(tmp_path / "request.json"),
                                         str(tmp_path / "second-response.json")), capture_output=True, text=True)
    assert direct.returncode != 0
    assert "overwrite" in direct.stderr


@pytest.mark.parametrize("missing", ["all", "impact_only", "duplicate"])
def test_missing_provenance_cannot_bypass_evidence_checks(missing, case, release):
    facts = prepare_facts(case())
    provenance = () if missing == "all" else tuple(
        p for p in facts.provenance if facts.asserted_triples[p.fact_index].predicate != NS + "extentChanges")
    if missing == "duplicate":
        provenance = facts.provenance + (facts.provenance[0],)
    with pytest.raises(RuntimeError, match="provenance coverage"):
        infer(facts.model_copy(update={"provenance": provenance}), release)


def test_response_cannot_replace_an_owl_artifact(case, release, tmp_path):
    from enviropermit.inference import ROOT
    paths = {key: str(ROOT / getattr(release, key)) for key in ("knowledge_base_path",)}
    request = ReasoningRequest(facts=prepare_facts(case()), release=release.model_copy(update=paths), run_rules=False)
    path = tmp_path / "request.json"
    path.write_text(request.model_dump_json())
    completed = subprocess.run(java_command("infer", str(path), str(tmp_path / "final-inferred.owl")), capture_output=True, text=True)
    assert completed.returncode != 0
    assert "reserved" in completed.stderr
    assert not (tmp_path / "core-asserted.owl").exists()


@pytest.mark.parametrize("value", ["true", "false", 1, None])
def test_raw_cli_rejects_non_boolean_rule_flag(value, case, release, tmp_path):
    from enviropermit.inference import ROOT
    paths = {key: str(ROOT / getattr(release, key)) for key in ("knowledge_base_path",)}
    request = ReasoningRequest(facts=prepare_facts(case("U")), release=release.model_copy(update=paths)).model_dump(mode="json")
    request["run_rules"] = value
    path = tmp_path / "request.json"
    path.write_text(json.dumps(request))
    completed = subprocess.run(java_command("infer", str(path), str(tmp_path / "response.json")), capture_output=True, text=True)
    assert completed.returncode != 0
    assert "run_rules must be boolean" in completed.stderr


def test_raw_cli_rejects_fractional_iteration_limit(case, release, tmp_path):
    from enviropermit.inference import ROOT
    paths = {key: str(ROOT / getattr(release, key)) for key in ("knowledge_base_path",)}
    request = ReasoningRequest(facts=prepare_facts(case()), release=release.model_copy(update=paths), run_rules=False).model_dump(mode="json")
    request["max_iterations"] = 1.5
    path = tmp_path / "request.json"
    path.write_text(json.dumps(request))
    completed = subprocess.run(java_command("infer", str(path), str(tmp_path / "response.json")), capture_output=True, text=True)
    assert completed.returncode != 0
    assert "max_iterations must be integer" in completed.stderr


