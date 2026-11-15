"""Versioned JSON contracts shared by the Python adapter and Java CLI.

Case evidence is scoped; inference is not a legal compliance certification.
"""
from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool

NS = "https://example.org/enviropermit#"
RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
XSD = "http://www.w3.org/2001/XMLSchema#"


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Applicability(StrEnum):
    APPLICABLE = "APPLICABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    UNRESOLVED = "UNRESOLVED"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"
    CONFLICTING = "CONFLICTING"


class Fulfillment(StrEnum):
    SATISFIED = "SATISFIED"
    UNSATISFIED = "UNSATISFIED"
    UNKNOWN = "UNKNOWN"
    CONFLICTING = "CONFLICTING"


class ReasoningContext(Contract):
    assessment_id: str = Field(min_length=1)
    scenario_id: str = Field(min_length=1)
    evidence_snapshot_id: str = Field(min_length=1)
    assessed_on: date
    kb_release_id: str = Field(min_length=1)


class Activity(Contract):
    id: str = Field(min_length=1)
    kind: Literal["WaterActivity", "MainActivity", "SupportingActivity", "FoodManufacturingActivity"] = "WaterActivity"
    scope_id: str = Field(min_length=1)
    kbli: str | None = None
    surface_discharge: bool = False
    existing_water_pertek: bool = False
    water_change: Literal["TreatmentDesignChange", "WastewaterManagementChange"] | None = None


class Observation(Contract):
    id: str
    context: ReasoningContext
    subject_id: str
    scope_id: str
    period_id: str
    extent_changes: tuple[bool, ...] = ()
    in_protected_area: tuple[bool, ...] = ()
    protected_area_exception: tuple[bool, ...] = ()
    origin: Literal["HYPOTHETICAL", "OBSERVED", "EXPECTED_EFFECT"] = "HYPOTHETICAL"


class Measurement(Contract):
    id: str = Field(min_length=1)
    context: ReasoningContext
    subject_id: str = Field(min_length=1)
    scope_id: str = Field(min_length=1)
    period_id: str = Field(min_length=1)
    metric: str = Field(min_length=1)
    value: float
    unit: str = Field(min_length=1)
    origin: Literal["HYPOTHETICAL", "OBSERVED", "EXPECTED_EFFECT"] = "HYPOTHETICAL"


class CaseSnapshot(Contract):
    context: ReasoningContext
    project_id: str
    goal: str
    period_id: str
    location: str | None = None
    activities: tuple[Activity, ...]
    observations: tuple[Observation, ...] = ()
    measurements: tuple[Measurement, ...] = ()
    project_changes: tuple[Literal["CapacityIncrease", "IdentityChange", "ManagementMonitoringChange"], ...] = ()
    changes_complete: bool = False
    screening: Literal["UKL", "AMDAL", "SPPL"] | None = None
    existing_environmental_approval: bool = False
    outsourcing_claim: bool = False


class Triple(Contract):
    subject: str
    predicate: str
    object: str
    datatype: str | None = None


class Closure(Contract):
    subject: str
    predicate: str
    members: tuple[str, ...]
    evidence_id: str


class FactProvenance(Contract):
    fact_index: int
    evidence_id: str
    origin: Literal["HYPOTHETICAL", "OBSERVED", "EXPECTED_EFFECT"]
    context: ReasoningContext


class FactBundle(Contract):
    context: ReasoningContext
    namespace: str
    project_iri: str
    assessment_iri: str
    asserted_triples: tuple[Triple, ...] = ()
    normalized_values: tuple[dict, ...] = ()
    provenance: tuple[FactProvenance, ...] = ()
    named_candidates: tuple[str, ...] = ()
    closures: tuple[Closure, ...] = ()
    input_issues: tuple[str, ...] = ()


class KBRelease(Contract):
    id: str
    knowledge_base_path: str
    checksums: dict[str, str]
    provision_ids: tuple[str, ...]
    supported_scope: str


class ProvisionRecord(Contract):
    id: str = Field(min_length=1)
    document_id: str | None = None
    locator: str = Field(min_length=1)
    source_url: str | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    scope: str = Field(min_length=1)
    supersedes: tuple[str, ...] = ()
    interpretation_note: str = Field(min_length=1)
    review_status: Literal["VERIFIED", "MODEL_ASSUMPTION", "DRAFT"] = "VERIFIED"
    rule_ids: tuple[str, ...] = ()
    case_ids: tuple[str, ...] = ()


class ProfileReport(Contract):
    in_owl2_dl_profile: bool
    violations: tuple[str, ...] = ()
    axiom_count: int


class DecisionFinding(Contract):
    id: str
    subject_id: str
    applicability: Applicability
    fulfillment: Fulfillment = Fulfillment.UNKNOWN
    branches: tuple[str, ...] = ()
    evidence_gaps: tuple[str, ...] = ()


class FiredRuleRecord(Contract):
    rule_id: str
    iteration: int
    conclusions: tuple[Triple, ...]


class InferenceResult(Contract):
    schema_version: Literal["1.1"] = "1.1"
    context: ReasoningContext
    consistency_status: Literal["CONSISTENT", "INCONSISTENT", "INVALID_PROFILE", "NONCONVERGENT", "VERSION_CONFLICT"]
    inferred_triples: tuple[Triple, ...] = ()
    core_inferred_triples: tuple[Triple, ...] = ()
    classifications: dict[str, tuple[str, ...]] = Field(default_factory=dict)
    project_obligations: tuple[str, ...] = ()
    decisions: tuple[DecisionFinding, ...] = ()
    precedence: tuple[tuple[str, str], ...] = ()
    evidence_gaps: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()
    fired_rules: tuple[FiredRuleRecord, ...] = ()
    profiles: dict[str, ProfileReport] = Field(default_factory=dict)
    input_issues: tuple[str, ...] = ()
    source_traces: tuple[dict, ...] = ()
    stage_iterations: int = 0


class ReasoningRequest(Contract):
    schema_version: Literal["1.1"] = "1.1"
    facts: FactBundle
    release: KBRelease
    run_rules: StrictBool = True
    max_iterations: int = Field(default=4, ge=1, le=16, strict=True)


class ObligationAssessment(Contract):
    assessment_id: str
    subject_id: str
    obligation_kind: str
    scope_id: str
    applicability: Applicability
    fulfillment: Fulfillment
    evidence_ids: tuple[str, ...]
    provision_ids: tuple[str, ...]
    rule_ids: tuple[str, ...]


class VersionConflictError(ValueError):
    def __init__(self, provision_ids: tuple[str, ...], assessed_on: date, scope: str):
        self.provision_ids, self.assessed_on, self.scope = provision_ids, assessed_on, scope
        super().__init__(f"VERSION_CONFLICT: {provision_ids}, {assessed_on}, {scope}")

