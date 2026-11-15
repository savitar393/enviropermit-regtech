"""Versioned JSON contracts shared by the Python adapter and Java CLI.

Case evidence is scoped; inference is not a legal compliance certification.
"""
from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Any, Literal

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


class StepStatus(StrEnum):
    AVAILABLE_NOW = "AVAILABLE_NOW"
    WAITING_FOR_PREDECESSOR = "WAITING_FOR_PREDECESSOR"
    NEEDS_EVIDENCE = "NEEDS_EVIDENCE"
    BLOCKED_BY_KNOWN_CONDITION = "BLOCKED_BY_KNOWN_CONDITION"
    SATISFIED = "SATISFIED"


class ReasoningContext(Contract):
    assessment_id: str = Field(min_length=1)
    scenario_id: str = Field(min_length=1)
    evidence_snapshot_id: str = Field(min_length=1)
    assessed_on: date
    kb_release_id: str = Field(min_length=1)


class Activity(Contract):
    id: str = Field(min_length=1)
    kind: Literal[
        "WaterActivity",
        "AirActivity",
        "MainActivity",
        "SupportingActivity",
        "FoodManufacturingActivity",
    ] = "WaterActivity"
    scope_id: str = Field(min_length=1)
    kbli: str | None = None
    surface_discharge: bool = False
    existing_water_pertek: bool = False
    water_change: Literal["TreatmentDesignChange", "WastewaterManagementChange"] | None = None
    stationary_emission: bool = False
    existing_emission_pertek: bool = False
    emission_change: Literal["BoilerAddition", "EmissionControlChange", "FuelSwitchChange"] | None = None


class Observation(Contract):
    id: str
    context: ReasoningContext
    subject_id: str
    scope_id: str
    period_id: str
    extent_changes: tuple[bool, ...] = ()
    in_protected_area: tuple[bool, ...] = ()
    protected_area_exception: tuple[bool, ...] = ()
    non_emitting_source: tuple[bool, ...] = ()
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


class FulfillmentFinding(Contract):
    subject_id: str
    scope_id: str
    obligation_kind: str = ""
    status: Fulfillment
    evidence_ids: tuple[str, ...] = ()
    provision_ids: tuple[str, ...] = ()


class AssessmentResult(Contract):
    assessment_id: str
    context: ReasoningContext
    kb_version: str
    consistency_status: Literal["CONSISTENT", "INCONSISTENT", "INVALID_PROFILE", "NONCONVERGENT", "VERSION_CONFLICT"]
    obligation_assessments: tuple[ObligationAssessment, ...] = ()
    fulfillment_findings: tuple[FulfillmentFinding, ...] = ()
    project_obligations: tuple[str, ...] = ()
    decisions: tuple[DecisionFinding, ...] = ()
    precedence: tuple[tuple[str, str], ...] = ()
    evidence_gaps: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()
    explanations: tuple[dict, ...] = ()
    input_issues: tuple[str, ...] = ()
    snapshot: CaseSnapshot | None = None
    facts: FactBundle | None = None
    inference: InferenceResult | None = None


class RequirementGroup(Contract):
    id: str
    operator: Literal["ALL_OF", "ANY_OF"]
    member_step_ids: tuple[str, ...]
    provision_ids: tuple[str, ...] = ()


class ActionTemplate(Contract):
    id: str
    title: str
    stage: Literal[
        "EVIDENCE_ACQUISITION",
        "TECHNICAL_DOCUMENTATION",
        "TECHNICAL_APPROVAL",
        "ENVIRONMENTAL_DOCUMENTATION",
        "ENVIRONMENTAL_APPROVAL",
        "POST_APPROVAL_SLO",
    ]
    kind: Literal["ACTION", "MILESTONE"] = "ACTION"
    scope_level: Literal["ACTIVITY", "SCENARIO"] = "ACTIVITY"
    for_obligations: tuple[str, ...]
    preconditions: tuple[str, ...] = ()
    requirement_groups: tuple[RequirementGroup, ...] = ()
    expected_effects: tuple[str, ...] = ()
    required_evidence: tuple[str, ...] = ()
    supported_by: tuple[str, ...] = ()


class PlanEdgeSpec(Contract):
    before_step_id: str
    after_step_id: str
    provision_ids: tuple[str, ...] = ()
    rule_ids: tuple[str, ...] = ()


class PlanBlocker(Contract):
    step_id: str
    subject_id: str
    scope_id: str
    status: Literal["NEEDS_EVIDENCE", "BLOCKED_BY_KNOWN_CONDITION", "CONFLICTING_DEPENDENCIES"]
    reason: str
    missing_evidence: tuple[str, ...] = ()
    provision_ids: tuple[str, ...] = ()


class ActionInstance(Contract):
    id: str
    template_id: str
    title: str
    subject_id: str
    scope_id: str
    stage: str
    kind: Literal["ACTION", "MILESTONE"] = "ACTION"
    status: StepStatus
    predecessor_ids: tuple[str, ...] = ()
    transitive_predecessor_ids: tuple[str, ...] = ()
    expected_effects: tuple[str, ...] = ()
    observed_fulfillment: Fulfillment = Fulfillment.UNKNOWN
    required_evidence: tuple[str, ...] = ()
    missing_evidence: tuple[str, ...] = ()
    provision_ids: tuple[str, ...] = ()


class PlanCandidate(Contract):
    id: str
    assessment_id: str
    branch_label: str
    consistent: bool = True
    truncated: bool = False
    action_instances: tuple[ActionInstance, ...] = ()
    prerequisite_groups: tuple[RequirementGroup, ...] = ()
    graph_edges: tuple[PlanEdgeSpec, ...] = ()
    topological_order: tuple[str, ...] = ()
    parallel_groups: tuple[tuple[str, ...], ...] = ()
    step_statuses: dict[str, StepStatus] = Field(default_factory=dict)
    blockers: tuple[PlanBlocker, ...] = ()
    source_trace: tuple[dict, ...] = ()


class ScenarioChange(Contract):
    subject_id: str = Field(min_length=1)
    field: str = Field(min_length=1)
    operation: Literal["SET", "ADD", "REMOVE"] = "SET"
    old_value: Any = None
    new_value: Any = None
    evidence_ids: tuple[str, ...] = ()


class ObligationChange(Contract):
    subject_id: str
    scope_id: str
    obligation_kind: str
    change_kind: Literal[
        "ADDED",
        "REMOVED",
        "CHANGED_STATUS",
        "BECAME_UNRESOLVED",
        "RESOLVED_FROM_UNRESOLVED",
        "UNCHANGED",
    ]
    left_applicability: Applicability | None = None
    right_applicability: Applicability | None = None
    left_fulfillment: Fulfillment | None = None
    right_fulfillment: Fulfillment | None = None
    reason: str
    is_obligation_saving: bool = False
    provision_ids: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()


class PlanDiffSummary(Contract):
    added_steps: tuple[str, ...] = ()
    removed_steps: tuple[str, ...] = ()
    changed_step_statuses: dict[str, tuple[StepStatus, StepStatus]] = Field(default_factory=dict)
    added_blockers: tuple[str, ...] = ()
    removed_blockers: tuple[str, ...] = ()


class ScenarioDiff(Contract):
    left_assessment_id: str
    right_assessment_id: str
    left_scenario_id: str
    right_scenario_id: str
    shared_goal: bool = True
    same_kb_version: bool = True
    left_kb_version: str
    right_kb_version: str
    kb_version_warning: str | None = None
    input_changes: tuple[ScenarioChange, ...] = ()
    obligation_changes: tuple[ObligationChange, ...] = ()
    added_obligations: tuple[ObligationChange, ...] = ()
    removed_obligations: tuple[ObligationChange, ...] = ()
    changed_obligations: tuple[ObligationChange, ...] = ()
    unresolved_obligations: tuple[ObligationChange, ...] = ()
    unchanged_obligations: tuple[ObligationChange, ...] = ()
    added_evidence_gaps: tuple[str, ...] = ()
    removed_evidence_gaps: tuple[str, ...] = ()
    plan_changes: PlanDiffSummary = Field(default_factory=PlanDiffSummary)
    explanation_links: tuple[dict, ...] = ()


class SupportEdge(Contract):
    from_node: str
    to_node: str
    relation: Literal[
        "FACT_SUPPORTS_RULE",
        "RULE_INFERS_CONCLUSION",
        "PROVISION_BACKS_RULE",
        "EVIDENCE_GAP_BLOCKS_DECISION",
    ]


class ExplanationTrace(Contract):
    conclusion_id: str
    subject_id: str
    scope_id: str
    obligation_kind: str
    applicability: Applicability
    fulfillment: Fulfillment
    derivation_kind: Literal["SUPPORTING_PATH", "MINIMAL_JUSTIFICATION"] = "SUPPORTING_PATH"
    supporting_fact_ids: tuple[str, ...] = ()
    supporting_triples: tuple[Triple, ...] = ()
    axiom_rule_ids: tuple[str, ...] = ()
    fired_rule_ids: tuple[str, ...] = ()
    support_edges: tuple[SupportEdge, ...] = ()
    provision_ids: tuple[str, ...] = ()
    provisions: tuple[ProvisionRecord, ...] = ()
    assumptions: tuple[str, ...] = ()
    unresolved_evidence_ids: tuple[str, ...] = ()
    summary: str = ""


class VersionConflictError(ValueError):
    def __init__(self, provision_ids: tuple[str, ...], assessed_on: date, scope: str):
        self.provision_ids, self.assessed_on, self.scope = provision_ids, assessed_on, scope
        super().__init__(f"VERSION_CONFLICT: {provision_ids}, {assessed_on}, {scope}")

