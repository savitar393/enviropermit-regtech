from datetime import date
import pytest

from enviropermit.contracts import ProvisionRecord, VersionConflictError
from enviropermit.inference import infer, prepare_facts
from enviropermit.sources import (
    audit_rule_sources,
    infer_with_selected_release,
    load_registry,
    select_release,
)


EXPECTED_WATER_SPIKE_PROVISIONS = (
    "PP22:89-90",
    "PP22:93.2",
    "P5:3",
    "P5:15",
    "P5:16.1.a",
    "P5:16.1.b",
    "P5:16.2",
    "P5:8.1",
    "P5:8.2",
    "P5:14",
    "MODEL:closure",
    "MODEL:screening",
    "MODEL:candidate-workflow",
)


def test_partial_repeal_preserves_unaffected_clause(case):
    registry = list(load_registry())
    by_id = {record.id: record for record in registry}
    assert "P5:feed-sector" in by_id
    assert by_id["P5:feed-sector"].document_id == "PERMEN_LHK_5_2021"
    assert by_id["P5:feed-sector"].effective_to == date(2026, 1, 19)
    assert "P2_2026:feed-sector" in by_id
    assert by_id["P2_2026:feed-sector"].supersedes == ("P5:feed-sector",)

    # 1. Partial repeal of feed-sector clauses in Permen LHK 5/2021 does not repeal
    #    industrial surface-water Pertek clauses in the same regulation.
    selected = select_release(case("A"), registry)
    assert set(selected.provision_ids) == set(EXPECTED_WATER_SPIKE_PROVISIONS)
    assert "P5:feed-sector" not in selected.provision_ids

    # 2. If one clause within wastewater_pertek is repealed before assessed_on,
    #    all other unaffected clauses in Permen LHK 5/2021 remain selected.
    partially_repealed_registry = [
        record.model_copy(update={"effective_to": date(2026, 1, 19)})
        if record.id == "P5:16.1.b"
        else record
        for record in registry
    ]
    selected_after_clause_repeal = select_release(case("A"), partially_repealed_registry)
    expected_remaining = set(EXPECTED_WATER_SPIKE_PROVISIONS) - {"P5:16.1.b"}
    assert set(selected_after_clause_repeal.provision_ids) == expected_remaining


def test_overlapping_versions_return_conflict(case):
    registry = list(load_registry())
    overlapping_amendment = ProvisionRecord(
        id="P5_AMEND_2026:15",
        document_id="PERMEN_LH_99_2026",
        locator="Pasal 15(1)-(2)",
        source_url="https://peraturan.bpk.go.id/Details/example-overlap",
        effective_from=date(2026, 6, 1),
        effective_to=None,
        scope="wastewater_pertek",
        supersedes=(),
        interpretation_note="Overlapping wastewater technical revision clause without explicit supersedes priority.",
        review_status="VERIFIED",
        rule_ids=("WaterTechnicalRevision",),
        case_ids=("A",),
    )
    with pytest.raises(VersionConflictError) as exc_info:
        select_release(case("A"), [*registry, overlapping_amendment])

    assert exc_info.value.provision_ids == ("P5:15", "P5_AMEND_2026:15")
    assert exc_info.value.assessed_on == date(2026, 11, 14)
    assert exc_info.value.scope == "wastewater_pertek"


def test_version_conflict_is_quarantined_before_inference(case):
    registry = list(load_registry())
    overlapping = ProvisionRecord(
        id="P5_AMEND_2026:15",
        document_id="PERMEN_LH_99_2026",
        locator="Pasal 15(1)-(2)",
        source_url="https://peraturan.bpk.go.id/Details/example-overlap",
        effective_from=date(2026, 6, 1),
        scope="wastewater_pertek",
        supersedes=(),
        interpretation_note="Conflicting version without supersedes relation.",
        review_status="VERIFIED",
        rule_ids=("WaterTechnicalRevision",),
    )
    result = infer_with_selected_release(case("A"), [*registry, overlapping])
    assert result.consistency_status == "VERSION_CONFLICT"
    assert any("P5:15" in c and "P5_AMEND_2026:15" in c for c in result.conflicts)
    assert not result.project_obligations
    assert not result.inferred_triples
    assert not result.decisions


def test_explicit_supersedes_resolves_overlapping_dates_by_assessment_date(case):
    registry = list(load_registry())
    snapshot_2024 = case("A")
    snapshot_2024 = snapshot_2024.model_copy(
        update={"context": snapshot_2024.context.model_copy(update={"assessed_on": date(2024, 5, 10)})}
    )
    early_Licensing = select_release(snapshot_2024, registry, scopes=("business_licensing_context",))
    assert early_Licensing.provision_ids == ("PP5_2021:perizinan-dasar",)

    late_licensing = select_release(case("A"), registry, scopes=("business_licensing_context",))
    assert late_licensing.provision_ids == ("PP28_2025:perizinan-dasar",)


def test_unknown_effective_date_on_verified_provision_is_rejected(case):
    registry = list(load_registry())
    undated = ProvisionRecord(
        id="P5:undated",
        document_id="PERMEN_LHK_5_2021",
        locator="Pasal 99",
        source_url="https://jdih.menlhk.go.id/example.pdf",
        effective_from=None,
        scope="wastewater_pertek",
        interpretation_note="Verified statutory clause missing effective_from date must not be guessed.",
        review_status="VERIFIED",
        rule_ids=("RegulatedSurfaceDischarge",),
    )
    with pytest.raises(ValueError, match="effective_from"):
        select_release(case("A"), [*registry, undated])


def test_all_production_rules_have_explicit_provision_or_model_assumption():
    registry = {record.id: record for record in load_registry()}
    rule_sources = audit_rule_sources()
    assert rule_sources, "Expected production classes and SWRL rules in kb/enviropermit.ttl"

    expected_rules = {
        "ConcurrentSubmissionPermitted",
        "EnvironmentalAmendment",
        "InteractingAmendments",
        "ManagementTechnicalDependency",
        "RegulatedSurfaceDischarge",
        "ScreenedCase",
        "TechnicalStandardBranch",
        "TechnicalStudyAttachmentCandidate",
        "TechnicalStudyBranch",
        "UKLSubmissionSequence",
        "WaterTechnicalRevision",
        "WithNewEnvironmentalDocumentation",
        "WithoutNewEnvironmentalDocumentation",
        "water-study-candidate",
    }
    assert expected_rules <= set(rule_sources)

    for rule_id, source_ids in rule_sources.items():
        assert source_ids, f"Production rule/class {rule_id} has no source_id"
        for source_id in source_ids:
            assert source_id in registry, f"{rule_id} references unknown provision {source_id}"
            record = registry[source_id]
            assert rule_id in record.rule_ids, f"Provision {source_id} does not list {rule_id} in rule_ids"
            if source_id.startswith("MODEL:"):
                assert record.review_status == "MODEL_ASSUMPTION"
            else:
                assert record.review_status == "VERIFIED"
                assert record.document_id
                assert record.source_url
                assert record.effective_from is not None


def test_selected_release_executes_and_traces_provisions_in_result(case):
    snapshot = case("A")
    release = select_release(snapshot)
    result = infer(prepare_facts(snapshot), release)
    assert result.consistency_status == "CONSISTENT"
    assert any(
        trace.get("conclusion") == "WaterTechnicalRevision"
        and any(
            p.get("id") == "P5:15"
            and p.get("document_id") == "PERMEN_LHK_5_2021"
            and p.get("effective_from") == "2021-04-01"
            for p in trace.get("provisions", ())
        )
        for trace in result.source_traces
    )
