from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.text import Text

from talaria import apk, hbc, tasm

CONSOLE = Console(highlight=False, markup=False, soft_wrap=True)


def _format_bundle(hbco) -> str:
    header = hbco.getHeader()
    source_hash = bytes(header["sourceHash"]).hex()
    return f"HBC v{header['version']} ({_format_counts(hbco)}), source {source_hash[:12]}"


def _format_counts(hbco) -> str:
    return f"{hbco.getFunctionCount():,} functions, {hbco.getStringCount():,} strings"


def _title(command: str) -> None:
    CONSOLE.print()
    CONSOLE.print(command, style="bold bright_blue")


def _field(label: str, value: object, *, value_style: str | None = None) -> None:
    line = Text("  ")
    line.append(f"{label:<9}", style="bright_black")
    if value_style is None:
        line.append(str(value))
    else:
        line.append(str(value), style=value_style)
    CONSOLE.print(line)


def _done(label: str, value: object) -> None:
    line = Text("  ")
    line.append(f"{label:<9}", style="bold green")
    line.append(str(value), style="bright_green")
    CONSOLE.print(line)


def _print_warnings(hbco) -> None:
    for warning in hbco.getObj().get("_validationWarnings", []):
        _field("warning", warning, value_style="yellow")


def disassemble(hbc_file: str, tasm_path: str, *, force: bool = False) -> None:
    input_path = Path(hbc_file)
    output_path = Path(tasm_path)

    _title("talaria disasm")
    _field("input", input_path, value_style="cyan")
    with input_path.open("rb") as f:
        hbco = hbc.load(f)

    _field("bundle", _format_bundle(hbco))
    _print_warnings(hbco)
    tasm.dump(hbco, str(output_path), force=force)
    _field("output", output_path, value_style="cyan")
    _done("wrote", "talaria.json, bundle.json, strings.json, functions.tasm")


def assemble(tasm_path: str, hbc_file: str, *, log: bool = True):
    input_path = Path(tasm_path)
    output_path = Path(hbc_file)

    if log:
        _title("talaria asm")
        _field("input", input_path, value_style="cyan")

    hbco = tasm.load(str(input_path))
    if log:
        _field("bundle", _format_bundle(hbco))
        _print_warnings(hbco)

    with output_path.open("w+b") as f:
        hbc.dump(hbco, f)
    if log:
        _done("output", output_path)

    return hbco


def disassemble_apk(
    apk_file: str,
    workspace_path: str,
    *,
    bundle_path: str = apk.DEFAULT_BUNDLE_PATH.as_posix(),
    force: bool = False,
) -> None:
    input_path = Path(apk_file)
    output_path = Path(workspace_path)

    _title("talaria apk disasm")
    _field("apk", input_path, value_style="cyan")
    _field("workdir", output_path, value_style="cyan")
    _field("decode", "apktool d -r")
    workspace = apk.create_workspace(
        input_path,
        output_path,
        bundle_path=bundle_path,
        force=force,
    )

    if not workspace.bundle.exists():
        raise FileNotFoundError(
            f"Hermes bundle not found at {workspace.bundle}; pass --bundle-path if needed"
        )

    with workspace.bundle.open("rb") as f:
        hbco = hbc.load(f)

    _field("bundle", workspace.bundle, value_style="cyan")
    _field("bytecode", _format_bundle(hbco))
    _print_warnings(hbco)
    tasm.dump(hbco, str(workspace.tasm), force=False)
    _field("tasm", workspace.tasm, value_style="cyan")
    _done("edit", workspace.tasm / tasm.FUNCTIONS_FILE)


def assemble_apk(workspace_path: str) -> None:
    input_path = Path(workspace_path)

    _title("talaria apk asm")
    _field("workdir", input_path, value_style="cyan")
    workspace = apk.load_workspace(input_path)

    if not workspace.decoded_apk.exists():
        raise FileNotFoundError(workspace.decoded_apk)
    if not workspace.tasm.exists():
        raise FileNotFoundError(workspace.tasm)

    hbco = assemble(str(workspace.tasm), str(workspace.bundle), log=False)
    _field("tasm", workspace.tasm, value_style="cyan")
    _field("bundle", _format_bundle(hbco))
    _print_warnings(hbco)
    _done("updated", workspace.bundle)
