"""Decision traces, SPARQL query evaluation, and HTML/Markdown consultation reports."""
from __future__ import annotations

from collections.abc import Sequence
from html import escape
from pathlib import Path
import re
from urllib.parse import quote

from .contracts import (
    NS,
    RDF_TYPE,
    Applicability,
    AssessmentResult,
    ExplanationTrace,
    Fulfillment,
    ObligationAssessment,
    PlanCandidate,
    ProvisionRecord,
    SupportEdge,
    Triple,
)
from .inference import ROOT
from .planning import load_action_templates
from .scenarios import compare
from .sources import (
    audit_rule_sources,
    load_decision_sources,
    load_obligation_rules,
    load_registry,
)

_PREFIX_RE = re.compile(r"PREFIX\s+([A-Za-z0-9_-]*):\s*<([^>]+)>", re.IGNORECASE)
_SELECT_RE = re.compile(r"SELECT\s+(.*?)\s+WHERE\s*\{(.*)\}\s*\Z", re.IGNORECASE | re.DOTALL)
_OPTIONAL_RE = re.compile(r"OPTIONAL\s*\{([^{}]*)\}", re.IGNORECASE | re.DOTALL)
_EVIDENCE_REQ_RE = re.compile(
    r"(?m)^:([A-Za-z0-9_]+)\s+a\s+owl:NamedIndividual\s*,\s*:EvidenceRequirement\s*;(.*?\.)",
    re.DOTALL,
)
_STRING_RE = re.compile(r'"((?:[^"\\]|\\.)*)"')
_TOKEN_RE = re.compile(r":([A-Za-z0-9_]+)")


def _build_query_triples(
    result: AssessmentResult | None,
    kb_path: Path = ROOT / "kb/enviropermit.ttl",
) -> list[tuple[str, str, str]]:
    triples: set[tuple[str, str, str]] = set()

    if result is not None:
        if result.facts is not None:
            for t in result.facts.asserted_triples:
                triples.add((t.subject, t.predicate, t.object))
        if result.inference is not None:
            for t in result.inference.inferred_triples:
                triples.add((t.subject, t.predicate, t.object))
            for subj_iri, classes in result.inference.classifications.items():
                for cls_name in classes:
                    triples.add((subj_iri, RDF_TYPE, NS + cls_name))

    ob_rules = load_obligation_rules(kb_path)
    rule_sources = audit_rule_sources(kb_path)
    for ob_kind, cls_names in ob_rules.items():
        for cls_name in cls_names:
            triples.add((NS + cls_name, NS + "entailsObligation", NS + ob_kind))
            for src_id in rule_sources.get(cls_name, ()):
                triples.add((NS + cls_name, NS + "source_id", src_id))

    templates, edge_sources = load_action_templates()
    for tmpl in templates:
        for pred in tmpl.preconditions:
            triples.add((NS + tmpl.id, NS + "requiresStep", NS + pred))
        for rg in tmpl.requirement_groups:
            for member in rg.member_step_ids:
                triples.add((NS + tmpl.id, NS + "requiresStep", NS + member))
        for src_id in tmpl.supported_by:
            triples.add((NS + tmpl.id, NS + "source_id", src_id))
    for edge_key, edge_meta in edge_sources.items():
        if "->" in edge_key:
            before_step, after_step = edge_key.split("->", 1)
            triples.add((NS + after_step, NS + "requiresStep", NS + before_step))
            for src_id in edge_meta.get("provision_ids", ()):
                triples.add((NS + after_step, NS + "source_id", src_id))

    for idx, prov in enumerate(load_registry(kb_path)):
        prov_iri = f"{NS}provision_{idx}_{prov.id}"
        triples.add((prov_iri, RDF_TYPE, NS + "Provision"))
        triples.add((prov_iri, NS + "source_id", prov.id))
        triples.add((prov_iri, NS + "locator", prov.locator))
        triples.add((prov_iri, NS + "provisionScope", prov.scope))
        triples.add((prov_iri, NS + "reviewStatus", prov.review_status))

    kb_text = kb_path.read_text(encoding="utf-8")
    for match in _EVIDENCE_REQ_RE.finditer(kb_text):
        req_id, body = match.group(1), match.group(2)
        req_iri = NS + req_id
        triples.add((req_iri, RDF_TYPE, NS + "EvidenceRequirement"))
        subj_cls = re.search(r":subjectClass\s+:([A-Za-z0-9_]+)", body)
        if subj_cls:
            triples.add((req_iri, NS + "forDecision", NS + subj_cls.group(1)))
        missing_ev = re.search(r':missingEvidence\s+"([^"]+)"', body)
        if missing_ev:
            triples.add((req_iri, NS + "missingMessage", missing_ev.group(1)))
            triples.add((req_iri, NS + "source_id", missing_ev.group(1)))

    return sorted(triples)


def _expand_term(token: str, prefixes: dict[str, str]) -> str:
    token = token.strip()
    if token.startswith("?"):
        return token
    if token.startswith("<") and token.endswith(">"):
        return token[1:-1]
    if token.startswith('"') and token.endswith('"'):
        return token[1:-1]
    if token == "a":
        return RDF_TYPE
    if ":" in token:
        pfx, local = token.split(":", 1)
        if pfx in prefixes:
            return prefixes[pfx] + local
    return token


def _parse_bgp(block: str, prefixes: dict[str, str]) -> list[tuple[str, str, str]]:
    patterns: list[tuple[str, str, str]] = []
    for raw_stmt in block.split("."):
        stmt = raw_stmt.strip()
        if not stmt:
            continue
        tokens = re.findall(r'\?[A-Za-z0-9_]+|<[^>]+>|"(?:[^"\\]|\\.)*"|[A-Za-z0-9_:-]+', stmt)
        if len(tokens) >= 3:
            s = _expand_term(tokens[0], prefixes)
            p = _expand_term(tokens[1], prefixes)
            o = _expand_term(tokens[2], prefixes)
            patterns.append((s, p, o))
    return patterns


def _match_patterns(
    patterns: Sequence[tuple[str, str, str]],
    triples: Sequence[tuple[str, str, str]],
    initial_bindings: list[dict[str, str]],
) -> list[dict[str, str]]:
    bindings = list(initial_bindings)
    for s_pat, p_pat, o_pat in patterns:
        next_bindings: list[dict[str, str]] = []
        for b in bindings:
            s_val = b.get(s_pat[1:], s_pat) if s_pat.startswith("?") else s_pat
            p_val = b.get(p_pat[1:], p_pat) if p_pat.startswith("?") else p_pat
            o_val = b.get(o_pat[1:], o_pat) if o_pat.startswith("?") else o_pat
            for ts, tp, to in triples:
                if not s_pat.startswith("?") or s_pat[1:] in b:
                    if ts != s_val:
                        continue
                if not p_pat.startswith("?") or p_pat[1:] in b:
                    if tp != p_val:
                        continue
                if not o_pat.startswith("?") or o_pat[1:] in b:
                    if to != o_val:
                        continue
                new_b = dict(b)
                if s_pat.startswith("?"):
                    new_b[s_pat[1:]] = ts
                if p_pat.startswith("?"):
                    new_b[p_pat[1:]] = tp
                if o_pat.startswith("?"):
                    new_b[o_pat[1:]] = to
                next_bindings.append(new_b)
        bindings = next_bindings
    return bindings


def run_sparql_query(
    query_path: Path | str,
    result: AssessmentResult | None = None,
) -> list[dict[str, str]]:
    path = Path(query_path)
    query_text = path.read_text(encoding="utf-8") if path.is_file() else str(query_path)

    prefixes = {m.group(1): m.group(2) for m in _PREFIX_RE.finditer(query_text)}
    sel_match = _SELECT_RE.search(query_text)
    if not sel_match:
        raise ValueError(f"Invalid SPARQL SELECT query: {query_path}")

    vars_chunk, where_body = sel_match.group(1), sel_match.group(2)
    select_vars = [v[1:] for v in re.findall(r"\?[A-Za-z0-9_]+", vars_chunk)]

    optional_blocks = [m.group(1) for m in _OPTIONAL_RE.finditer(where_body)]
    required_body = _OPTIONAL_RE.sub("", where_body)

    req_patterns = _parse_bgp(required_body, prefixes)
    opt_pattern_groups = [_parse_bgp(opt, prefixes) for opt in optional_blocks]

    triples = _build_query_triples(result)
    bindings = _match_patterns(req_patterns, triples, [{}])

    for opt_patterns in opt_pattern_groups:
        extended_all: list[dict[str, str]] = []
        for b in bindings:
            ext = _match_patterns(opt_patterns, triples, [b])
            if ext:
                extended_all.extend(ext)
            else:
                extended_all.append(b)
        bindings = extended_all

    rows: list[dict[str, str]] = []
    seen: set[tuple[tuple[str, str], ...]] = set()
    for b in bindings:
        row = {var: b.get(var, "") for var in select_vars}
        key = tuple(sorted(row.items()))
        if key not in seen:
            seen.add(key)
            rows.append(row)
    return rows


def _resolve_target_obligation(
    result: AssessmentResult,
    conclusion_id: str,
) -> ObligationAssessment:
    parts = conclusion_id.split(":")
    for oa in result.obligation_assessments:
        full_id = f"{oa.subject_id}:{oa.scope_id}:{oa.obligation_kind}"
        short_id = f"{oa.subject_id}:{oa.obligation_kind}"
        if conclusion_id in (full_id, short_id, oa.obligation_kind):
            return oa
        if (
            len(parts) == 3
            and oa.subject_id == result.context.scenario_id
            and parts[0] == oa.scope_id
            and parts[1] == oa.scope_id
            and parts[2] == oa.obligation_kind
        ):
            return oa

    if conclusion_id in result.project_obligations:
        proj_id = result.snapshot.project_id if result.snapshot else result.context.scenario_id
        all_ev = tuple(sorted({ev for oa in result.obligation_assessments for ev in oa.evidence_ids}))
        all_prov = tuple(sorted({p for oa in result.obligation_assessments for p in oa.provision_ids}))
        all_rules = tuple(sorted({r for oa in result.obligation_assessments for r in oa.rule_ids}))
        return ObligationAssessment(
            assessment_id=result.assessment_id,
            subject_id=result.context.scenario_id,
            obligation_kind=conclusion_id,
            scope_id=proj_id,
            applicability=Applicability.APPLICABLE,
            fulfillment=Fulfillment.UNKNOWN,
            evidence_ids=all_ev or ("configuration",),
            provision_ids=all_prov or ("P5:3",),
            rule_ids=all_rules or ("RegulatedSurfaceDischarge",),
        )

    raise KeyError(f"Conclusion '{conclusion_id}' not found in assessment '{result.assessment_id}'")


def explain(result: AssessmentResult, conclusion_id: str) -> ExplanationTrace:
    oa = _resolve_target_obligation(result, conclusion_id)
    canonical_id = f"{oa.subject_id}:{oa.scope_id}:{oa.obligation_kind}"

    kb_path = ROOT / "kb/enviropermit.ttl"
    rule_sources = audit_rule_sources(kb_path)
    decision_sources = load_decision_sources(kb_path)
    registry_by_id: dict[str, ProvisionRecord] = {p.id: p for p in load_registry(kb_path)}

    supporting_triples: list[Triple] = []
    supporting_fact_ids: set[str] = set(oa.evidence_ids)
    fired_rule_ids: set[str] = set()

    if result.facts is not None:
        ns = result.facts.namespace
        target_subjects = {
            f"{ns}scenario"
            if oa.subject_id == result.context.scenario_id
            else f"{ns}activity-{quote(oa.subject_id, safe='-_')}"
        }
        if oa.subject_id == result.context.scenario_id:
            for act in (result.snapshot.activities if result.snapshot else ()):
                target_subjects.add(f"{ns}activity-{quote(act.id, safe='-_')}")

        child_subjects: set[str] = set()
        for t in result.facts.asserted_triples:
            if t.subject in target_subjects and t.object.startswith(ns):
                child_subjects.add(t.object)

        all_target_subjects = target_subjects | child_subjects
        prov_by_idx = {p.fact_index: p.evidence_id for p in result.facts.provenance}
        for idx, t in enumerate(result.facts.asserted_triples):
            if t.subject in all_target_subjects:
                supporting_triples.append(t)
                ev_id = prov_by_idx.get(idx)
                if ev_id:
                    supporting_fact_ids.add(ev_id)

    if result.inference is not None and result.facts is not None:
        ns = result.facts.namespace
        cand_iri = f"{ns}study-candidate-{quote(oa.subject_id, safe='-_')}"
        act_iri = f"{ns}activity-{quote(oa.subject_id, safe='-_')}"
        for fired in result.inference.fired_rules:
            for concl in fired.conclusions:
                if concl.subject in (cand_iri, act_iri):
                    fired_rule_ids.add(fired.rule_id)

    axiom_rule_ids = tuple(sorted(set(oa.rule_ids) | fired_rule_ids))

    prov_ids: set[str] = set(oa.provision_ids)
    for r_id in axiom_rule_ids:
        prov_ids.update(rule_sources.get(r_id, ()))
        prov_ids.update(decision_sources.get(r_id, ()))
    provision_ids = tuple(sorted(prov_ids))
    provisions = tuple(registry_by_id[pid] for pid in provision_ids if pid in registry_by_id)

    assumptions = tuple(
        f"{p.id} [{p.review_status}]: {p.interpretation_note}"
        for p in provisions
        if p.review_status == "MODEL_ASSUMPTION" or p.id.startswith("MODEL:")
    )

    unresolved_gaps: set[str] = set()
    if oa.applicability == Applicability.UNRESOLVED and result.inference is not None:
        for dec in result.inference.decisions:
            if dec.id == oa.obligation_kind or dec.subject_id.endswith(oa.subject_id):
                unresolved_gaps.update(dec.evidence_gaps)
        if not unresolved_gaps:
            unresolved_gaps.update(result.evidence_gaps)

    edges: list[SupportEdge] = []
    for fact_id in sorted(supporting_fact_ids):
        for r_id in axiom_rule_ids:
            edges.append(
                SupportEdge(
                    from_node=f"fact:{fact_id}",
                    to_node=f"rule:{r_id}",
                    relation="FACT_SUPPORTS_RULE",
                )
            )
    for r_id in axiom_rule_ids:
        r_provs = rule_sources.get(r_id) or decision_sources.get(r_id) or provision_ids
        for pid in sorted(set(r_provs)):
            edges.append(
                SupportEdge(
                    from_node=f"provision:{pid}",
                    to_node=f"rule:{r_id}",
                    relation="PROVISION_BACKS_RULE",
                )
            )
        edges.append(
            SupportEdge(
                from_node=f"rule:{r_id}",
                to_node=f"conclusion:{canonical_id}",
                relation="RULE_INFERS_CONCLUSION",
            )
        )
    for gap_id in sorted(unresolved_gaps):
        edges.append(
            SupportEdge(
                from_node=f"gap:{gap_id}",
                to_node=f"conclusion:{canonical_id}",
                relation="EVIDENCE_GAP_BLOCKS_DECISION",
            )
        )

    summary = (
        f"Kesimpulan '{oa.obligation_kind}' pada subjek '{oa.subject_id}' (cakupan '{oa.scope_id}') "
        f"berstatus {oa.applicability}/{oa.fulfillment} berdasarkan bukti "
        f"{list(sorted(supporting_fact_ids))}, aturan {list(axiom_rule_ids)}, "
        f"dan ketentuan {list(provision_ids)}."
    )

    return ExplanationTrace(
        conclusion_id=canonical_id,
        subject_id=oa.subject_id,
        scope_id=oa.scope_id,
        obligation_kind=oa.obligation_kind,
        applicability=oa.applicability,
        fulfillment=oa.fulfillment,
        derivation_kind="SUPPORTING_PATH",
        supporting_fact_ids=tuple(sorted(supporting_fact_ids)),
        supporting_triples=tuple(supporting_triples),
        axiom_rule_ids=axiom_rule_ids,
        fired_rule_ids=tuple(sorted(fired_rule_ids)),
        support_edges=tuple(edges),
        provision_ids=provision_ids,
        provisions=provisions,
        assumptions=assumptions,
        unresolved_evidence_ids=tuple(sorted(unresolved_gaps)),
        summary=summary,
    )


def explain_scenario_change(
    left: AssessmentResult,
    right: AssessmentResult,
    conclusion_id: str,
) -> dict[str, object]:
    diff = compare(left, right)
    parts = conclusion_id.split(":")
    target_change = None
    for ch in diff.obligation_changes:
        full_id = f"{ch.subject_id}:{ch.scope_id}:{ch.obligation_kind}"
        short_id = f"{ch.subject_id}:{ch.obligation_kind}"
        if conclusion_id in (full_id, short_id, ch.obligation_kind):
            target_change = ch
            break
        if len(parts) == 3 and ch.subject_id == parts[0] and ch.obligation_kind == parts[2]:
            target_change = ch
            break

    if target_change is None:
        raise KeyError(f"Conclusion '{conclusion_id}' not found in scenario diff")

    subj_changes = [
        {
            "subject_id": ic.subject_id,
            "field": ic.field,
            "operation": ic.operation,
            "old_value": ic.old_value,
            "new_value": ic.new_value,
            "evidence_ids": list(ic.evidence_ids),
        }
        for ic in diff.input_changes
        if ic.subject_id == target_change.subject_id
        or (
            left.snapshot is not None
            and target_change.subject_id == left.snapshot.project_id
        )
    ]

    left_trace: ExplanationTrace | None = None
    right_trace: ExplanationTrace | None = None
    try:
        left_trace = explain(left, conclusion_id)
    except KeyError:
        pass
    try:
        right_trace = explain(right, conclusion_id)
    except KeyError:
        for oa in right.obligation_assessments:
            if oa.subject_id == target_change.subject_id and oa.scope_id == target_change.scope_id:
                right_trace = explain(
                    right, f"{oa.subject_id}:{oa.scope_id}:{oa.obligation_kind}"
                )
                break

    left_ev = list(left_trace.supporting_fact_ids) if left_trace else []
    right_ev = (
        list(right_trace.supporting_fact_ids)
        if right_trace
        else list(target_change.evidence_ids)
    )
    unresolved_gaps = (
        list(right_trace.unresolved_evidence_ids)
        if right_trace and right_trace.unresolved_evidence_ids
        else list(diff.added_evidence_gaps)
    )

    return {
        "conclusion_id": f"{target_change.subject_id}:{target_change.scope_id}:{target_change.obligation_kind}",
        "subject_id": target_change.subject_id,
        "scope_id": target_change.scope_id,
        "obligation_kind": target_change.obligation_kind,
        "change_kind": target_change.change_kind,
        "is_obligation_saving": target_change.is_obligation_saving,
        "reason": target_change.reason,
        "changed_input_facts": subj_changes,
        "left_evidence_ids": left_ev,
        "right_evidence_ids": right_ev,
        "provision_ids": list(target_change.provision_ids),
        "unresolved_evidence_gaps": unresolved_gaps,
        "left_trace": left_trace.model_dump(mode="json") if left_trace else None,
        "right_trace": right_trace.model_dump(mode="json") if right_trace else None,
    }


def render_report(
    result: AssessmentResult,
    plans: Sequence[PlanCandidate],
    *,
    format: str = "html",
) -> str:
    traces = [
        explain(result, f"{oa.subject_id}:{oa.scope_id}:{oa.obligation_kind}")
        for oa in result.obligation_assessments
    ]
    if format.lower() == "json":
        import json

        return json.dumps(
            {
                "assessment": result.model_dump(mode="json", exclude={"facts", "inference"}),
                "traces": [t.model_dump(mode="json") for t in traces],
                "plans": [p.model_dump(mode="json") for p in plans],
            },
            indent=2,
        )

    rows_html: list[str] = []
    for oa in result.obligation_assessments:
        rows_html.append(
            "<tr>"
            f"<td>{escape(oa.subject_id)}</td>"
            f"<td>{escape(oa.scope_id)}</td>"
            f"<td><code>{escape(oa.obligation_kind)}</code></td>"
            f"<td><strong>{escape(oa.applicability.value)}</strong></td>"
            f"<td>{escape(oa.fulfillment.value)}</td>"
            f"<td>{escape(', '.join(oa.evidence_ids))}</td>"
            f"<td>{escape(', '.join(oa.rule_ids))}</td>"
            f"<td>{escape(', '.join(oa.provision_ids))}</td>"
            "</tr>"
        )

    trace_cards: list[str] = []
    for tr in traces:
        prov_items: list[str] = []
        for p in tr.provisions:
            badge = (
                ' <span class="badge-assumption">[MODEL_ASSUMPTION]</span>'
                if p.review_status == "MODEL_ASSUMPTION" or p.id.startswith("MODEL:")
                else ' <span class="badge-verified">[VERIFIED]</span>'
            )
            url_html = (
                f' — <a href="{escape(p.source_url)}">{escape(p.source_url)}</a>'
                if p.source_url
                else ""
            )
            prov_items.append(
                f"<li><code>{escape(p.id)}</code> ({escape(p.locator)}){badge}: "
                f"{escape(p.interpretation_note)}{url_html}</li>"
            )
        assumptions_html = ""
        if tr.assumptions:
            items = "".join(f"<li>{escape(a)}</li>" for a in tr.assumptions)
            assumptions_html = f'<div class="assumptions"><strong>Asumsi Pemodelan (MODEL_ASSUMPTION):</strong><ul>{items}</ul></div>'

        trace_cards.append(
            f'<section class="trace-card" id="{escape(tr.conclusion_id)}">'
            f"<h3>{escape(tr.conclusion_id)} ({escape(tr.derivation_kind)})</h3>"
            f"<p>{escape(tr.summary)}</p>"
            f"<p><strong>Bukti Masukan:</strong> {escape(', '.join(tr.supporting_fact_ids))}</p>"
            f"<p><strong>Aturan OWL/SWRL:</strong> {escape(', '.join(tr.axiom_rule_ids))}</p>"
            f"<ul>{''.join(prov_items)}</ul>"
            f"{assumptions_html}"
            "</section>"
        )

    plan_sections: list[str] = []
    for plan in plans:
        step_rows = "".join(
            "<tr>"
            f"<td><code>{escape(step.id)}</code></td>"
            f"<td>{escape(step.title)}</td>"
            f"<td>{escape(step.subject_id)} ({escape(step.scope_id)})</td>"
            f"<td>{escape(step.kind)}</td>"
            f"<td><strong>{escape(step.status.value)}</strong></td>"
            f"<td>{escape(', '.join(step.predecessor_ids))}</td>"
            "</tr>"
            for step in plan.action_instances
        )
        blocker_items = "".join(
            f"<li><code>{escape(b.step_id)}</code> [{escape(b.status)}]: {escape(b.reason)}</li>"
            for b in plan.blockers
        )
        plan_sections.append(
            f'<section class="plan-card">'
            f"<h3>Kandidat Rencana: {escape(plan.id)} ({escape(plan.branch_label)})</h3>"
            f"<table><thead><tr><th>ID Langkah</th><th>Tindakan</th><th>Subjek</th>"
            f"<th>Jenis</th><th>Status</th><th>Prasyarat</th></tr></thead>"
            f"<tbody>{step_rows}</tbody></table>"
            f"<h4>Hambatan (Blockers)</h4><ul>{blocker_items or '<li>Tidak ada hambatan.</li>'}</ul>"
            "</section>"
        )

    gaps_html = "".join(f"<li><code>{escape(g)}</code></li>" for g in result.evidence_gaps)
    goal_text = escape(result.snapshot.goal) if result.snapshot else "-"

    return (
        "<!DOCTYPE html>\n"
        '<html lang="id">\n'
        "<head>\n"
        '  <meta charset="utf-8" />\n'
        f"  <title>Laporan Penilaian EnviroPermit-KBS — {escape(result.assessment_id)}</title>\n"
        "  <style>\n"
        "    body { font-family: system-ui, sans-serif; margin: 2rem; line-height: 1.5; color: #1e293b; }\n"
        "    table { border-collapse: collapse; width: 100%; margin-bottom: 1.5rem; }\n"
        "    th, td { border: 1px solid #cbd5e1; padding: 0.5rem 0.75rem; text-align: left; }\n"
        "    th { background: #f1f5f9; }\n"
        "    .trace-card, .plan-card { border: 1px solid #e2e8f0; border-radius: 6px; padding: 1rem; margin-bottom: 1rem; }\n"
        "    .badge-assumption { background: #fef3c7; color: #92400e; padding: 0.1rem 0.4rem; border-radius: 4px; font-weight: 600; }\n"
        "    .badge-verified { background: #dcfce7; color: #166534; padding: 0.1rem 0.4rem; border-radius: 4px; font-weight: 600; }\n"
        "  </style>\n"
        "</head>\n"
        "<body>\n"
        f"  <h1>Laporan Konsultasi Kewajiban Lingkungan — {escape(result.assessment_id)}</h1>\n"
        f"  <p><strong>Skenario:</strong> {escape(result.context.scenario_id)} | "
        f"<strong>Snapshot Bukti:</strong> {escape(result.context.evidence_snapshot_id)} | "
        f"<strong>Tanggal Penilaian:</strong> {escape(str(result.context.assessed_on))} | "
        f"<strong>Versi KB:</strong> {escape(result.kb_version)} | "
        f"<strong>Status Konsistensi:</strong> {escape(result.consistency_status)}</p>\n"
        f"  <p><strong>Tujuan Proyek:</strong> {goal_text}</p>\n"
        "  <h2>1. Ringkasan Kewajiban per Kegiatan dan Cakupan</h2>\n"
        "  <table>\n"
        "    <thead><tr><th>Subjek</th><th>Cakupan</th><th>Kewajiban</th><th>Applicability</th>"
        "<th>Fulfillment</th><th>Bukti</th><th>Aturan</th><th>Ketentuan</th></tr></thead>\n"
        f"    <tbody>{''.join(rows_html)}</tbody>\n"
        "  </table>\n"
        "  <h2>2. Kesenjangan Bukti (Evidence Gaps)</h2>\n"
        f"  <ul>{gaps_html or '<li>Tidak ada kesenjangan bukti.</li>'}</ul>\n"
        "  <h2>3. Jejak Alasan dan Sumber Hukum (Decision Traces)</h2>\n"
        f"  {''.join(trace_cards)}\n"
        "  <h2>4. Rencana Persetujuan dan Diagnosis Hambatan</h2>\n"
        f"  {''.join(plan_sections)}\n"
        "</body>\n"
        "</html>\n"
    )
