from __future__ import annotations

import io
import pathlib
import re

import pytest

from talaria import hbc as hbcl
from talaria import tasm
from talaria.hbc import SUPPORTED_VERSIONS
from talaria.hbc.hbc96.translator import assemble, disassemble, opcode_mapper_inv
from talaria.models import FunctionBody, Instruction, Operand

ROOT = pathlib.Path(__file__).resolve().parents[1]
HBC98_FIXTURE = ROOT / "src" / "talaria" / "hbc" / "hbc98" / "example" / "index.android.bundle"


def test_supported_versions_match_ported_modules():
    assert SUPPORTED_VERSIONS == (59, 62, 74, 76, 84, 85, 90, 94, 96, 98)
    assert sorted(hbcl.HBC) == list(SUPPORTED_VERSIONS)


def test_imm32_is_signed():
    op = opcode_mapper_inv["LoadConstInt"]
    bytecode = [op, 0, 0xFF, 0xFF, 0xFF, 0xFF]
    instructions = disassemble(bytecode)

    assert instructions[0][1][1] == ("Imm32", False, -1)
    assert assemble(instructions) == bytecode


def test_truncated_instruction_is_preserved_as_raw():
    instructions = disassemble([42])

    assert instructions == [(".raw", [("UInt8", False, 42)])]
    assert assemble(instructions) == [42]


def test_invalid_string_reference_does_not_crash():
    class FakeHBC:
        def getHeader(self):
            return {"version": 98}

        def getStringCount(self):
            return 0

    out = io.StringIO()
    context = tasm.TasmContext.from_hbc(FakeHBC())
    func = FunctionBody(
        name="",
        param_count=0,
        register_count=0,
        symbol_count=0,
        instructions=(Instruction("DeclareGlobalVar", (Operand("UInt32", True, 999999),)),),
    )

    tasm.write_func(out, func, 0, context)

    assert out.getvalue().startswith('.function @0\n    .name ""')
    assert "DeclareGlobalVar s@999999" in out.getvalue()


def test_tasm_missing_function_block_preserves_original_function(tmp_path):
    with HBC98_FIXTURE.open("rb") as f:
        original = hbcl.load(f)

    tasm.dump(original, tmp_path, force=True)

    instruction_path = tmp_path / "functions.tasm"
    content = instruction_path.read_text()
    instruction_path.write_text(
        re.sub(
            r"\n\.function\s+@?[0-9]+.*?\n\.end function\n*$",
            "\n",
            content,
            count=1,
            flags=re.DOTALL,
        )
    )

    loaded = tasm.load(tmp_path)

    original_function = original.getFunction(original.getFunctionCount() - 1, disasm=False)
    loaded_function = loaded.getFunction(loaded.getFunctionCount() - 1, disasm=False)
    assert original_function == loaded_function


def test_tasm_allows_single_string_edit_for_repeated_string_id(tmp_path):
    with HBC98_FIXTURE.open("rb") as f:
        original = hbcl.load(f)

    tasm.dump(original, tmp_path, force=True)
    instruction_path = tmp_path / "functions.tasm"
    content = instruction_path.read_text()
    instruction_path.write_text(content.replace('s@8 "alpha"', 's@8 "omega"', 1))

    loaded = tasm.load(tmp_path)

    assert loaded.getString(8)[0] == "omega"


def test_tasm_rejects_conflicting_string_edits(tmp_path):
    with HBC98_FIXTURE.open("rb") as f:
        original = hbcl.load(f)

    tasm.dump(original, tmp_path, force=True)
    instruction_path = tmp_path / "functions.tasm"
    content = instruction_path.read_text()
    content = content.replace('s@8 "alpha"', 's@8 "omega"', 1)
    content = content.replace('s@8 "alpha"', 's@8 "bravo"', 1)
    instruction_path.write_text(content)

    with pytest.raises(ValueError, match="Conflicting edits for string 8"):
        tasm.load(tmp_path)


def test_tasm_resolves_unique_bare_string_literal(tmp_path):
    with HBC98_FIXTURE.open("rb") as f:
        original = hbcl.load(f)

    tasm.dump(original, tmp_path, force=True)
    instruction_path = tmp_path / "functions.tasm"
    content = instruction_path.read_text()
    instruction_path.write_text(content.replace('s@14 "now"', '"now"', 1))

    loaded = tasm.load(tmp_path)
    out_path = tmp_path / "out.bundle"
    with out_path.open("w+b") as f:
        hbcl.dump(loaded, f)

    assert out_path.read_bytes() == HBC98_FIXTURE.read_bytes()


def test_hbc98_direct_dump_round_trips_bytes(tmp_path):
    original_bytes = HBC98_FIXTURE.read_bytes()
    with HBC98_FIXTURE.open("rb") as f:
        hbco = hbcl.load(f)

    out_path = tmp_path / "index.android.bundle"
    with out_path.open("w+b") as f:
        hbcl.dump(hbco, f)

    assert out_path.read_bytes() == original_bytes
