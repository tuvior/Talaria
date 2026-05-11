#!/usr/bin/env python3
import json
import pathlib
import sys

from generate_opcodes import generate

ROOT = pathlib.Path(__file__).resolve().parents[1]


def main():
    failures = []
    for hbc_dir in sorted((ROOT / "src" / "talaria" / "hbc").glob("hbc[0-9]*")):
        raw = hbc_dir / "raw" / "BytecodeList.def"
        opcode_json = hbc_dir / "data" / "opcode.json"
        if not raw.exists() or not opcode_json.exists():
            continue

        generated = generate(raw)
        committed = json.loads(opcode_json.read_text())
        if generated != committed:
            failures.append(str(hbc_dir.relative_to(ROOT)))

    if failures:
        print("Stale opcode metadata:")
        for failure in failures:
            print(f"  {failure}")
        return 1

    specs_path = ROOT / "src" / "talaria" / "hbc" / "specs.json"
    specs = json.loads(specs_path.read_text()) if specs_path.exists() else {}
    for version in specs:
        hbc_dir = ROOT / "src" / "talaria" / "hbc" / f"hbc{version}"
        if not hbc_dir.exists():
            print(f"Spec registry references missing hbc{version}")
            return 1

    print("HBC opcode metadata is up to date.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
