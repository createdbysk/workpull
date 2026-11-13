"""Tests for the lint command, scripts/dev.py lint.

Lint runs pymarkdown on the docs and Ruff on the Python
sources. These tests drive lint as a subprocess from the
repo root. A violation case writes its source to a probe
file in tests/, one of the directories lint checks, runs
lint, and asserts the exact outcome: the exit code and the
full printed output. The probe is removed after each run.
"""

import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

import pytest

ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "tests" / "lint_probe.py"
PROBE_DISPLAY_PATH = str(Path("tests") / "lint_probe.py")


class Outcome(NamedTuple):
    exit_code: int
    output: str


def run_dev_lint() -> Outcome:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "dev.py"), "lint"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return Outcome(exit_code=result.returncode, output=result.stdout)


RunLintWithProbe = Callable[[str], Outcome]


@pytest.fixture
def run_lint_with_probe() -> RunLintWithProbe:
    def _run(probe_source: str) -> Outcome:
        PROBE.write_text(probe_source, encoding="utf-8")
        try:
            return run_dev_lint()
        finally:
            PROBE.unlink()

    return _run


def test_lint_clean_tree_passes() -> None:
    # GIVEN
    expected = Outcome(exit_code=0, output="All checks passed!\n")
    # WHEN
    actual = run_dev_lint()
    # THEN
    assert expected == actual


class LintCase(NamedTuple):
    case_name: str
    probe_source: str
    expected_output: str


def _lint_case_id(case: LintCase) -> str:
    return case.case_name


@pytest.mark.parametrize(
    "case",
    [
        LintCase(
            case_name="one_blank_line_before_top_level_def",
            probe_source="""import os

def first() -> None:
    print(os.name)
""",
            expected_output=(
                f"{PROBE_DISPLAY_PATH}:3:1: blank-lines-top-level: "
                "[*] Expected 2 blank lines, found 1\n"
                "Found 1 error.\n"
                "[*] 1 fixable with `--fix`.\n"
            ),
        ),
        LintCase(
            case_name="three_blank_lines_before_top_level_def",
            probe_source="""import os



def first() -> None:
    print(os.name)
""",
            expected_output=(
                f"{PROBE_DISPLAY_PATH}:5:1: too-many-blank-lines: "
                "[*] Too many blank lines (3)\n"
                "Found 1 error.\n"
                "[*] 1 fixable with `--fix`.\n"
            ),
        ),
        LintCase(
            case_name="blank_run_inside_function_body",
            probe_source="""import os


def first() -> None:
    print(os.name)



    print("again")
""",
            expected_output=(
                f"{PROBE_DISPLAY_PATH}:9:5: too-many-blank-lines: "
                "[*] Too many blank lines (3)\n"
                "Found 1 error.\n"
                "[*] 1 fixable with `--fix`.\n"
            ),
        ),
        LintCase(
            case_name="file_ends_with_extra_blank_lines",
            probe_source=(
                "import os\n"
                "\n"
                "\n"
                "def first() -> None:\n"
                "    print(os.name)\n"
                "\n"
            ),
            expected_output=(
                f"{PROBE_DISPLAY_PATH}:6:1: "
                "too-many-newlines-at-end-of-file: "
                "[*] Extra newline at end of file\n"
                "Found 1 error.\n"
                "[*] 1 fixable with `--fix`.\n"
            ),
        ),
        LintCase(
            case_name="file_ends_without_newline",
            probe_source=(
                "import os\n"
                "\n"
                "\n"
                "def first() -> None:\n"
                "    print(os.name)"
            ),
            expected_output=(
                f"{PROBE_DISPLAY_PATH}:5:19: "
                "missing-newline-at-end-of-file: "
                "[*] No newline at end of file\n"
                "Found 1 error.\n"
                "[*] 1 fixable with `--fix`.\n"
            ),
        ),
    ],
    ids=_lint_case_id,
)
def test_lint_catches_spacing_violation(
    run_lint_with_probe: RunLintWithProbe, case: LintCase
) -> None:
    # GIVEN
    expected = Outcome(exit_code=1, output=case.expected_output)
    # WHEN
    actual = run_lint_with_probe(case.probe_source)
    # THEN
    assert expected == actual


STRING_CONTENT_SOURCE = '''SCRIPT = """def inner() -> None:
    print("one")



    print("two")
"""


def first() -> None:
    print(SCRIPT)
'''


def test_lint_ignores_blank_lines_inside_string_literal(
    run_lint_with_probe: RunLintWithProbe,
) -> None:
    # GIVEN
    expected = Outcome(exit_code=0, output="All checks passed!\n")
    # WHEN
    actual = run_lint_with_probe(STRING_CONTENT_SOURCE)
    # THEN
    assert expected == actual
