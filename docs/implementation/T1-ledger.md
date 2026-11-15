# SDD ledger — plan: docs/EnviroPermit_KBS_Project_Plan.md

Scope: T1 only. Specification and implementation plan are the same source.

- Ruling: execute the existing design directly; the user explicitly requested T1, including the engine architecture. Reopening design approval adds no missing decision.
- Ruling: use `reference/spike/EnviroPermit_KBS_Test/README.md`; the requested parent README is absent. Preserve the reference directory unchanged.
- Ruling: work in the supplied directory; there is no `.git`, so no branch/worktree or commit can be made without creating repository history. Leave commit pending instead of inventing history.
- Pre-flight: T1 → T2 consumes CaseSnapshot/KBRelease; T1 defines release checksums but does not implement legal-version selection. T1 → T4 consumes scoped facts/results; no fulfillment or initial-permit inference is claimed.
- T1 in progress: acceptance tests first against a neutral stub, then OWLAPI/HermiT and isolated SWRLAPI/Drools stage.
- RED: `pytest tests/test_reasoner_contract.py tests/regression -q` returned 13 expected assertion failures against the neutral stub. Log: `artifacts/t1-red.txt`.
- Ruling: pin OWLAPI 4.5.26 because Maven Central lacks the 4.5.27 parent POM; pin Jackson through its BOM and MVEL 2.5.2.Final to resolve observed compile/runtime incompatibilities. Cost: compatibility is claimed for the tested combination only.
- SWRL smoke GREEN: `test_swrl_materializes_candidate_and_core_reclassifies` passed with real SWRLAPI/Drools output and subsequent HermiT classification.
- Additional RED: direct CLI allowed overwriting existing stage OWL artifacts with a differently named response. `test_artifacts_cannot_be_overwritten` exposed this; CLI now checks all fixed output artifact names before inference.
- Full pre-review suite: 35 passed, 2 failed. One test expected the wrong spelling in OWLAPI's diagnostic (the profile rejection itself worked); the other exposed nondeterministic source-trace ordering between JVMs. Explicit subject/conclusion sorting replaces Map.toString sorting.
- Independent reviewer (read-only) identified missing provenance coverage, reserved response-name collision, and raw control-field type coercion. All three reproduced RED (`artifacts/review-red.txt`, `artifacts/iteration-red.txt`); fixes require complete/unambiguous provenance, protect reserved filenames, and validate boolean/integer control fields in both contracts.
- Final review scope rulings: current legal applicability remains T2; full scoped composition/fulfillment T4–T5; generic planning/OR T6; complete explanation/SPARQL T8; independent evaluation T10. These are retained boundaries of the requested T1, not completion claims for later tasks. Cost: this foundation must not be presented as the completed application or a real-project legal determination.
- Final: fixed provenance coverage — coverage tests RED→GREEN; fixed reserved response collision — collision test RED→GREEN; fixed control-field coercion — boolean/integer tests RED→GREEN. Full suite 46/46 green; no deferred minors.
- Final: fixed deterministic trace ordering — direct CLI/adapter parity test RED→GREEN. Corrected profile-test message expectation after confirming real OWLAPI rejection.
- Task T1: implementation and verification complete (no Git metadata, commit pending); `.venv/Scripts/python.exe scripts/verify.py --output artifacts/t1-final` → exit 0, 46 passed in 288.15s, core profile 169 axioms/0 violations, A/B/U consistent and C quarantined. Persisted facts and diagnostics reviewed from artifacts, summary copied to `docs/verification/T1-results.json`.
- Finish: supplied directory remains in place. No branch/merge/push operation applies because `.git` is absent; no user-owned files or reference spike files were removed.
