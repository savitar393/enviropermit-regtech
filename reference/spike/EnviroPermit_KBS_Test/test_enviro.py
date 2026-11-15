"""Source-derived acceptance cases. Expectations are not computed by the model."""
import copy
import unittest
from enviro import assess


BASE = {
    'id': 'A', 'existing_environmental_approval': True,
    'project_changes': ['CapacityIncrease'], 'changes_complete': True,
    'screening': 'UKL', 'surface_discharge': True,
    'existing_water_pertek': True, 'water_change': 'TreatmentDesignChange',
    'impact_extent': [True],
}


class Acceptance(unittest.TestCase):
    def case(self, **changes):
        data = copy.deepcopy(BASE)
        data.update(changes)
        return assess(data)

    def test_expansion_combines_environmental_and_water_obligations(self):
        r = self.case()
        self.assertEqual(r['status'], 'CONSISTENT')
        self.assertTrue({'amend_environmental_approval', 'prepare_new_environmental_documentation',
                         'amend_water_pertek', 'prepare_technical_study',
                         'water_pertek_required', 'water_slo_required'} <= set(r['obligations']))

    def test_second_design_selects_standard_documentation(self):
        r = self.case(id='B', impact_extent=[False])
        self.assertIn('prepare_standard_technical_documentation', r['obligations'])
        self.assertNotIn('prepare_technical_study', r['obligations'])

    def test_unknown_extent_never_defaults_to_no_change(self):
        r = self.case(id='U', impact_extent=[])
        self.assertIn('amend_water_pertek', r['obligations'])
        self.assertNotIn('prepare_technical_study', r['obligations'])
        self.assertNotIn('prepare_standard_technical_documentation', r['obligations'])
        self.assertIn('impact_extent_assessment', r['evidence_gaps'])

    def test_management_only_still_has_interacting_technical_dependency(self):
        r = self.case(id='M', project_changes=['ManagementMonitoringChange'],
                      water_change='WastewaterManagementChange', impact_extent=[False])
        self.assertIn('WithoutNewEnvironmentalDocumentation', r['conclusions'])
        self.assertIn('amend_water_pertek', r['obligations'])
        self.assertNotIn('prepare_new_environmental_documentation', r['obligations'])
        self.assertIn(['water_pertek_change_issued', 'environmental_change_issued'], r['precedence'])

    def test_identity_only_is_narrow_exception(self):
        r = self.case(id='I', project_changes=['IdentityChange'], water_change=None,
                      impact_extent=[])
        self.assertIn('amend_environmental_approval', r['obligations'])
        self.assertIn('WithoutNewEnvironmentalDocumentation', r['conclusions'])
        self.assertNotIn('amend_water_pertek', r['obligations'])

    def test_incomplete_change_inventory_does_not_prove_identity_only(self):
        r = self.case(id='O', project_changes=['IdentityChange'], changes_complete=False,
                      water_change=None, impact_extent=[])
        self.assertNotIn('WithoutNewEnvironmentalDocumentation', r['conclusions'])
        self.assertIn('complete_project_change_inventory', r['evidence_gaps'])

    def test_mixed_identity_and_capacity_does_not_erase_new_documentation(self):
        r = self.case(id='X', project_changes=['IdentityChange', 'CapacityIncrease'])
        self.assertIn('prepare_new_environmental_documentation', r['obligations'])
        self.assertNotIn('WithoutNewEnvironmentalDocumentation', r['conclusions'])

    def test_amdal_does_not_inherit_ukl_strict_application_order(self):
        r = self.case(id='D', screening='AMDAL')
        self.assertNotIn(['submit_water_pertek_change', 'submit_environmental_change'], r['precedence'])
        self.assertIn('ConcurrentSubmissionPermitted', r['conclusions'])
        self.assertIn(['water_pertek_change_issued', 'environmental_change_issued'], r['precedence'])

    def test_conflicting_impact_evidence_is_quarantined(self):
        r = self.case(id='C', impact_extent=[True, False])
        self.assertEqual(r['status'], 'INCONSISTENT')
        self.assertEqual(r['obligations'], [])

    def test_property_chain_creates_unasserted_case_obligation(self):
        r = self.case()
        self.assertFalse(r['case_obligations_asserted_before_reasoning'])
        self.assertIn('water_slo_required', r['obligations'])
        self.assertTrue(r['inverse_membership_inferred'])

    def test_unknown_proposed_screening_does_not_copy_old_regime(self):
        r = self.case(id='Q', screening=None)
        self.assertNotIn(['submit_water_pertek_change', 'submit_environmental_change'], r['precedence'])
        self.assertIn('proposed_activity_screening', r['evidence_gaps'])

    def test_outsourcing_does_not_become_automatic_exemption(self):
        r = self.case(id='T', surface_discharge=False, outsourcing_claim=True)
        self.assertNotIn('ExemptFromWaterObligations', r['conclusions'])
        self.assertIn('outsourced_wastewater_route_outside_verified_slice', r['evidence_gaps'])

    def test_missing_prior_pertek_does_not_use_amendment_route(self):
        r = self.case(id='P', existing_water_pertek=False)
        self.assertNotIn('amend_water_pertek', r['obligations'])
        self.assertIn('prior_water_pertek_or_initial_application_route', r['evidence_gaps'])

    def test_fresh_snapshot_does_not_keep_previous_document_branch(self):
        before = self.case(id='S', impact_extent=[True])
        after = self.case(id='S', impact_extent=[False])
        self.assertIn('prepare_technical_study', before['obligations'])
        self.assertNotIn('prepare_technical_study', after['obligations'])
        self.assertIn('prepare_standard_technical_documentation', after['obligations'])

    def test_two_distinct_snapshots_conflict_with_one_snapshot_contract(self):
        r = self.case(id='N', two_distinct_snapshots=True)
        self.assertEqual(r['status'], 'INCONSISTENT')

    def test_explanations_include_applicable_provisions(self):
        r = self.case()
        sources = {s for t in r['explanation'] for s in t['sources']}
        self.assertTrue({'PP22:89-90', 'P5:15', 'P5:16.1.a', 'P5:3'} <= sources)


if __name__ == '__main__':
    unittest.main(verbosity=2)
