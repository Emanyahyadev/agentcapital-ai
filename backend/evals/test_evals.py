"""Adversarial evals run as part of the pytest suite — a regression in any
threshold, regex, or reconciliation rule fails CI, not the demo."""

import pytest

from evals.runner import load_cases, run_case

CASES = load_cases()


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_adversarial_case(case):
    passed, detail = run_case(case)
    assert passed, f"[{case['id']}] {detail}"
