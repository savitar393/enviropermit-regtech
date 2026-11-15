"""Reproduce T1 verification, preserving request/response and OWL stage artifacts."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from enviropermit.contracts import NS, CaseSnapshot, Triple
from enviropermit.inference import ROOT, infer, java_command, load_release, prepare_facts


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True, help="New, empty verification directory")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise SystemExit("Verification directory must be empty")
    lock = json.loads((ROOT / "services/reasoner/dependencies.lock.json").read_text())
    actual = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
              for p in (ROOT / "services/reasoner/target/dependency").glob("*.jar")}
    if actual != lock:
        raise SystemExit("Java runtime dependencies differ from the tested lock; clean-build pinned dependencies")
    with (output / "pytest.txt").open("w", encoding="utf-8") as log:
        code = subprocess.call([sys.executable, "-m", "pytest", "-q", f"--junitxml={output / 'pytest.xml'}"],
                               cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
    print((output / "pytest.txt").read_text(), flush=True)
    if code:
        return code
    subprocess.run(java_command("profile", str(ROOT / "kb/enviropermit.ttl"), str(output / "core-profile.json")), check=True)
    summary = {}
    for name in ("A", "B", "U", "C"):
        snapshot = CaseSnapshot.model_validate_json((ROOT / f"cases/regression/water_spike/{name}.json").read_text())
        facts = prepare_facts(snapshot)
        result = infer(facts, load_release(), artifact_dir=output / name)
        triple = Triple(subject=facts.project_iri, predicate=NS + "projectObligation", object=NS + "water_slo_required")
        summary[name] = {
            "context": result.context.model_dump(mode="json"),
            "consistency_status": result.consistency_status,
            "project_obligations": result.project_obligations,
            "decisions": [d.model_dump(mode="json") for d in result.decisions],
            "profiles": {k: v.model_dump() for k, v in result.profiles.items()},
            "fired_rules": [r.model_dump() for r in result.fired_rules],
            "project_slo_asserted": triple in facts.asserted_triples,
            "project_slo_inferred_by_hermit": triple in result.core_inferred_triples,
        }
        print(f"{name}: {result.consistency_status}; obligations={len(result.project_obligations)}", flush=True)
    (output / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
