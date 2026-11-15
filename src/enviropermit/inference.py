"""Map evidence to assertions; run an isolated Java reasoner process per request.

No legal threshold or document-branch decision is implemented in this adapter.
False/absent inventory fields are not asserted as negative OWL facts.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
from urllib.parse import quote

from .contracts import (NS, RDF_TYPE, XSD, CaseSnapshot, Closure, FactBundle,
                        FactProvenance, InferenceResult, KBRelease, ReasoningRequest, Triple)
from .normalization import normalize_measurement

ROOT = Path(__file__).resolve().parents[2]


def prepare_facts(snapshot: CaseSnapshot) -> FactBundle:
    context = snapshot.context
    digest = hashlib.sha256(json.dumps(context.model_dump(mode="json"), sort_keys=True,
                                      separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
    namespace = f"urn:enviropermit:{digest}:"
    triples, provenance, closures, issues = [], [], [], []
    names = set()

    def node(name):
        iri = namespace + quote(name, safe="-_")
        names.add(iri)
        return iri

    def add(subject, prop, obj, evidence="configuration", datatype=None, origin="HYPOTHETICAL"):
        triples.append(Triple(subject=subject, predicate=prop, object=obj, datatype=datatype))
        provenance.append(FactProvenance(fact_index=len(triples)-1, evidence_id=evidence,
                                         origin=origin, context=context))

    def typed(name, kind):
        iri = node(name)
        add(iri, RDF_TYPE, NS + kind)
        return iri

    if len({a.id for a in snapshot.activities}) != len(snapshot.activities):
        raise ValueError("Activity IDs must be unique in a snapshot")
    if len({e.id for e in snapshot.observations}) != len(snapshot.observations):
        raise ValueError("Observation IDs must be unique in a snapshot")
    if len({m.id for m in snapshot.measurements}) != len(snapshot.measurements):
        raise ValueError("Measurement IDs must be unique in a snapshot")

    project = typed("project-" + snapshot.project_id, "Project")
    scenario = typed("scenario", "Scenario")
    assessment = typed("assessment", "Assessment")
    evidence_snapshot = typed("snapshot", "EvidenceSnapshot")
    add(project, NS + "hasScenario", scenario)
    add(assessment, NS + "assessesScenario", scenario)
    add(assessment, NS + "hasSnapshot", evidence_snapshot)
    if snapshot.existing_environmental_approval:
        add(scenario, NS + "hasExistingApproval", typed("environmental-approval", "EnvironmentalApproval"))
    if snapshot.screening:
        add(scenario, NS + "hasScreening", NS + snapshot.screening, "proposed-screening")
    changes = []
    for index, kind in enumerate(snapshot.project_changes):
        change = typed(f"change-{index}", kind)
        changes.append(change)
        add(scenario, NS + "hasProjectChange", change)
    if snapshot.changes_complete:
        closures.append(Closure(subject=scenario, predicate=NS + "hasProjectChange",
                                members=tuple(changes), evidence_id="complete-change-inventory"))
    add(scenario, NS + "changesInventoryComplete", str(snapshot.changes_complete).lower(),
        "complete-change-inventory", XSD + "boolean")
    add(scenario, NS + "outsourcingClaim", str(snapshot.outsourcing_claim).lower(), datatype=XSD + "boolean")

    activity_map = {}
    for activity in snapshot.activities:
        act_kind = "FoodManufacturingActivity" if (activity.kind == "MainActivity" and activity.kbli == "10799") else activity.kind
        subject = typed("activity-" + activity.id, act_kind)
        scope = typed("scope-" + activity.scope_id, "WastewaterOutlet" if activity.kind == "WaterActivity" else "Scope")
        activity_map[activity.id] = (activity, subject)
        add(scenario, NS + "hasActivity", subject)
        add(subject, NS + "onScope", scope)
        if activity.surface_discharge:
            add(subject, NS + "dischargesTo", typed("receiving-" + activity.id, "SurfaceWater"))
        if activity.existing_water_pertek:
            add(subject, NS + "hasCurrentPertek", typed("pertek-" + activity.id, "WaterPertek"))
        if activity.water_change:
            add(subject, NS + "hasWaterTechnicalChange", typed("water-change-" + activity.id, activity.water_change))
        if activity.kind == "WaterActivity":
            candidate = typed("study-candidate-" + activity.id, "ObligationCandidate")
            add(subject, NS + "hasStudyCandidate", candidate)
            add(candidate, NS + "hasAssessment", assessment)
            add(candidate, NS + "ofSubject", subject)
            add(candidate, NS + "onScope", scope)

    for observation in snapshot.observations:
        matching = activity_map.get(observation.subject_id)
        if (observation.context != context or observation.period_id != snapshot.period_id
                or not matching or matching[0].scope_id != observation.scope_id):
            issues.append("EVIDENCE_SCOPE_MISMATCH:" + observation.id)
            continue
        if observation.origin == "EXPECTED_EFFECT":
            issues.append("EXPECTED_EFFECT_NOT_EVIDENCE:" + observation.id)
            continue
        if observation.extent_changes:
            evidence = typed("evidence-" + observation.id, "ImpactAssessment")
            add(matching[1], NS + "hasImpactAssessment", evidence, observation.id, origin=observation.origin)
            for value in observation.extent_changes:
                add(evidence, NS + "extentChanges", str(value).lower(), observation.id,
                    XSD + "boolean", observation.origin)
        if observation.in_protected_area:
            loc_evidence = typed("location-" + observation.id, "LocationAssessment")
            add(matching[1], NS + "hasLocationAssessment", loc_evidence, observation.id, origin=observation.origin)
            for value in observation.in_protected_area:
                add(loc_evidence, NS + "inProtectedArea", str(value).lower(), observation.id,
                    XSD + "boolean", observation.origin)
            exceptions = observation.protected_area_exception or ((False,) if True in observation.in_protected_area else ())
            for exc_value in exceptions:
                add(loc_evidence, NS + "hasProtectedAreaException", str(exc_value).lower(), observation.id,
                    XSD + "boolean", observation.origin)

    normalized_values = []
    for measurement in snapshot.measurements:
        matching = activity_map.get(measurement.subject_id)
        if (measurement.context != context or measurement.period_id != snapshot.period_id
                or not matching or matching[0].scope_id != measurement.scope_id):
            issues.append("EVIDENCE_SCOPE_MISMATCH:" + measurement.id)
            continue
        if measurement.origin == "EXPECTED_EFFECT":
            issues.append("EXPECTED_EFFECT_NOT_EVIDENCE:" + measurement.id)
            continue
        normalized = normalize_measurement(measurement)
        normalized_values.append(normalized.model_dump(mode="json"))
        if normalized.status != "NORMALIZED" or normalized.predicate is None or normalized.normalized_value is None:
            if normalized.issue:
                issues.append(normalized.issue)
            continue
        add(matching[1], normalized.predicate, normalized.normalized_value,
            measurement.id, XSD + "decimal", measurement.origin)
        if normalized.metric.strip().lower() == "production_capacity":
            scale_ev = typed("scale-" + measurement.id, "ScaleAssessment")
            add(matching[1], NS + "hasScaleAssessment", scale_ev, measurement.id, origin=measurement.origin)

    return FactBundle(context=context, namespace=namespace, project_iri=project,
                      assessment_iri=assessment, asserted_triples=tuple(triples),
                      normalized_values=tuple(normalized_values),
                      provenance=tuple(provenance), named_candidates=tuple(sorted(names)),
                      closures=tuple(closures), input_issues=tuple(sorted(set(issues))))


def load_release(path: Path | str = ROOT / "kb/releases/t1-water-spike-v2.json") -> KBRelease:
    return KBRelease.model_validate_json(Path(path).read_text(encoding="utf-8"))


def java_command(*args: str) -> list[str]:
    target = ROOT / "services/reasoner/target"
    if not (target / "classes/id/enviropermit/ReasoningCli.class").is_file():
        raise RuntimeError("Build the reasoner first: scripts/build_reasoner.ps1 or mvn -f services/reasoner/pom.xml package")
    classpath = os.pathsep.join((str(target / "classes"), str(target / "dependency/*")))
    return ["java", "-Dorg.slf4j.simpleLogger.defaultLogLevel=warn", "-cp", classpath,
            "id.enviropermit.ReasoningCli", *args]


def infer(facts: FactBundle, release: KBRelease, *, artifact_dir: Path | str | None = None,
          run_rules: bool = True, max_iterations: int = 4) -> InferenceResult:
    """infer(facts, release) uses the exact request/response schema of the Java CLI.

    A supplied artifact directory must be empty. Inconsistent results contain
    diagnostics only. Process/contract failures raise, never look like no obligations.
    """
    if facts.context.kb_release_id != release.id:
        raise ValueError("KB release differs from the assessment context")
    paths = {"knowledge_base_path": str((ROOT / release.knowledge_base_path).resolve())}
    request = ReasoningRequest(facts=facts, release=release.model_copy(update=paths),
                               run_rules=run_rules, max_iterations=max_iterations)

    def execute(directory: Path):
        directory.mkdir(parents=True, exist_ok=True)
        if any(directory.iterdir()):
            raise FileExistsError(f"Artifact directory must be empty: {directory}")
        request_path, response_path = directory / "request.json", directory / "response.json"
        request_path.write_text(request.model_dump_json(indent=2), encoding="utf-8")
        process = subprocess.run(java_command("infer", str(request_path.resolve()),
                                             str(response_path.resolve())), cwd=ROOT,
                                 capture_output=True, text=True, encoding="utf-8", timeout=120)
        (directory / "engine.log").write_text(process.stdout + process.stderr, encoding="utf-8")
        if process.returncode:
            raise RuntimeError(f"Reasoner failed ({process.returncode}): {process.stderr[-6000:]}")
        result = InferenceResult.model_validate_json(response_path.read_text(encoding="utf-8"))
        if result.context != facts.context:
            raise RuntimeError("Reasoner returned a different assessment context")
        return result

    if artifact_dir is not None:
        return execute(Path(artifact_dir))
    with tempfile.TemporaryDirectory(prefix="enviropermit-") as directory:
        return execute(Path(directory))

