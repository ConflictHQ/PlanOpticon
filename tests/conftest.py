"""Test tiers: every test declares exactly one tier marker.

Tiers decide when a test runs (see docs/contributing.md#test-tiers):

    always     every local run, pre-commit, every CI run   (whole tier < 2 min)
    sometimes  every PR                                     (< 10 min)
    rarely     nightly on main, before a release            (< 60 min)
    edge       before a release, on demand                  (no limit)
    debug      only when named explicitly                   (never gates)

Collection fails for a test with no tier or more than one, so a new test has to
choose. Set the tier per module with ``pytestmark = pytest.mark.always`` or per
test with a decorator.
"""

import pytest

TIERS = ("always", "sometimes", "rarely", "edge", "debug")

pytest_plugins = ["pytester"]


def pytest_collection_modifyitems(config, items):
    problems = []
    for item in items:
        tiers = sorted({m.name for m in item.iter_markers() if m.name in TIERS})
        if len(tiers) != 1:
            found = ", ".join(tiers) if tiers else "none"
            problems.append(f"{item.nodeid}: expected exactly one tier, found {found}")
    if problems:
        raise pytest.UsageError(
            "Every test needs exactly one tier marker "
            f"({', '.join(TIERS)}):\n  " + "\n  ".join(problems)
        )
