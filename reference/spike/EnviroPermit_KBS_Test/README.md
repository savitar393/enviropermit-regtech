# EnviroPermit-KBS: feasibility spike

Prepared and run on 14 November 2026. This is a disposable, bounded reasoning
experiment supporting a project-selection decision. It is not a production
system or a determination of any real project's legal obligations.

## Reproduce

Use Python 3.12, a Java runtime available to Owlready2 and JPype, and a fresh
virtual environment. Commands below assume this directory is the working directory.

```bash
python -m pip install -r requirements.txt
python -m unittest -v
python export_cases.py
python check_owl_profile.py
python mutation_check.py
```

`enviro.py` builds the ontology, asserts hypothetical case facts, invokes HermiT,
and renders entailed obligations, ordering constraints and source mappings.
Python's evidence-gap checks request missing facts; they do not establish legal
exemptions. `cases.json` and `outputs/` contain the exported examples.

`test_enviro.py` defines 16 source-derived behavioral tests. Expected values were
written before implementing the ontology; `red_test_output.txt` records the
neutral baseline's 16 expected assertion failures. `test_output.txt` records the
passing run. `mutation_results.json` shows four intentional defects caught by
selected tests. Mutation tests patch the builder in memory and do not alter files.

`check_owl_profile.py` uses OWLAPI's OWL2DLProfile, not a text pattern checker.
`profile_results.json` covers every exported asserted ontology, including the
deliberately inconsistent case C. Syntactic profile validity is distinct from
semantic consistency.

## Interpretation

- CONSISTENT means consistent with this ontology, not environmentally acceptable,
  legally compliant, approved, or complete.
- Non-entailment is not proof that a requirement is absent.
- Empty `evidence_gaps` means only that the few implemented checks found no gap.
- Screening and impact-spread assessments are hypothetical supplied evidence.
  They are not inferred from a KBLI code or computed from physical measurements.
- `prepare_new_environmental_documentation` means the route in PP 22/2021
  articles 90-91; it does not select AMDAL, addendum type, or UKL-UPL forms.
- `water_slo_required` is an obligation to have SLO; it is not an instruction to
  obtain a new SLO in every scenario and does not assert that one has been issued.
- Precedence refers to distinct application and issuance events. The model does
  not infer issuance or approval success from an application.
- Explanations map entailed classes to curated source IDs and input facts.
  They are not minimal justifications automatically extracted from HermiT.
- No SWRL, SHACL, general legal-version resolver, user interface, or plan search
  engine has been implemented in this spike.

Sources and formalization assumptions are separated in `sources.json`.
Scope excludes domestic wastewater, feed-sector special provisions, emissions,
protected-area exceptions, authority assignment, new permits, outsourcing routes,
and automatic threshold screening. Such extensions need their own source review.

This experiment verifies selected formal behavior. Its cases and interpretations
were produced in the same work session; they are not an independent legal audit,
held-out benchmark, or evidence of predictive accuracy on real applications.
