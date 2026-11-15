"""Targeted adversarial mutations; never modify the saved source ontology."""
import io
import json
import unittest
from unittest.mock import patch
import enviro
from test_enviro import Acceptance

original = enviro.build_model
mutations = [
    ('remove_case_obligation_property_chain',
     'test_property_chain_creates_unasserted_case_obligation'),
    ('remove_water_change_property_hierarchy',
     'test_expansion_combines_environmental_and_water_obligations'),
    ('treat_incomplete_inventory_as_complete',
     'test_incomplete_change_inventory_does_not_prove_identity_only'),
    ('turn_unknown_extent_into_false',
     'test_unknown_extent_never_defaults_to_no_change'),
]
results = []
for name, test in mutations:
    def mutant(data, name=name):
        data = dict(data)
        if name == 'treat_incomplete_inventory_as_complete':
            data['changes_complete'] = True
        if name == 'turn_unknown_extent_into_false' and not data.get('impact_extent'):
            data['impact_extent'] = [False]
        world, onto, case, activity = original(data)
        if name == 'remove_case_obligation_property_chain':
            onto.caseObligation.property_chain = []
        if name == 'remove_water_change_property_hierarchy':
            onto.hasWaterTechnicalChange.is_a.remove(onto.hasTechnicalChange)
        return world, onto, case, activity
    with patch.object(enviro, 'build_model', mutant):
        stream = io.StringIO()
        result = unittest.TextTestRunner(stream=stream).run(Acceptance(test))
    results.append({'mutation':name, 'test':test,
                    'detected': len(result.failures) == 1 and not result.errors,
                    'failures':len(result.failures), 'errors':len(result.errors)})
print(json.dumps(results,indent=2))
if not all(r['detected'] for r in results):
    raise SystemExit(1)
