from click.testing import CliRunner

from talaria import apk as talaria_apk
from talaria import hbc
from talaria.cli import main
from tests.test_hbc_core import HBC98_FIXTURE, string_id


def test_cli_version():
    result = CliRunner().invoke(main, ["--version"])

    assert result.exit_code == 0
    assert "talaria" in result.output


def test_cli_disasm_asm_round_trip(tmp_path):
    runner = CliRunner()
    tasm_path = tmp_path / "tasm"
    bundle_path = tmp_path / "index.android.bundle"

    disasm_result = runner.invoke(main, ["disasm", str(HBC98_FIXTURE), str(tasm_path), "--force"])
    assert disasm_result.exit_code == 0, disasm_result.output
    assert "talaria disasm" in disasm_result.output
    assert "wrote   talaria.json, bundle.json, strings.json, functions.tasm" in disasm_result.output
    assert (tasm_path / "talaria.json").exists()
    assert (tasm_path / "bundle.json").exists()
    assert (tasm_path / "strings.json").exists()
    assert (tasm_path / "functions.tasm").exists()

    asm_result = runner.invoke(main, ["asm", str(tasm_path), str(bundle_path)])
    assert asm_result.exit_code == 0, asm_result.output
    assert "talaria asm" in asm_result.output
    assert f"output  {bundle_path}" in asm_result.output
    assert bundle_path.read_bytes() == HBC98_FIXTURE.read_bytes()


def test_cli_apk_disasm_and_asm_updates_decoded_bundle(tmp_path, monkeypatch):
    fake_apk = tmp_path / "app.apk"
    fake_apk.write_bytes(b"apk")
    workspace = tmp_path / "workspace"

    def fake_apktool(args: list[str]) -> None:
        assert args[:2] == ["d", "-r"]
        assert args[2] == str(fake_apk)
        assert args[3] == "-o"
        decoded_apk = tmp_path / "workspace" / "apk"
        assert args[4] == str(decoded_apk)
        assets = decoded_apk / "assets"
        assets.mkdir(parents=True)
        (assets / "index.android.bundle").write_bytes(HBC98_FIXTURE.read_bytes())

    monkeypatch.setattr(talaria_apk, "run_apktool", fake_apktool)

    runner = CliRunner()
    disasm_result = runner.invoke(main, ["apk", "disasm", str(fake_apk), str(workspace)])

    assert disasm_result.exit_code == 0, disasm_result.output
    assert "talaria apk disasm" in disasm_result.output
    assert f"edit    {workspace / 'tasm' / 'functions.tasm'}" in disasm_result.output
    assert (workspace / "talaria-apk.json").exists()
    assert (workspace / "tasm" / "functions.tasm").exists()

    with HBC98_FIXTURE.open("rb") as f:
        hbco = hbc.load(f)
    alpha_id = string_id(hbco, "alpha")

    functions_path = workspace / "tasm" / "functions.tasm"
    functions_path.write_text(
        functions_path.read_text().replace(f's@{alpha_id} "alpha"', f's@{alpha_id} "omega"', 1)
    )

    asm_result = runner.invoke(main, ["apk", "asm", str(workspace)])

    assert asm_result.exit_code == 0, asm_result.output
    assert "talaria apk asm" in asm_result.output
    assert "talaria asm" not in asm_result.output
    assert f"updated {workspace / 'apk' / 'assets' / 'index.android.bundle'}" in asm_result.output
    with (workspace / "apk" / "assets" / "index.android.bundle").open("rb") as f:
        hbco = hbc.load(f)
    assert hbco.getString(alpha_id)[0] == "omega"
