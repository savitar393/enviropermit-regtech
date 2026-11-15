"""Local synthetic-case CLI. Output is a versioned InferenceResult."""
import argparse
from pathlib import Path

from .contracts import CaseSnapshot
from .inference import infer, load_release, prepare_facts


def main():
    parser = argparse.ArgumentParser(description="Penalaran kasus EnviroPermit T1")
    parser.add_argument("--case", type=Path, required=True)
    parser.add_argument("--release", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--core-only", action="store_true")
    args = parser.parse_args()
    snapshot = CaseSnapshot.model_validate_json(args.case.read_text(encoding="utf-8"))
    release = load_release(args.release) if args.release else load_release()
    result = infer(prepare_facts(snapshot), release, artifact_dir=args.output, run_rules=not args.core_only)
    print(result.model_dump_json(indent=2))
    return 0 if result.consistency_status == "CONSISTENT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
