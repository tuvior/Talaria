from __future__ import annotations

import subprocess
import sys


def test_hbc_spec_metadata_is_current():
    result = subprocess.run(
        [sys.executable, "tools/check_hbc_specs.py"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "HBC opcode metadata is up to date." in result.stdout
