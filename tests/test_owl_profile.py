import hashlib
import json
import re
import subprocess
from enviropermit.inference import ROOT, infer, java_command, prepare_facts


def modified(release, tmp_path, text):
    path = tmp_path / 'modified.ttl'
    path.write_text(text,encoding='utf-8')
    return path, release.model_copy(update={'knowledge_base_path':str(path),
        'checksums':{'knowledge_base':hashlib.sha256(path.read_bytes()).hexdigest()}})


def test_profile_checker_rejects_cardinality_on_chain_result(release, tmp_path):
    text = (ROOT / 'kb/enviropermit.ttl').read_text(encoding='utf-8')
    text += '\n:Project rdfs:subClassOf [ a owl:Restriction ; owl:onProperty :projectObligation ; owl:maxQualifiedCardinality "1"^^xsd:nonNegativeInteger ; owl:onClass :ObligationKind ] .\n'
    path, _ = modified(release, tmp_path, text)
    output = tmp_path / 'profile.json'
    completed = subprocess.run(java_command('profile', str(path), str(output)),capture_output=True,text=True)
    assert completed.returncode == 2, completed.stderr
    report = json.loads(output.read_text())
    assert not report['in_owl2_dl_profile']
    assert any('non-simple property' in v.lower() for v in report['violations'])


def test_subproperty_hierarchy_is_required_for_amendment(case, release, tmp_path):
    text = (ROOT / 'kb/enviropermit.ttl').read_text(encoding='utf-8')
    mutant, count = re.subn(r'rdfs:subPropertyOf\s+:hasTechnicalChange', 'rdfs:comment "hierarchy removed"', text)
    assert count == 1
    _, changed = modified(release, tmp_path, mutant)
    result = infer(prepare_facts(case()), changed, run_rules=False)
    assert result.consistency_status == 'CONSISTENT'
    assert 'water_slo_required' in result.project_obligations
    assert 'amend_water_pertek' not in result.project_obligations


def test_property_chain_is_required_for_project_obligation(case, release, tmp_path):
    text = (ROOT / 'kb/enviropermit.ttl').read_text(encoding='utf-8')
    mutant, count = re.subn(r'owl:propertyChainAxiom\s*\(\s*:hasActivity\s+:activityObligation\s*\)', 'rdfs:comment "chain removed"', text)
    assert count == 1
    _, changed = modified(release, tmp_path, mutant)
    result = infer(prepare_facts(case()), changed, run_rules=False)
    assert 'water_slo_required' not in result.project_obligations
    assert 'amend_environmental_approval' in result.project_obligations
    assert any(t.predicate.endswith('#activityObligation') and t.object.endswith('#water_slo_required') for t in result.core_inferred_triples)
