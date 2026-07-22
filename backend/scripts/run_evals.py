"""Print the adversarial-eval scorecard. Exit code 1 on any failure, so this
can gate CI or a pre-demo check."""

import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evals.runner import load_cases, run_case  # noqa: E402


def main() -> None:
    results = defaultdict(list)
    for case in load_cases():
        passed, detail = run_case(case)
        results[case["kind"]].append((case["id"], passed, detail))

    total = failed = 0
    for kind, rows in results.items():
        print(f"\n=== {kind} ===")
        for case_id, passed, detail in rows:
            total += 1
            failed += 0 if passed else 1
            print(f"  {'PASS' if passed else 'FAIL'}  {case_id:38s} {detail}")

    print(f"\n{total - failed}/{total} cases passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
