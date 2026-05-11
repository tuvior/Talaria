from __future__ import annotations

import click

from talaria import __version__, apk, commands


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, prog_name="talaria")
def main() -> None:
    """Disassemble and assemble Hermes bytecode bundles."""


@main.command()
@click.argument("hbc_file", type=click.Path(exists=True, dir_okay=False, path_type=str))
@click.argument("tasm_path", type=click.Path(file_okay=False, path_type=str))
@click.option(
    "-f",
    "--force",
    is_flag=True,
    help="Replace the output TASM directory if it already exists.",
)
def disasm(hbc_file: str, tasm_path: str, force: bool) -> None:
    """Disassemble a Hermes bytecode bundle."""
    commands.disassemble(hbc_file, tasm_path, force=force)


@main.command()
@click.argument("tasm_path", type=click.Path(exists=True, file_okay=False, path_type=str))
@click.argument("hbc_file", type=click.Path(dir_okay=False, path_type=str))
def asm(tasm_path: str, hbc_file: str) -> None:
    """Assemble a TASM directory."""
    commands.assemble(tasm_path, hbc_file)


@main.group(name="apk")
def apk_cmd() -> None:
    """Work with APKs that contain Hermes bundles."""


@apk_cmd.command("disasm")
@click.argument("apk_file", type=click.Path(exists=True, dir_okay=False, path_type=str))
@click.argument("workspace_path", type=click.Path(file_okay=False, path_type=str))
@click.option(
    "--bundle-path",
    default=apk.DEFAULT_BUNDLE_PATH.as_posix(),
    show_default=True,
    help="Bundle path inside the decoded APK tree.",
)
@click.option(
    "-f",
    "--force",
    is_flag=True,
    help="Replace the output APK workspace if it already exists.",
)
def apk_disasm(apk_file: str, workspace_path: str, bundle_path: str, force: bool) -> None:
    """Decode an APK with apktool -r and disassemble its Hermes bundle."""
    commands.disassemble_apk(
        apk_file,
        workspace_path,
        bundle_path=bundle_path,
        force=force,
    )


@apk_cmd.command("asm")
@click.argument("workspace_path", type=click.Path(exists=True, file_okay=False, path_type=str))
def apk_asm(workspace_path: str) -> None:
    """Assemble TASM back into a decoded APK workspace bundle."""
    commands.assemble_apk(workspace_path)


if __name__ == "__main__":
    main()
