from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

APK_MANIFEST_FILE = "talaria-apk.json"
APK_WORKSPACE_FORMAT = "talaria.apk-workspace"
APK_WORKSPACE_VERSION = 1
DECODED_APK_DIR = "apk"
TASM_DIR = "tasm"
DEFAULT_BUNDLE_PATH = Path("assets/index.android.bundle")


@dataclass(frozen=True, slots=True)
class ApkWorkspace:
    root: Path
    decoded_apk: Path
    tasm: Path
    bundle_path: Path

    @property
    def bundle(self) -> Path:
        return self.decoded_apk / self.bundle_path


def create_workspace(
    apk_file: str | Path,
    workspace_path: str | Path,
    *,
    bundle_path: str | Path = DEFAULT_BUNDLE_PATH,
    force: bool = False,
) -> ApkWorkspace:
    apk_path = Path(apk_file)
    workspace = Path(workspace_path)

    if workspace.exists():
        if not force:
            raise FileExistsError(f"{workspace} already exists; pass force=True to replace it")
        shutil.rmtree(workspace)

    workspace.mkdir(parents=True)
    decoded_apk = workspace / DECODED_APK_DIR
    run_apktool(["d", "-r", str(apk_path), "-o", str(decoded_apk)])

    apk_workspace = ApkWorkspace(
        root=workspace,
        decoded_apk=decoded_apk,
        tasm=workspace / TASM_DIR,
        bundle_path=Path(bundle_path),
    )
    write_manifest(apk_workspace, apk_path)
    return apk_workspace


def load_workspace(workspace_path: str | Path) -> ApkWorkspace:
    workspace = Path(workspace_path)
    manifest_path = workspace / APK_MANIFEST_FILE
    if not manifest_path.exists():
        raise FileNotFoundError(manifest_path)

    manifest = json.loads(manifest_path.read_text())
    if manifest.get("format") != APK_WORKSPACE_FORMAT:
        raise ValueError(f"Unsupported Talaria APK workspace format: {manifest.get('format')}")
    if manifest.get("formatVersion") != APK_WORKSPACE_VERSION:
        raise ValueError(
            f"Unsupported Talaria APK workspace version: {manifest.get('formatVersion')}"
        )

    return ApkWorkspace(
        root=workspace,
        decoded_apk=workspace / manifest["decodedApk"],
        tasm=workspace / manifest["tasm"],
        bundle_path=Path(manifest["bundlePath"]),
    )


def write_manifest(workspace: ApkWorkspace, original_apk: Path) -> None:
    manifest = {
        "format": APK_WORKSPACE_FORMAT,
        "formatVersion": APK_WORKSPACE_VERSION,
        "originalApk": str(original_apk),
        "decodedApk": workspace.decoded_apk.relative_to(workspace.root).as_posix(),
        "tasm": workspace.tasm.relative_to(workspace.root).as_posix(),
        "bundlePath": workspace.bundle_path.as_posix(),
    }
    (workspace.root / APK_MANIFEST_FILE).write_text(json.dumps(manifest, indent=2))


def run_apktool(args: list[str]) -> None:
    apktool = shutil.which("apktool")
    if apktool is None:
        raise FileNotFoundError("apktool is not installed or is not on PATH")
    command = [apktool, *args]
    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",
    )
    if result.returncode != 0:
        if result.stdout:
            sys.stderr.write(result.stdout)
            if not result.stdout.endswith("\n"):
                sys.stderr.write("\n")
        raise subprocess.CalledProcessError(result.returncode, command, output=result.stdout)
