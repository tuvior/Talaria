from __future__ import annotations

import io
import json
import pathlib
import re

import pytest

from talaria import hbc as hbcl
from talaria import tasm
from talaria.hbc import SUPPORTED_VERSIONS
from talaria.hbc.hbc96.translator import assemble, disassemble, opcode_mapper_inv
from talaria.models import FunctionBody, Instruction, Operand
from talaria.util import BitReader, BitWriter, read, write

ROOT = pathlib.Path(__file__).resolve().parents[1]
HBC_ROOT = ROOT / "src" / "talaria" / "hbc"
HBC98_FIXTURE = HBC_ROOT / "hbc98" / "example" / "index.android.bundle"
HBC_FIXTURES = {
    version: HBC_ROOT / f"hbc{version}" / "example" / "index.android.bundle"
    for version in SUPPORTED_VERSIONS
}


def test_supported_versions_match_ported_modules():
    assert SUPPORTED_VERSIONS == (59, 62, 74, 76, 84, 85, 90, 94, 96, 98)
    assert sorted(hbcl.HBC) == list(SUPPORTED_VERSIONS)


def test_supported_versions_have_specs_and_fixtures():
    specs = json.loads((HBC_ROOT / "specs.json").read_text())

    assert sorted(int(version) for version in specs) == list(SUPPORTED_VERSIONS)
    for version, fixture in HBC_FIXTURES.items():
        assert fixture.exists(), f"hbc{version} is missing an index.android.bundle fixture"
        assert specs[str(version)]["bytecode_version"] == version
        assert specs[str(version)]["tag"]


@pytest.mark.parametrize("version,fixture", HBC_FIXTURES.items())
def test_hbc_fixture_direct_dump_round_trips_bytes(version, fixture, tmp_path):
    original_bytes = fixture.read_bytes()
    with fixture.open("rb") as f:
        hbco = hbcl.load(f)

    assert hbco.getHeader()["version"] == version

    out_path = tmp_path / "index.android.bundle"
    with out_path.open("w+b") as f:
        hbcl.dump(hbco, f)

    assert out_path.read_bytes() == original_bytes


@pytest.mark.parametrize("version,fixture", HBC_FIXTURES.items())
def test_hbc_fixture_tasm_round_trips_bytes(version, fixture, tmp_path):
    original_bytes = fixture.read_bytes()
    with fixture.open("rb") as f:
        hbco = hbcl.load(f)

    assert hbco.getHeader()["version"] == version

    tasm_path = tmp_path / "tasm"
    tasm.dump(hbco, tasm_path, force=True)
    loaded = tasm.load(tasm_path)

    out_path = tmp_path / "index.android.bundle"
    with out_path.open("w+b") as f:
        hbcl.dump(loaded, f)

    assert out_path.read_bytes() == original_bytes


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


def test_bitfields_write_little_endian_across_byte_boundaries():
    out = io.BytesIO()
    writer = BitWriter(out)

    write(writer, 749, ["bit", 25, 1])
    write(writer, 1, ["bit", 5, 1])
    write(writer, 0, ["bit", 2, 1])
    writer.flush()

    encoded = out.getvalue()
    assert encoded == bytes.fromhex("ed 02 00 02")

    reader = BitReader(io.BytesIO(encoded))
    assert read(reader, ["bit", 25, 1]) == 749
    assert read(reader, ["bit", 5, 1]) == 1
    assert read(reader, ["bit", 2, 1]) == 0


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


def test_tasm_groups_related_instructions_without_extra_gaps():
    class FakeHBC:
        def getHeader(self):
            return {"version": 98}

        def getStringCount(self):
            return 2

        def getString(self, index):
            return (["first", "second"][index], (False, 0, 0))

    out = io.StringIO()
    context = tasm.TasmContext.from_hbc(FakeHBC())
    func = FunctionBody(
        name="",
        param_count=0,
        register_count=5,
        symbol_count=0,
        instructions=(
            Instruction("DeclareGlobalVar", (Operand("UInt32", True, 0),)),
            Instruction("DeclareGlobalVar", (Operand("UInt32", True, 1),)),
            Instruction(
                "CreateClosure",
                (
                    Operand("Reg8", False, 1),
                    Operand("Reg8", False, 2),
                    Operand("UInt16", False, 3),
                ),
            ),
            Instruction(
                "LoadConstUInt8",
                (
                    Operand("Reg8", False, 4),
                    Operand("UInt8", False, 1),
                ),
            ),
            Instruction(
                "Call2",
                (
                    Operand("Reg8", False, 0),
                    Operand("Reg8", False, 1),
                    Operand("Reg8", False, 2),
                    Operand("Reg8", False, 4),
                ),
            ),
            Instruction("Jmp", (Operand("Addr8", False, 2),)),
            Instruction("Ret", (Operand("Reg8", False, 0),)),
            Instruction(
                "CreateClosure",
                (
                    Operand("Reg8", False, 2),
                    Operand("Reg8", False, 1),
                    Operand("UInt16", False, 3),
                ),
            ),
            Instruction(
                "PutByIdLoose",
                (
                    Operand("Reg8", False, 0),
                    Operand("Reg8", False, 2),
                    Operand("UInt8", False, 1),
                    Operand("UInt16", True, 0),
                ),
            ),
            Instruction(
                "StoreToEnvironment",
                (
                    Operand("Reg8", False, 1),
                    Operand("UInt8", False, 3),
                    Operand("Reg8", False, 2),
                ),
            ),
            Instruction(
                "CreateClosure",
                (
                    Operand("Reg8", False, 2),
                    Operand("Reg8", False, 1),
                    Operand("UInt16", False, 4),
                ),
            ),
            Instruction(
                "PutByIdLoose",
                (
                    Operand("Reg8", False, 0),
                    Operand("Reg8", False, 2),
                    Operand("UInt8", False, 2),
                    Operand("UInt16", True, 1),
                ),
            ),
            Instruction(
                "LoadConstUInt8",
                (
                    Operand("Reg8", False, 3),
                    Operand("UInt8", False, 4),
                ),
            ),
            Instruction(
                "GetByVal",
                (
                    Operand("Reg8", False, 3),
                    Operand("Reg8", False, 4),
                    Operand("Reg8", False, 3),
                ),
            ),
        ),
    )

    tasm.write_func(out, func, 0, context)

    assert (
        '    DeclareGlobalVar s@0 "first"\n'
        '    DeclareGlobalVar s@1 "second"\n\n'
        "    CreateClosure r1, r2, fn@3\n"
        "    LoadConstUInt8 r4, 1\n"
        "    Call2 r0, r1, r2, r4\n"
        "    Jmp :L0019\n\n"
        ":L0019\n"
        "    Ret r0\n\n"
        "    CreateClosure r2, r1, fn@3\n"
        '    PutByIdLoose r0, r2, cache:1, s@0 "first"\n'
        "    StoreToEnvironment r1, slot:3, r2\n"
        "    CreateClosure r2, r1, fn@4\n"
        '    PutByIdLoose r0, r2, cache:2, s@1 "second"\n\n'
        "    LoadConstUInt8 r3, 4\n"
        "    GetByVal r3, r4, r3\n"
    ) in out.getvalue()


def test_tasm_keeps_selector_construction_together():
    class FakeHBC:
        def getHeader(self):
            return {"version": 96}

        def getStringCount(self):
            return 4

        def getString(self, index):
            return (
                [
                    "createSelector",
                    "isSubscribed",
                    "hasBusinessWeekEntitlement",
                    "nextDependency",
                ][index],
                (False, 0, 0),
            )

    out = io.StringIO()
    context = tasm.TasmContext.from_hbc(FakeHBC())
    func = FunctionBody(
        name="",
        param_count=0,
        register_count=12,
        symbol_count=0,
        instructions=(
            Instruction(
                "CreateClosure",
                (
                    Operand("Reg8", False, 4),
                    Operand("Reg8", False, 1),
                    Operand("UInt16", False, 23573),
                ),
            ),
            Instruction(
                "PutById",
                (
                    Operand("Reg8", False, 2),
                    Operand("Reg8", False, 4),
                    Operand("UInt8", False, 76),
                    Operand("UInt16", True, 2),
                ),
            ),
            Instruction(
                "LoadConstUInt8",
                (
                    Operand("Reg8", False, 4),
                    Operand("UInt8", False, 6),
                ),
            ),
            Instruction(
                "GetByVal",
                (
                    Operand("Reg8", False, 10),
                    Operand("Reg8", False, 7),
                    Operand("Reg8", False, 4),
                ),
            ),
            Instruction(
                "Call2",
                (
                    Operand("Reg8", False, 10),
                    Operand("Reg8", False, 6),
                    Operand("Reg8", False, 0),
                    Operand("Reg8", False, 10),
                ),
            ),
            Instruction(
                "GetById",
                (
                    Operand("Reg8", False, 11),
                    Operand("Reg8", False, 10),
                    Operand("UInt8", False, 3),
                    Operand("UInt16", True, 0),
                ),
            ),
            Instruction(
                "NewArray",
                (
                    Operand("Reg8", False, 10),
                    Operand("UInt16", False, 2),
                ),
            ),
            Instruction(
                "PutOwnByIndex",
                (
                    Operand("Reg8", False, 10),
                    Operand("Reg8", False, 3),
                    Operand("UInt8", False, 0),
                ),
            ),
            Instruction(
                "PutOwnByIndex",
                (
                    Operand("Reg8", False, 10),
                    Operand("Reg8", False, 5),
                    Operand("UInt8", False, 1),
                ),
            ),
            Instruction(
                "CreateClosure",
                (
                    Operand("Reg8", False, 5),
                    Operand("Reg8", False, 1),
                    Operand("UInt16", False, 23574),
                ),
            ),
            Instruction(
                "Call3",
                (
                    Operand("Reg8", False, 5),
                    Operand("Reg8", False, 11),
                    Operand("Reg8", False, 0),
                    Operand("Reg8", False, 10),
                    Operand("Reg8", False, 5),
                ),
            ),
            Instruction(
                "PutById",
                (
                    Operand("Reg8", False, 2),
                    Operand("Reg8", False, 5),
                    Operand("UInt8", False, 85),
                    Operand("UInt16", True, 1),
                ),
            ),
            Instruction(
                "StoreToEnvironment",
                (
                    Operand("Reg8", False, 1),
                    Operand("UInt8", False, 22),
                    Operand("Reg8", False, 5),
                ),
            ),
            Instruction(
                "GetByVal",
                (
                    Operand("Reg8", False, 10),
                    Operand("Reg8", False, 7),
                    Operand("Reg8", False, 4),
                ),
            ),
        ),
    )

    tasm.write_func(out, func, 0, context)

    assert (
        "    CreateClosure r4, r1, fn@23573\n"
        '    PutById r2, r4, cache:76, s@2 "hasBusinessWeekEntitlement"\n\n'
        "    LoadConstUInt8 r4, 6\n"
        "    GetByVal r10, r7, r4\n"
        "    Call2 r10, r6, r0, r10\n"
        '    GetById r11, r10, cache:3, s@0 "createSelector"\n'
        "    NewArray r10, 2\n"
        "    PutOwnByIndex r10, r3, 0\n"
        "    PutOwnByIndex r10, r5, 1\n"
        "    CreateClosure r5, r1, fn@23574\n"
        "    Call3 r5, r11, r0, r10, r5\n"
        '    PutById r2, r5, cache:85, s@1 "isSubscribed"\n'
        "    StoreToEnvironment r1, slot:22, r5\n\n"
        "    GetByVal r10, r7, r4\n"
    ) in out.getvalue()


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

    alpha_id = string_id(original, "alpha")
    tasm.dump(original, tmp_path, force=True)
    instruction_path = tmp_path / "functions.tasm"
    content = instruction_path.read_text()
    instruction_path.write_text(
        content.replace(f's@{alpha_id} "alpha"', f's@{alpha_id} "omega"', 1)
    )

    loaded = tasm.load(tmp_path)

    assert loaded.getString(alpha_id)[0] == "omega"


def test_tasm_rejects_conflicting_string_edits(tmp_path):
    with HBC98_FIXTURE.open("rb") as f:
        original = hbcl.load(f)

    alpha_id = string_id(original, "alpha")
    tasm.dump(original, tmp_path, force=True)
    instruction_path = tmp_path / "functions.tasm"
    content = instruction_path.read_text()
    content = content.replace(f's@{alpha_id} "alpha"', f's@{alpha_id} "omega"', 1)
    content = content.replace(f's@{alpha_id} "alpha"', f's@{alpha_id} "bravo"', 1)
    instruction_path.write_text(content)

    with pytest.raises(ValueError, match=f"Conflicting edits for string {alpha_id}"):
        tasm.load(tmp_path)


def test_tasm_resolves_unique_bare_string_literal(tmp_path):
    with HBC98_FIXTURE.open("rb") as f:
        original = hbcl.load(f)

    now_id = string_id(original, "now")
    tasm.dump(original, tmp_path, force=True)
    instruction_path = tmp_path / "functions.tasm"
    content = instruction_path.read_text()
    instruction_path.write_text(content.replace(f's@{now_id} "now"', '"now"', 1))

    loaded = tasm.load(tmp_path)
    out_path = tmp_path / "out.bundle"
    with out_path.open("w+b") as f:
        hbcl.dump(loaded, f)

    assert out_path.read_bytes() == HBC98_FIXTURE.read_bytes()


def string_id(hbco, value: str) -> int:
    for index in range(hbco.getStringCount()):
        if hbco.getString(index)[0] == value:
            return index
    raise AssertionError(f"fixture is missing string {value!r}")
