"""The tier hook in conftest.py: every test must declare exactly one tier."""

from pathlib import Path

import pytest

pytestmark = pytest.mark.always

CONFTEST = Path(__file__).with_name("conftest.py").read_text()


def _run(pytester, body):
    pytester.makeconftest(CONFTEST.replace('pytest_plugins = ["pytester"]', ""))
    pytester.makeini(
        "[pytest]\nmarkers =\n    always\n    sometimes\n    rarely\n    edge\n    debug\n"
    )
    pytester.makepyfile(body)
    return pytester.runpytest("-p", "no:randomly")


def test_tiered_test_runs(pytester):
    result = _run(pytester, "import pytest\n\n@pytest.mark.always\ndef test_ok():\n    pass\n")
    result.assert_outcomes(passed=1)


def test_untiered_test_fails_collection(pytester):
    result = _run(pytester, "def test_untiered():\n    pass\n")
    assert result.ret != 0
    result.stderr.fnmatch_lines(["*expected exactly one tier, found none*"])


def test_two_tiers_fail_collection(pytester):
    body = "import pytest\n\n@pytest.mark.always\n@pytest.mark.rarely\ndef test_both():\n    pass\n"
    result = _run(pytester, body)
    assert result.ret != 0
    result.stderr.fnmatch_lines(["*expected exactly one tier, found always, rarely*"])


def test_debug_tier_is_excluded_by_default(pytester):
    pytester.makeconftest(CONFTEST.replace('pytest_plugins = ["pytester"]', ""))
    pytester.makeini(
        "[pytest]\naddopts = -m 'not debug'\n"
        "markers =\n    always\n    sometimes\n    rarely\n    edge\n    debug\n"
    )
    pytester.makepyfile(
        "import pytest\n\n"
        "@pytest.mark.always\ndef test_fast():\n    pass\n\n"
        "@pytest.mark.debug\ndef test_diagnostic():\n    pass\n"
    )
    result = pytester.runpytest("-p", "no:randomly")
    result.assert_outcomes(passed=1, deselected=1)
    named = pytester.runpytest("-p", "no:randomly", "-m", "debug")
    named.assert_outcomes(passed=1, deselected=1)
