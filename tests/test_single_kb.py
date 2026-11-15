import hashlib
from pathlib import Path
import pytest

from enviropermit.inference import ROOT, infer, prepare_facts


def test_release_has_one_knowledge_source(release):
    payload = release.model_dump()
    assert payload.get('knowledge_base_path') == 'kb/enviropermit.ttl'
    assert not {'core_path', 'rules_path', 'queries_path'} & payload.keys()


def changed_release(release, tmp_path, transform):
    path = ROOT / release.model_dump().get('knowledge_base_path', 'kb/core.owl')
    edited = tmp_path / 'edited.ttl'
    edited.write_text(transform(path.read_text(encoding='utf-8')), encoding='utf-8')
    return release.model_copy(update={'knowledge_base_path': str(edited),
        'checksums': {'knowledge_base': hashlib.sha256(edited.read_bytes()).hexdigest()}})


def test_rule_can_be_disabled_in_ttl_without_recompiling(case, release, tmp_path):
    assert 'knowledge_base_path' in release.model_dump()
    edited = changed_release(release, tmp_path, lambda s: s.replace('swrla:isRuleEnabled true', 'swrla:isRuleEnabled false'))
    result = infer(prepare_facts(case()), edited)
    assert 'prepare_technical_study' in result.project_obligations
    assert not result.fired_rules
    assert not any('ReviewableCandidate' in c for c in result.classifications.values())


def test_second_rule_in_ttl_is_discovered_without_code_change(case, release, tmp_path):
    assert 'knowledge_base_path' in release.model_dump()
    addition = '''
:ExtraReview a owl:Class .
[] a swrl:Imp ; rdfs:label "extra-review" ; swrla:isRuleEnabled true ;
   swrl:body ( [ a swrl:ClassAtom ; swrl:classPredicate :ReviewableCandidate ; swrl:argument1 :candidate ] ) ;
   swrl:head ( [ a swrl:ClassAtom ; swrl:classPredicate :ExtraReview ; swrl:argument1 :candidate ] ) .
'''
    result = infer(prepare_facts(case()), changed_release(release, tmp_path, lambda s: s + addition))
    assert any('ExtraReview' in c for c in result.classifications.values())
    assert {r.rule_id for r in result.fired_rules} == {'water-study-candidate', 'extra-review'}


def test_gap_requirement_is_read_from_ttl(case, release, tmp_path):
    assert 'knowledge_base_path' in release.model_dump()
    result = infer(prepare_facts(case('U')), changed_release(release, tmp_path,
        lambda s: s.replace('impact_extent_assessment', 'technical_finding_needed')))
    assert result.decisions[0].applicability == 'UNRESOLVED'
    assert result.decisions[0].evidence_gaps == ('technical_finding_needed',)


def test_unknown_metadata_reference_is_rejected(case, release, tmp_path):
    edited = changed_release(release, tmp_path, lambda s: s.replace(
        ':subjectClass :WaterTechnicalRevision', ':subjectClass :WaterTechnicalRevisionTypo'))
    with pytest.raises(RuntimeError, match='Invalid KB reference'):
        infer(prepare_facts(case('U')), edited)


def test_branch_metadata_preserves_full_iri(case, release, tmp_path):
    edited = changed_release(release, tmp_path, lambda s: s.replace(
        ':branchClass :TechnicalStudyBranch,', ':branchClass <urn:other#TechnicalStudyBranch>,')
        + '\n<urn:other#TechnicalStudyBranch> a owl:Class .\n')
    result = infer(prepare_facts(case()), edited)
    assert result.decisions[0].applicability == 'UNRESOLVED'


@pytest.mark.parametrize('old,new', [
    ('swrla:isRuleEnabled true', 'swrla:isRuleEnabled true, false'),
    ('swrla:isRuleEnabled true', 'swrla:isRuleEnabled "true"'),
    ('rdfs:label "water-study-candidate"', 'rdfs:label "water-study-candidate", "other-id"'),
])
def test_invalid_rule_annotations_are_rejected(old, new, case, release, tmp_path):
    edited = changed_release(release, tmp_path, lambda s: s.replace(old, new))
    with pytest.raises(RuntimeError, match='rule annotation'):
        infer(prepare_facts(case()), edited)
