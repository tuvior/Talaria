#!/usr/bin/env python3
import argparse
import json
import pathlib
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW_FILES = {
    "include/hermes/BCGen/HBC/BytecodeFileFormat.h": "BytecodeFileFormat.h",
    "include/hermes/BCGen/HBC/BytecodeList.def": "BytecodeList.def",
    "include/hermes/BCGen/SerializedLiteralGenerator.h": "SerializedLiteralGenerator.h",
}


def fetch(version):
    specs = json.loads((ROOT / "src" / "talaria" / "hbc" / "specs.json").read_text())
    spec = specs[str(version)]
    tag = spec["tag"]
    url = f"https://github.com/facebook/hermes/tarball/{tag}"
    target = ROOT / "src" / "talaria" / "hbc" / f"hbc{version}" / "raw"
    target.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = pathlib.Path(tmp)
        archive = tmp_path / "hermes.tar.gz"
        urllib.request.urlretrieve(url, archive)
        with tarfile.open(archive) as tar:
            tar.extractall(tmp_path)
        source_root = next(p for p in tmp_path.iterdir() if p.is_dir())
        for source, dest in RAW_FILES.items():
            shutil.copyfile(source_root / source, target / dest)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("version", type=int)
    args = parser.parse_args()
    fetch(args.version)
    hbc_dir = ROOT / "src" / "talaria" / "hbc" / f"hbc{args.version}"
    subprocess.check_call(
        [
            sys.executable,
            str(ROOT / "tools" / "generate_opcodes.py"),
            str(hbc_dir / "raw" / "BytecodeList.def"),
            "-o",
            str(hbc_dir / "data" / "opcode.json"),
        ]
    )


if __name__ == "__main__":
    main()
