import subprocess

import pytest

from talaria import apk as talaria_apk


def test_run_apktool_suppresses_success_output(monkeypatch, capsys):
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, stdout="apktool noise\n")

    monkeypatch.setattr(talaria_apk.shutil, "which", lambda name: f"/bin/{name}")
    monkeypatch.setattr(talaria_apk.subprocess, "run", fake_run)

    talaria_apk.run_apktool(["d", "app.apk"])

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
    assert calls == [
        (
            ["/bin/apktool", "d", "app.apk"],
            {
                "stdout": subprocess.PIPE,
                "stderr": subprocess.STDOUT,
                "text": True,
                "errors": "replace",
            },
        )
    ]


def test_run_apktool_replays_output_on_failure(monkeypatch, capsys):
    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(command, 1, stdout="apktool failed")

    monkeypatch.setattr(talaria_apk.shutil, "which", lambda name: f"/bin/{name}")
    monkeypatch.setattr(talaria_apk.subprocess, "run", fake_run)

    with pytest.raises(subprocess.CalledProcessError) as exc_info:
        talaria_apk.run_apktool(["d", "app.apk"])

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "apktool failed\n"
    assert exc_info.value.returncode == 1
    assert exc_info.value.cmd == ["/bin/apktool", "d", "app.apk"]
