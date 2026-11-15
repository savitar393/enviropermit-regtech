"""Provision registry loading, rule-source auditing, and dated rule-pack selection."""
from __future__ import annotations

from collections.abc import Sequence
from datetime import date
import hashlib
import json
from pathlib import Path
import re

from .contracts import (
    CaseSnapshot,
    InferenceResult,
    KBRelease,
    ProvisionRecord,
    VersionConflictError,
)
from .inference import ROOT, infer, load_release, prepare_facts

_PROVISION_BLOCK_RE = re.compile(
    r"(?m)^:[A-Za-z0-9_]+\s+a\s+owl:NamedIndividual\s*,\s*:Provision\s*;(.*?)(?=\n:[A-Za-z0-9_]+\s+a\s+|\Z)",
    re.DOTALL,
)
_STRING_LITERALS_RE = re.compile(r'"((?:[^"\\]|\\.)*)"')
_DATE_LITERAL_RE = re.compile(r'"(\d{4}-\d{2}-\d{2})"\^\^xsd:date')
_IRI_LITERAL_RE = re.compile(r"<([^>]+)>")


_TURTLE_VALUE = r'(?:"(?:[^"\\]|\\.)*"(?:\^\^[A-Za-z0-9_:]+)?|<[^>]+>|[A-Za-z0-9_:-]+)'
_TURTLE_OBJECT_LIST = rf"{_TURTLE_VALUE}(?:\s*,\s*{_TURTLE_VALUE})*"


def _extract_predicate_chunk(block: str, predicate: str) -> str | None:
    pattern = re.compile(rf"(?:^|[;\s]){re.escape(predicate)}\s+({_TURTLE_OBJECT_LIST})")
    match = pattern.search(block)
    return match.group(1).strip() if match else None


def _extract_strings(block: str, predicate: str) -> tuple[str, ...]:
    chunk = _extract_predicate_chunk(block, predicate)
    if not chunk:
        return ()
    return tuple(_STRING_LITERALS_RE.findall(chunk))


def _extract_single_string(block: str, predicate: str, *, required: bool = False) -> str | None:
    values = _extract_strings(block, predicate)
    if len(values) > 1:
        raise ValueError(f"Ambiguous {predicate} in provision block")
    if not values:
        if required:
            raise ValueError(f"Missing required {predicate} in provision block")
        return None
    return values[0]


def _extract_single_date(block: str, predicate: str) -> date | None:
    chunk = _extract_predicate_chunk(block, predicate)
    if not chunk:
        return None
    matches = _DATE_LITERAL_RE.findall(chunk)
    if len(matches) != 1:
        raise ValueError(f"Invalid xsd:date annotation for {predicate}: {chunk}")
    return date.fromisoformat(matches[0])


def _extract_single_iri(block: str, predicate: str) -> str | None:
    chunk = _extract_predicate_chunk(block, predicate)
    if not chunk:
        return None
    matches = _IRI_LITERAL_RE.findall(chunk)
    if len(matches) != 1:
        raise ValueError(f"Invalid IRI annotation for {predicate}: {chunk}")
    return matches[0]


def load_registry(path: Path | str = ROOT / "kb/enviropermit.ttl") -> tuple[ProvisionRecord, ...]:
    source_path = Path(path)
    text = source_path.read_text(encoding="utf-8")
    if source_path.suffix.lower() == ".json":
        raw = json.loads(text)
        return tuple(ProvisionRecord.model_validate(item) for item in raw)

    records: list[ProvisionRecord] = []
    seen_ids: set[str] = set()
    for match in _PROVISION_BLOCK_RE.finditer(text):
        block = match.group(1)
        prov_id = _extract_single_string(block, ":source_id", required=True)
        assert prov_id is not None
        if prov_id in seen_ids:
            raise ValueError(f"Duplicate provision id in KB: {prov_id}")
        seen_ids.add(prov_id)

        locator = _extract_single_string(block, ":locator", required=True)
        scope = _extract_single_string(block, ":provisionScope", required=True)
        comment = _extract_single_string(block, "rdfs:comment", required=True)
        review_status = _extract_single_string(block, ":reviewStatus") or (
            "MODEL_ASSUMPTION" if prov_id.startswith("MODEL:") else "VERIFIED"
        )
        assert locator is not None and scope is not None and comment is not None

        record = ProvisionRecord(
            id=prov_id,
            document_id=_extract_single_string(block, ":documentId"),
            locator=locator,
            source_url=_extract_single_iri(block, ":sourceURL"),
            effective_from=_extract_single_date(block, ":effectiveFrom"),
            effective_to=_extract_single_date(block, ":effectiveTo"),
            scope=scope,
            supersedes=_extract_strings(block, ":supersedes"),
            interpretation_note=comment,
            review_status=review_status,  # type: ignore[arg-type]
            rule_ids=_extract_strings(block, ":ruleId"),
            case_ids=_extract_strings(block, ":caseId"),
        )
        records.append(record)
    return tuple(records)


def audit_rule_sources(path: Path | str = ROOT / "kb/enviropermit.ttl") -> dict[str, tuple[str, ...]]:
    text = Path(path).read_text(encoding="utf-8")
    mapping: dict[str, tuple[str, ...]] = {}

    class_block_re = re.compile(
        r"(?m)^:([A-Za-z0-9_]+)\s+rdf:type\s+owl:Class\s*;(.*?)(?=\n###|\n#################################################################)",
        re.DOTALL,
    )
    for match in class_block_re.finditer(text):
        class_name, body = match.group(1), match.group(2)
        if "owl:equivalentClass" in body or ":source_id" in body:
            mapping[class_name] = tuple(sorted(set(_extract_strings(body, ":source_id"))))

    swrl_block_re = re.compile(r"\[\]\s+a\s+swrl:Imp\s*;(.*?\)\s*\.)", re.DOTALL)
    for match in swrl_block_re.finditer(text):
        body = match.group(1)
        labels = _extract_strings(body, "rdfs:label")
        if not labels:
            continue
        sources = _extract_strings(body, ":source_id")
        mapping[labels[0]] = tuple(sorted(set(sources)))

    return mapping


def snapshot_scopes(snapshot: CaseSnapshot) -> tuple[str, ...]:
    scopes: list[str] = []
    if snapshot.existing_environmental_approval or snapshot.project_changes:
        scopes.append("environmental_approval_change")
    if any(
        activity.kind in ("MainActivity", "FoodManufacturingActivity")
        for activity in snapshot.activities
    ):
        scopes.append("activity_screening")
    if any(activity.kind == "WaterActivity" for activity in snapshot.activities):
        scopes.append("wastewater_pertek")
    scopes.append("modeling_assumption")
    return tuple(scopes)


def _validate_provision(record: ProvisionRecord) -> None:
    if record.effective_from and record.effective_to and record.effective_to < record.effective_from:
        raise ValueError(
            f"Provision {record.id} has effective_to ({record.effective_to}) before effective_from ({record.effective_from})"
        )
    if record.review_status != "MODEL_ASSUMPTION" and record.effective_from is None:
        raise ValueError(
            f"Provision {record.id} ({record.review_status}) is missing explicit effective_from date"
        )


def _is_effective_on(record: ProvisionRecord, assessed_on: date) -> bool:
    if record.effective_from is not None and assessed_on < record.effective_from:
        return False
    if record.effective_to is not None and assessed_on > record.effective_to:
        return False
    return True


def _resolve_scope_provisions(
    scope: str,
    candidates: Sequence[ProvisionRecord],
    assessed_on: date,
) -> list[ProvisionRecord]:
    for record in candidates:
        _validate_provision(record)

    active = [record for record in candidates if _is_effective_on(record, assessed_on)]
    by_id: dict[str, list[ProvisionRecord]] = {}
    for record in active:
        by_id.setdefault(record.id, []).append(record)
    for prov_id, group in by_id.items():
        if len(group) > 1:
            raise VersionConflictError((prov_id,), assessed_on, scope)

    active_by_id = {record.id: record for record in active}

    def supersedes_transitively(left_id: str, right_id: str, visited: set[str] | None = None) -> bool:
        seen = visited or set()
        if left_id in seen:
            return False
        seen.add(left_id)
        left = active_by_id.get(left_id)
        if left is None:
            return False
        if right_id in left.supersedes:
            return True
        return any(
            supersedes_transitively(mid_id, right_id, seen.copy())
            for mid_id in left.supersedes
            if mid_id in active_by_id
        )

    # Check for supersession cycles among active provisions
    for record in active:
        if supersedes_transitively(record.id, record.id):
            cycle_ids = tuple(
                sorted(
                    other.id
                    for other in active
                    if supersedes_transitively(record.id, other.id)
                    and supersedes_transitively(other.id, record.id)
                )
            )
            raise VersionConflictError(cycle_ids or (record.id,), assessed_on, scope)

    # Check for divergent replacements of the same target provision
    predecessor_map: dict[str, list[str]] = {}
    for record in active:
        for target in record.supersedes:
            predecessor_map.setdefault(target, []).append(record.id)
    for target_id, replacers in predecessor_map.items():
        if len(replacers) > 1:
            undominated = [
                r_id
                for r_id in replacers
                if not any(
                    other_id != r_id and supersedes_transitively(other_id, r_id)
                    for other_id in replacers
                )
            ]
            if len(undominated) > 1:
                raise VersionConflictError(tuple(sorted(set(undominated))), assessed_on, scope)

    surviving = [
        record
        for record in active
        if not any(
            other.id != record.id and supersedes_transitively(other.id, record.id)
            for other in active
        )
    ]

    # Check surviving provisions for overlapping coverage without explicit priority
    conflicting_ids: set[str] = set()
    for index, left in enumerate(surviving):
        for right in surviving[index + 1 :]:
            same_locator = (
                left.review_status != "MODEL_ASSUMPTION"
                and right.review_status != "MODEL_ASSUMPTION"
                and left.locator == right.locator
            )
            same_nonempty_rules = bool(left.rule_ids) and set(left.rule_ids) == set(right.rule_ids)
            cross_doc_shared_rule = (
                left.document_id != right.document_id
                and bool(set(left.rule_ids) & set(right.rule_ids))
            )
            if same_locator or same_nonempty_rules or cross_doc_shared_rule:
                conflicting_ids.update((left.id, right.id))

    if conflicting_ids:
        raise VersionConflictError(tuple(sorted(conflicting_ids)), assessed_on, scope)

    return surviving


def select_release(
    snapshot: CaseSnapshot,
    registry: Sequence[ProvisionRecord] | None = None,
    *,
    scopes: Sequence[str] | None = None,
    kb_path: Path | str = ROOT / "kb/enviropermit.ttl",
) -> KBRelease:
    records = tuple(registry) if registry is not None else load_registry(kb_path)
    target_scopes = tuple(scopes) if scopes is not None else snapshot_scopes(snapshot)
    assessed_on = snapshot.context.assessed_on

    selected: list[ProvisionRecord] = []
    for scope in target_scopes:
        scoped_records = [record for record in records if record.scope == scope]
        selected.extend(_resolve_scope_provisions(scope, scoped_records, assessed_on))

    selected_ids = tuple(record.id for record in selected)
    default_release = load_release()
    if set(selected_ids) == set(default_release.provision_ids) and snapshot.context.kb_release_id == default_release.id:
        return default_release

    resolved_kb = Path(kb_path)
    if not resolved_kb.is_absolute():
        resolved_kb = ROOT / resolved_kb
    checksum = hashlib.sha256(resolved_kb.read_bytes()).hexdigest()
    rel_kb_path = (
        resolved_kb.relative_to(ROOT).as_posix()
        if resolved_kb.is_relative_to(ROOT)
        else str(resolved_kb)
    )
    return KBRelease(
        id=snapshot.context.kb_release_id,
        knowledge_base_path=rel_kb_path,
        checksums={"knowledge_base": checksum},
        provision_ids=selected_ids,
        supported_scope="; ".join(target_scopes),
    )


def infer_with_selected_release(
    snapshot: CaseSnapshot,
    registry: Sequence[ProvisionRecord] | None = None,
    *,
    scopes: Sequence[str] | None = None,
    artifact_dir: Path | str | None = None,
    run_rules: bool = True,
    max_iterations: int = 4,
) -> InferenceResult:
    try:
        release = select_release(snapshot, registry, scopes=scopes)
    except VersionConflictError as exc:
        conflict_code = f"VERSION_CONFLICT:{exc.scope}:{','.join(exc.provision_ids)}:{exc.assessed_on.isoformat()}"
        return InferenceResult(
            context=snapshot.context,
            consistency_status="VERSION_CONFLICT",
            conflicts=(conflict_code,),
        )
    return infer(
        prepare_facts(snapshot),
        release,
        artifact_dir=artifact_dir,
        run_rules=run_rules,
        max_iterations=max_iterations,
    )
