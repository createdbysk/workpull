"""Tests for the git hook wrappers in .githooks/.

The hooks are thin wrappers over scripts/dev.py: pre-commit
runs lint then type, pre-push runs test, and a failed check
stops the commit or the push. These tests build a fixture
tree in an isolated filesystem — the real hook scripts, a
stub scripts/dev.py that records the subcommands it was
called with and can be told to fail one of them, and a stub
venv python that runs the real interpreter — and invoke the
hooks through sh. One test drives the real wiring: a git
repository with core.hooksPath pointed at the fixture hooks.

The tests drive the hooks through a standalone POSIX sh,
which Windows does not provide; on Windows, git's bundled
sh runs the same scripts.
"""

import contextlib
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="hooks are driven through a standalone POSIX sh in these tests",
)

ROOT = Path(__file__).resolve().parents[1]
HOOKS = ROOT / ".githooks"
STUB_FAILURE_EXIT_CODE = 7

STUB_DEV_PY = f"""import sys
from pathlib import Path

with (Path.cwd() / "calls.txt").open("a", encoding="utf-8") as calls:
    calls.write(sys.argv[1] + "\\n")

failing = Path.cwd() / "failing.txt"
if failing.exists() and failing.read_text(encoding="utf-8") == sys.argv[1]:
    sys.exit({STUB_FAILURE_EXIT_CODE})
"""

VENV_PYTHON_SCRIPT = f"""#!/bin/sh
exec "{sys.executable}" "$@"
"""

UNSELECTED_VENV_PYTHON_EXIT_CODE = 3

UNSELECTED_VENV_PYTHON_SCRIPT = f"""#!/bin/sh
exit {UNSELECTED_VENV_PYTHON_EXIT_CODE}
"""

IsolatedFilesystem = Callable[[], contextlib.AbstractContextManager[str]]


class Outcome(NamedTuple):
    exit_code: int
    output: str
    error: str
    calls: str


class HookRun(NamedTuple):
    hook: str
    venv_layout: str
    failing_command: str
    invoke_from: str


class HookCase(NamedTuple):
    case_name: str
    run: HookRun
    expected: Outcome


def write_venv_python(root: Path, relative_path: str, script: str) -> None:
    python = root / ".venv" / relative_path
    python.parent.mkdir(parents=True)
    python.write_text(script, encoding="utf-8")
    python.chmod(0o755)


def build_fixture_tree(root: Path, venv_layout: str, failing_command: str) -> None:
    hooks_dir = root / ".githooks"
    hooks_dir.mkdir()
    for hook in ("pre-commit", "pre-push"):
        shutil.copy(HOOKS / hook, hooks_dir / hook)
    scripts_dir = root / "scripts"
    scripts_dir.mkdir()
    (scripts_dir / "dev.py").write_text(STUB_DEV_PY, encoding="utf-8")
    if failing_command:
        (root / "failing.txt").write_text(failing_command, encoding="utf-8")
    if venv_layout == "none":
        return
    if venv_layout == "unix":
        write_venv_python(root, "bin/python", VENV_PYTHON_SCRIPT)
    elif venv_layout == "windows":
        write_venv_python(root, "Scripts/python.exe", VENV_PYTHON_SCRIPT)
    elif venv_layout == "both":
        write_venv_python(root, "bin/python", UNSELECTED_VENV_PYTHON_SCRIPT)
        write_venv_python(root, "Scripts/python.exe", VENV_PYTHON_SCRIPT)


RunGitHook = Callable[[HookRun], Outcome]


@pytest.fixture
def run_git_hook(isolated_filesystem: IsolatedFilesystem) -> RunGitHook:
    def _run(run: HookRun) -> Outcome:
        with isolated_filesystem():
            root = Path.cwd()
            build_fixture_tree(root, run.venv_layout, run.failing_command)
            invoke_from = root / run.invoke_from if run.invoke_from else root
            invoke_from.mkdir(parents=True, exist_ok=True)
            result = subprocess.run(
                ["sh", str(root / ".githooks" / run.hook)],
                cwd=invoke_from,
                capture_output=True,
                text=True,
                timeout=30,
            )
            calls_file = root / "calls.txt"
            calls = (
                calls_file.read_text(encoding="utf-8") if calls_file.exists() else ""
            )
            return Outcome(
                exit_code=result.returncode,
                output=result.stdout,
                error=result.stderr,
                calls=calls,
            )

    return _run


def _hook_case_id(case: HookCase) -> str:
    return case.case_name


@pytest.mark.parametrize(
    "case",
    [
        HookCase(
            case_name="pre_commit_all_checks_pass",
            run=HookRun(
                hook="pre-commit",
                venv_layout="unix",
                failing_command="",
                invoke_from="",
            ),
            expected=Outcome(exit_code=0, output="", error="", calls="lint\ntype\n"),
        ),
        HookCase(
            case_name="pre_commit_lint_failure_stops_before_type",
            run=HookRun(
                hook="pre-commit",
                venv_layout="unix",
                failing_command="lint",
                invoke_from="",
            ),
            expected=Outcome(
                exit_code=STUB_FAILURE_EXIT_CODE,
                output="",
                error="",
                calls="lint\n",
            ),
        ),
        HookCase(
            case_name="pre_commit_type_failure_propagates",
            run=HookRun(
                hook="pre-commit",
                venv_layout="unix",
                failing_command="type",
                invoke_from="",
            ),
            expected=Outcome(
                exit_code=STUB_FAILURE_EXIT_CODE,
                output="",
                error="",
                calls="lint\ntype\n",
            ),
        ),
        HookCase(
            case_name="pre_commit_windows_venv_layout",
            run=HookRun(
                hook="pre-commit",
                venv_layout="windows",
                failing_command="",
                invoke_from="",
            ),
            expected=Outcome(exit_code=0, output="", error="", calls="lint\ntype\n"),
        ),
        HookCase(
            case_name="pre_commit_both_layouts_scripts_python_wins",
            run=HookRun(
                hook="pre-commit",
                venv_layout="both",
                failing_command="",
                invoke_from="",
            ),
            expected=Outcome(exit_code=0, output="", error="", calls="lint\ntype\n"),
        ),
        HookCase(
            case_name="pre_commit_missing_venv_names_setup_step",
            run=HookRun(
                hook="pre-commit",
                venv_layout="none",
                failing_command="",
                invoke_from="",
            ),
            expected=Outcome(
                exit_code=1,
                output="",
                error="error: .venv not found. Run: python scripts/dev.py setup\n",
                calls="",
            ),
        ),
        HookCase(
            case_name="pre_commit_invoked_from_subdirectory",
            run=HookRun(
                hook="pre-commit",
                venv_layout="unix",
                failing_command="",
                invoke_from="docs",
            ),
            expected=Outcome(exit_code=0, output="", error="", calls="lint\ntype\n"),
        ),
        HookCase(
            case_name="pre_push_all_checks_pass",
            run=HookRun(
                hook="pre-push",
                venv_layout="unix",
                failing_command="",
                invoke_from="",
            ),
            expected=Outcome(exit_code=0, output="", error="", calls="test\n"),
        ),
        HookCase(
            case_name="pre_push_test_failure_propagates",
            run=HookRun(
                hook="pre-push",
                venv_layout="unix",
                failing_command="test",
                invoke_from="",
            ),
            expected=Outcome(
                exit_code=STUB_FAILURE_EXIT_CODE,
                output="",
                error="",
                calls="test\n",
            ),
        ),
        HookCase(
            case_name="pre_push_windows_venv_layout",
            run=HookRun(
                hook="pre-push",
                venv_layout="windows",
                failing_command="",
                invoke_from="",
            ),
            expected=Outcome(exit_code=0, output="", error="", calls="test\n"),
        ),
        HookCase(
            case_name="pre_push_both_layouts_scripts_python_wins",
            run=HookRun(
                hook="pre-push",
                venv_layout="both",
                failing_command="",
                invoke_from="",
            ),
            expected=Outcome(exit_code=0, output="", error="", calls="test\n"),
        ),
        HookCase(
            case_name="pre_push_missing_venv_names_setup_step",
            run=HookRun(
                hook="pre-push",
                venv_layout="none",
                failing_command="",
                invoke_from="",
            ),
            expected=Outcome(
                exit_code=1,
                output="",
                error="error: .venv not found. Run: python scripts/dev.py setup\n",
                calls="",
            ),
        ),
        HookCase(
            case_name="pre_push_invoked_from_subdirectory",
            run=HookRun(
                hook="pre-push",
                venv_layout="unix",
                failing_command="",
                invoke_from="docs",
            ),
            expected=Outcome(exit_code=0, output="", error="", calls="test\n"),
        ),
    ],
    ids=_hook_case_id,
)
def test_git_hook(run_git_hook: RunGitHook, case: HookCase) -> None:
    # GIVEN
    expected = case.expected
    # WHEN
    actual = run_git_hook(case.run)
    # THEN
    assert expected == actual


class GitOutcome(NamedTuple):
    first_commit_exit_code: int
    blocked_commit_exit_code: int
    log_output: str
    calls: str


def run_git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_git_commit_blocked_by_failing_check_and_allowed_by_passing_one(
    isolated_filesystem: IsolatedFilesystem,
) -> None:
    # GIVEN
    expected = GitOutcome(
        first_commit_exit_code=0,
        blocked_commit_exit_code=1,
        log_output="first\n",
        calls="lint\ntype\nlint\n",
    )
    # WHEN
    with isolated_filesystem():
        root = Path.cwd()
        build_fixture_tree(root, "unix", "")
        for hook in ("pre-commit", "pre-push"):
            (root / ".githooks" / hook).chmod(0o755)
        run_git(root, "init", "-q", "-b", "main")
        run_git(root, "config", "user.email", "test@example.com")
        run_git(root, "config", "user.name", "Test")
        run_git(root, "config", "core.hooksPath", ".githooks")
        tracked = root / "tracked.txt"
        tracked.write_text("one\n", encoding="utf-8")
        run_git(root, "add", "tracked.txt")
        first = run_git(root, "commit", "-q", "-m", "first")
        (root / "failing.txt").write_text("lint", encoding="utf-8")
        tracked.write_text("two\n", encoding="utf-8")
        run_git(root, "add", "tracked.txt")
        blocked = run_git(root, "commit", "-q", "-m", "second")
        log = run_git(root, "log", "--format=%s")
        actual = GitOutcome(
            first_commit_exit_code=first.returncode,
            blocked_commit_exit_code=blocked.returncode,
            log_output=log.stdout,
            calls=(root / "calls.txt").read_text(encoding="utf-8"),
        )
    # THEN
    assert expected == actual
