"""Throwaway OWL reasoning spike. No real-world permit determinations.

Legal classifications and ordering edges are derived by HermiT. Python only
loads explicit fixture facts, renders entailments, and flags missing evidence.
Source mappings are in sources.json. Each run gets an isolated OWL World.
"""
import json
import types
from pathlib import Path
from owlready2 import (World, Thing, ObjectProperty, DataProperty,
                      AnnotationProperty, FunctionalProperty, PropertyChain,
                      OneOf, AllDisjoint, AllDifferent, sync_reasoner,
                      OwlReadyInconsistentOntologyError)

BASE_IRI = 'https://example.org/enviropermit-spike/2026-11-14#'


def build_model(data):
    world = World()
    onto = world.get_ontology(BASE_IRI)
    with onto:
        names = ['Case', 'Snapshot', 'EnvironmentalApproval', 'WaterPertek',
                 'Screening', 'ProjectChange', 'NewDocChange', 'NoNewDocChange',
                 'CapacityIncrease', 'IdentityChange', 'ManagementMonitoringChange',
                 'WaterActivity', 'SurfaceWater', 'TechnicalWaterChange',
                 'TreatmentDesignChange', 'WastewaterManagementChange',
                 'ImpactAssessment', 'ObligationKind', 'PlanEdge', 'StepKind']
        for name in names:
            types.new_class(name, (Thing,))
        for name in ['hasSnapshot', 'hasExistingApproval', 'hasScreening',
                     'hasProjectChange', 'hasActivity', 'isActivityOf',
                     'dischargesTo', 'hasCurrentPertek', 'hasTechnicalChange',
                     'hasWaterTechnicalChange', 'hasImpactAssessment',
                     'caseObligation', 'activityObligation', 'hasPlanEdge',
                     'edgeBefore', 'edgeAfter']:
            types.new_class(name, (ObjectProperty,))
        class extentChanges(DataProperty, FunctionalProperty):
            range = [bool]
        class source_id(AnnotationProperty):
            pass

        onto.NewDocChange.is_a.append(onto.ProjectChange)
        onto.NoNewDocChange.is_a.append(onto.ProjectChange)
        onto.CapacityIncrease.is_a.append(onto.NewDocChange)
        onto.IdentityChange.is_a.append(onto.NoNewDocChange)
        onto.ManagementMonitoringChange.is_a.append(onto.NoNewDocChange)
        onto.TreatmentDesignChange.is_a.append(onto.TechnicalWaterChange)
        onto.WastewaterManagementChange.is_a.append(onto.TechnicalWaterChange)
        AllDisjoint([onto.NewDocChange, onto.NoNewDocChange])
        onto.hasWaterTechnicalChange.is_a.append(onto.hasTechnicalChange)
        onto.hasActivity.inverse_property = onto.isActivityOf
        onto.Case.is_a.append(onto.hasSnapshot.exactly(1, onto.Snapshot))
        onto.caseObligation.property_chain.append(
            PropertyChain([onto.hasActivity, onto.activityObligation]))
        ukl = onto.Screening('UKL')
        amdal = onto.Screening('AMDAL')
        AllDifferent([ukl, amdal])

        actions = {n: onto.ObligationKind(n) for n in [
            'amend_environmental_approval', 'prepare_new_environmental_documentation',
            'water_pertek_required', 'water_slo_required', 'amend_water_pertek',
            'prepare_technical_study', 'prepare_standard_technical_documentation']}
        steps = {n: onto.StepKind(n) for n in [
            'submit_water_pertek_change', 'submit_environmental_change',
            'water_pertek_change_issued', 'environmental_change_issued']}

        def derived(name, expression, sources, obligations=(), activity=False):
            c = types.new_class(name, (Thing,))
            c.equivalent_to.append(expression)
            c.source_id = sources
            prop = onto.activityObligation if activity else onto.caseObligation
            for obligation in obligations:
                c.is_a.append(prop.value(actions[obligation]))
            return c

        has_approval = onto.hasExistingApproval.some(onto.EnvironmentalApproval)
        amendment = derived('EnvironmentalAmendment',
            onto.Case & has_approval & onto.hasProjectChange.some(onto.ProjectChange),
            ['PP22:89-90'], ['amend_environmental_approval'])
        newdoc = derived('WithNewEnvironmentalDocumentation',
            amendment & onto.hasProjectChange.some(onto.NewDocChange),
            ['PP22:89-90'], ['prepare_new_environmental_documentation'])
        nonew = derived('WithoutNewEnvironmentalDocumentation',
            amendment & onto.hasProjectChange.some(onto.NoNewDocChange)
            & onto.hasProjectChange.only(onto.NoNewDocChange),
            ['PP22:89-90', 'MODEL:closure'])
        AllDisjoint([newdoc, nonew])

        scoped = derived('ScreenedCase',
            onto.Case & onto.hasScreening.some(OneOf([ukl, amdal])),
            ['MODEL:screening'])
        water = derived('RegulatedSurfaceDischarge',
            onto.WaterActivity & onto.dischargesTo.some(onto.SurfaceWater)
            & onto.isActivityOf.some(scoped),
            ['P5:3'], ['water_pertek_required', 'water_slo_required'], activity=True)
        revision = derived('WaterTechnicalRevision',
            onto.WaterActivity & onto.dischargesTo.some(onto.SurfaceWater)
            & onto.hasCurrentPertek.some(onto.WaterPertek)
            & onto.hasTechnicalChange.some(onto.TechnicalWaterChange),
            ['P5:15'], ['amend_water_pertek'], activity=True)
        study = derived('TechnicalStudyBranch',
            revision & onto.hasImpactAssessment.some(
                onto.ImpactAssessment & onto.extentChanges.value(True)),
            ['P5:16.1.a'], ['prepare_technical_study'], activity=True)
        standard = derived('TechnicalStandardBranch',
            revision & onto.hasImpactAssessment.some(
                onto.ImpactAssessment & onto.extentChanges.value(False)),
            ['P5:16.1.b'], ['prepare_standard_technical_documentation'], activity=True)
        AllDisjoint([study, standard])

        interaction = derived('InteractingAmendments',
            amendment & onto.hasActivity.some(revision),
            ['P5:14', 'P5:15'])
        strict = derived('UKLSubmissionSequence',
            interaction & onto.hasScreening.value(ukl),
            ['P5:8.2', 'P5:16.2'])
        derived('ConcurrentSubmissionPermitted',
            interaction & onto.hasScreening.value(amdal),
            ['P5:8.1', 'P5:16.2'])
        derived('ManagementTechnicalDependency',
            nonew & onto.hasProjectChange.some(onto.ManagementMonitoringChange)
            & onto.hasActivity.some(revision), ['PP22:93.2'])

        for name, cls, before, after, refs in [
            ('technical_issue_before_environmental_issue', interaction,
             'water_pertek_change_issued', 'environmental_change_issued', ['P5:14']),
            ('ukl_application_order', strict,
             'submit_water_pertek_change', 'submit_environmental_change', ['P5:8.2','P5:16.2'])]:
            edge = onto.PlanEdge(name)
            edge.edgeBefore = [steps[before]]
            edge.edgeAfter = [steps[after]]
            edge.source_id = refs
            cls.is_a.append(onto.hasPlanEdge.value(edge))

        # Hypothetical evidence in one immutable assessment snapshot.
        case = onto.Case('case_' + data['id'])
        snap = onto.Snapshot('snapshot_' + data['id'])
        case.hasSnapshot = [snap]
        if data.get('two_distinct_snapshots'):
            snap2 = onto.Snapshot('second_snapshot_' + data['id'])
            case.hasSnapshot.append(snap2)
            AllDifferent([snap, snap2])
        if data.get('existing_environmental_approval'):
            case.hasExistingApproval = [onto.EnvironmentalApproval('existing_env_approval')]
        if data.get('screening'):
            case.hasScreening = [onto[data['screening']]]
        changes = [onto[k]('project_change_' + str(i))
                   for i,k in enumerate(data.get('project_changes', []))]
        case.hasProjectChange = changes
        if changes and data.get('changes_complete'):
            # Explicitly certified inventory, not absence-as-negation.
            case.is_a.append(onto.hasProjectChange.only(OneOf(changes)))
            if len(changes) > 1:
                AllDifferent(changes)

        activity = onto.WaterActivity('water_activity_' + data['id'])
        case.hasActivity = [activity]
        if data.get('surface_discharge'):
            activity.dischargesTo = [onto.SurfaceWater('receiving_surface_water')]
        if data.get('existing_water_pertek'):
            activity.hasCurrentPertek = [onto.WaterPertek('existing_water_pertek')]
        if data.get('water_change'):
            activity.hasWaterTechnicalChange = [onto[data['water_change']]('water_change')]
        impacts = data.get('impact_extent', [])
        if impacts:
            evidence = onto.ImpactAssessment('impact_assessment')
            # Assign through the property index to preserve contradictions in a fixture.
            onto.extentChanges[evidence] = impacts
            activity.hasImpactAssessment = [evidence]
    return world, onto, case, activity


def assess(data, export_dir=None):
    world, onto, case, activity = build_model(data)
    asserted = bool(case.caseObligation)
    if export_dir:
        Path(export_dir).mkdir(parents=True, exist_ok=True)
        onto.save(file=str(Path(export_dir) / (data['id'] + '_asserted.owl')))
    try:
        sync_reasoner(world, infer_property_values=True, debug=0)
    except OwlReadyInconsistentOntologyError:
        world.close()
        return {'status':'INCONSISTENT', 'obligations':[], 'conclusions':[],
                'precedence':[], 'evidence_gaps':[], 'explanation':[],
                'case_obligations_asserted_before_reasoning':asserted,
                'inverse_membership_inferred':False}

    classified = sorted({c.name for item in [case,activity]
                         for c in item.INDIRECT_is_a if isinstance(c, type)})
    explanation = []
    for item in [case, activity]:
        for c in item.INDIRECT_is_a:
            if isinstance(c, type) and c.namespace.ontology == onto and c.source_id:
                explanation.append({'subject':item.name, 'conclusion':c.name,
                                    'sources':list(c.source_id)})
    explanation.sort(key=lambda x:(x['subject'],x['conclusion']))
    edges = sorted([[e.edgeBefore[0].name,e.edgeAfter[0].name] for e in case.hasPlanEdge])
    gaps = []
    # Completeness checks request evidence; they never derive legal exemptions.
    if 'WaterTechnicalRevision' in classified and not data.get('impact_extent'):
        gaps.append('impact_extent_assessment')
    if not data.get('changes_complete'):
        gaps.append('complete_project_change_inventory')
    if not data.get('screening'):
        gaps.append('proposed_activity_screening')
    if data.get('outsourcing_claim'):
        gaps.append('outsourced_wastewater_route_outside_verified_slice')
    if data.get('water_change') and not data.get('existing_water_pertek'):
        gaps.append('prior_water_pertek_or_initial_application_route')
    result = {'status':'CONSISTENT', 'obligations':sorted(v.name for v in case.caseObligation),
              'conclusions':classified, 'precedence':edges, 'evidence_gaps':gaps,
              'explanation':explanation,
              'case_obligations_asserted_before_reasoning':asserted,
              'inverse_membership_inferred':case in activity.isActivityOf}
    if export_dir:
        world.as_rdflib_graph().serialize(
            destination=str(Path(export_dir)/(data['id']+'_inferred.ttl')),format='turtle')
        (Path(export_dir)/(data['id']+'_result.json')).write_text(
            json.dumps(result,indent=2,ensure_ascii=False)+'\n')
    world.close()
    return result
