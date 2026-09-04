import os
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.fixture
def entrypoint_runner(tmp_path):
    shell = shutil.which("sh")
    if shell is None and os.name == "nt":
        git_shell = Path("C:/Program Files/Git/bin/bash.exe")
        shell = str(git_shell) if git_shell.exists() else None
    if shell is None:
        pytest.skip("A POSIX shell is required for entrypoint tests")
    entrypoint = tmp_path / "entrypoint.sh"
    entrypoint.write_bytes(
        (Path(__file__).parents[1] / "deploy/docker-entrypoint.sh").read_bytes()
    )
    entrypoint.chmod(0o755)
    commands = tmp_path / "commands"
    commands.mkdir()
    log = tmp_path / "calls"
    scripts = {
        "id": 'printf "%s\n" "$TEST_UID"',
        "mkdir": 'printf "mkdir:%s\n" "$*" >> "$TEST_LOG"',
        "chown": 'printf "chown:%s\n" "$*" >> "$TEST_LOG"; exit "$TEST_CHOWN_EXIT"',
        "chmod": 'printf "chmod:%s\n" "$*" >> "$TEST_LOG"',
        "gosu": (
            'printf "gosu:%s\n" "$1" >> "$TEST_LOG"; '
            '[ "$TEST_GOSU_EXIT" = 0 ] || exit "$TEST_GOSU_EXIT"; '
            '[ "$1" = slipstream ] || exit 99; '
            'shift; export TEST_UID=10001; exec "$@"'
        ),
        "python": (
            'printf "python-uid:%s\n" "$TEST_UID" >> "$TEST_LOG"; '
            'printf "arg:%s\n" "$@" >> "$TEST_LOG"'
        ),
    }
    for name, body in scripts.items():
        command = commands / name
        command.write_text("#!/bin/sh\n" + body + "\n", encoding="utf-8", newline="\n")
        command.chmod(0o755)

    def shell_path(path):
        value = path.as_posix()
        if os.name == "nt":
            return "/" + value[0].lower() + value[2:]
        return value

    def run(*args, uid="0", chown_exit="0", gosu_exit="0"):
        env = dict(os.environ)
        env.update(
            TEST_UID=uid,
            TEST_CHOWN_EXIT=chown_exit,
            TEST_GOSU_EXIT=gosu_exit,
            TEST_BIN=shell_path(commands),
            TEST_LOG=shell_path(log),
            TEST_ENTRYPOINT=shell_path(entrypoint),
        )
        result = subprocess.run(
            [
                shell, "-c",
                'PATH="$TEST_BIN:/usr/bin:/bin" exec /bin/sh "$TEST_ENTRYPOINT" "$@"',
                "entrypoint-test", *args,
            ],
            env=env, capture_output=True, text=True, check=False,
        )
        calls = log.read_text().splitlines() if log.exists() else []
        return result, calls

    return run


@pytest.mark.parametrize("uid", ["0", "10001"])
def test_entrypoint_drops_privileges_and_preserves_cli_arguments(entrypoint_runner, uid):
    args = ("serve", "/data", "--web-dir", "/app/web with spaces", "--port", "3344")
    result, calls = entrypoint_runner(*args, uid=uid)
    assert result.returncode == 0, result.stderr
    expected = []
    if uid == "0":
        expected = [
            "mkdir:-p /data",
            "chown:slipstream:slipstream /data",
            "chmod:u+rwx /data",
            "gosu:slipstream",
        ]
    assert calls == expected + [
        "python-uid:10001", "arg:-m", "arg:slipstream",
        *(f"arg:{arg}" for arg in args),
    ]


@pytest.mark.parametrize("failure", ["chown_exit", "gosu_exit"])
def test_entrypoint_never_launches_python_after_bootstrap_failure(entrypoint_runner, failure):
    result, calls = entrypoint_runner("--help", **{failure: "1"})
    assert result.returncode != 0
    assert not any(call.startswith("python-uid:") for call in calls)


def test_entrypoint_rejects_an_unexpected_runtime_user(entrypoint_runner):
    result, calls = entrypoint_runner("--help", uid="99")
    assert result.returncode != 0
    assert "UID 10001" in result.stderr
    assert calls == []
