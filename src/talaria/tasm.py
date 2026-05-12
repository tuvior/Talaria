from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Any, TextIO

import talaria.hbc as hbcl
from talaria.models import FunctionBody, Instruction, Operand

FORMAT_NAME = "talaria.disassembly"
FORMAT_VERSION = 3
MANIFEST_FILE = "talaria.json"
BUNDLE_FILE = "bundle.json"
STRINGS_FILE = "strings.json"
FUNCTIONS_FILE = "functions.tasm"

FUNCTION_BLOCK_RE = re.compile(r"(?ms)^\.function\s+@(?P<id>[0-9]+)\n.*?^\.end function$")
FUNCTION_ID_RE = re.compile(r"^\.function\s+@([0-9]+)$", re.MULTILINE)
LABEL_RE = re.compile(r"^:[A-Za-z_.$][A-Za-z0-9_.$-]*$")
TYPED_OPERAND_RE = re.compile(
    r"(?P<prefix>r32|u8|u16|u32|i32|imm32|addr8|addr32|f64):(?P<value>.+)"
)
NUMERIC_ALIAS_PREFIXES = frozenset({"argc", "param", "slot", "cache", "env"})

OPERAND_SIZES = {
    "Reg8": 1,
    "Reg32": 4,
    "UInt8": 1,
    "UInt16": 2,
    "UInt32": 4,
    "Addr8": 1,
    "Addr32": 4,
    "Imm32": 4,
    "Double": 8,
}


@dataclass(frozen=True, slots=True)
class OpcodeMetadata:
    operands: dict[str, list[str]]
    operand_types: dict[str, list[str]]
    operand_roles: dict[str, list[str | None]]
    opcode_sizes: dict[str, int]

    def operand_type(self, opcode: str, index: int) -> str:
        try:
            return self.operand_types[opcode][index]
        except KeyError as error:
            raise ValueError(f"Unknown opcode: {opcode}") from error
        except IndexError as error:
            raise ValueError(f"Operand {index + 1} is not valid for {opcode}") from error

    def operand_role(self, opcode: str, index: int) -> str | None:
        try:
            return self.operand_roles[opcode][index]
        except (KeyError, IndexError):
            return None

    def instruction_size(self, instruction: Instruction) -> int:
        return self.instruction_size_from_opcode(instruction.opcode)

    def instruction_size_from_opcode(self, opcode: str) -> int:
        try:
            return self.opcode_sizes[opcode]
        except KeyError as error:
            raise ValueError(f"Unknown opcode: {opcode}") from error


@dataclass(slots=True)
class TasmContext:
    metadata: OpcodeMetadata
    original_strings: dict[int, str]
    strings: dict[int, str]
    encoded_strings: dict[int, str]
    string_updates: dict[int, str] = field(default_factory=dict)

    @classmethod
    def from_hbc(cls, hbc, strings: list[dict[str, Any]] | None = None) -> TasmContext:
        version = hbc.getHeader()["version"]
        if strings is None:
            string_values = {
                index: hbc.getString(index)[0] for index in range(hbc.getStringCount())
            }
        else:
            string_values = {int(string["id"]): str(string["value"]) for string in strings}

        return cls(
            metadata=_load_opcode_metadata(version),
            original_strings=string_values.copy(),
            strings=string_values,
            encoded_strings={
                string_id: json.dumps(value) for string_id, value in string_values.items()
            },
        )

    def resolve_string_value(self, value: str) -> int:
        matches = [
            string_id for string_id, string_value in self.strings.items() if value == string_value
        ]
        if not matches:
            raise ValueError(f"String literal is not present in strings.json: {value!r}")
        if len(matches) > 1:
            ids = ", ".join(str(match) for match in matches)
            raise ValueError(f"String literal {value!r} is ambiguous; use s@id. Matches: {ids}")
        return matches[0]

    def update_string(self, string_id: int, value: str) -> None:
        if string_id not in self.strings:
            raise ValueError(f"String ID {string_id} is outside strings.json")
        original_value = self.original_strings[string_id]
        current_update = self.string_updates.get(string_id)
        if value == original_value and current_update is not None:
            return
        if current_update is not None and current_update != value:
            raise ValueError(
                f"Conflicting edits for string {string_id}: " f"{current_update!r} and {value!r}"
            )

        self.strings[string_id] = value
        self.encoded_strings[string_id] = json.dumps(value)
        if value != original_value:
            self.string_updates[string_id] = value


@cache
def _load_opcode_metadata(version: int) -> OpcodeMetadata:
    version_path = Path(__file__).parent / "hbc" / f"hbc{version}"
    operands = json.loads((version_path / "data" / "opcode.json").read_text())
    roles: dict[tuple[str, int], str] = {}

    bytecode_list_path = version_path / "raw" / "BytecodeList.def"
    if bytecode_list_path.exists():
        for line in bytecode_list_path.read_text().splitlines():
            role_match = re.search(
                r"OPERAND_(?P<role>STRING|FUNCTION|BIGINT)_ID"
                r"\((?P<opcode>[A-Za-z0-9_]+),\s*(?P<index>[0-9]+)\)",
                line,
            )
            if role_match:
                roles[
                    (
                        role_match.group("opcode"),
                        int(role_match.group("index")) - 1,
                    )
                ] = role_match.group("role").lower()

    for (opcode, index), role in tuple(roles.items()):
        for suffix in ("LongIndex", "Long"):
            if not opcode.endswith(suffix):
                continue
            short_opcode = opcode.removesuffix(suffix)
            if short_opcode in operands and len(operands[short_opcode]) == len(operands[opcode]):
                roles.setdefault((short_opcode, index), role)

    operand_types = {
        opcode: [operand_type.removesuffix(":S") for operand_type in operand_list]
        for opcode, operand_list in operands.items()
    }
    operand_roles = {}
    for opcode, operand_list in operands.items():
        opcode_roles = []
        for index, operand_type in enumerate(operand_list):
            opcode_roles.append(
                roles.get((opcode, index), "string" if operand_type.endswith(":S") else None)
            )
        operand_roles[opcode] = opcode_roles

    opcode_sizes = {
        opcode: 1 + sum(OPERAND_SIZES[operand_type] for operand_type in operand_list)
        for opcode, operand_list in operand_types.items()
    }

    return OpcodeMetadata(
        operands=operands,
        operand_types=operand_types,
        operand_roles=operand_roles,
        opcode_sizes=opcode_sizes,
    )


def write_func(out: TextIO, function: FunctionBody, index: int, context: TasmContext) -> None:
    offsets, labels = _function_offsets_and_labels(function, context.metadata)

    out.write(f".function @{index}\n")
    out.write(f"    .name {json.dumps(function.name)}\n")
    out.write(f"    .params {function.param_count}\n")
    out.write(f"    .registers {function.register_count}\n")
    out.write(f"    .symbols {function.symbol_count}\n\n")

    previous_opcode: str | None = None
    for offset, instruction in zip(offsets, function.instructions, strict=True):
        label = labels.get(offset)
        if label is not None:
            if previous_opcode is not None:
                out.write("\n")
            out.write(f"{label}\n")
        elif previous_opcode is not None and _starts_new_instruction_group(
            previous_opcode, instruction.opcode
        ):
            out.write("\n")
        previous_opcode = instruction.opcode

        encoded_operands = [
            _format_operand(instruction, operand_index, operand, offset, labels, context)
            for operand_index, operand in enumerate(instruction.operands)
        ]
        operands = f" {', '.join(encoded_operands)}" if encoded_operands else ""
        out.write(f"    {instruction.opcode}{operands}\n")

    out.write(".end function\n\n")


def _function_offsets_and_labels(
    function: FunctionBody, metadata: OpcodeMetadata
) -> tuple[list[int], dict[int, str]]:
    offsets: list[int] = []
    offset = 0
    for instruction in function.instructions:
        offsets.append(offset)
        offset += metadata.instruction_size(instruction)

    valid_offsets = set(offsets)
    labels: dict[int, str] = {}
    for instruction_offset, instruction in zip(offsets, function.instructions, strict=True):
        for operand in instruction.operands:
            if not operand.type.startswith("Addr"):
                continue
            target = instruction_offset + operand.value
            if target in valid_offsets:
                labels.setdefault(target, f":L{target:04x}")

    return offsets, labels


def _starts_new_instruction_group(previous_opcode: str, opcode: str) -> bool:
    previous_is_declaration = previous_opcode.startswith("Declare")
    opcode_is_declaration = opcode.startswith("Declare")
    if previous_is_declaration:
        return not opcode_is_declaration
    if opcode_is_declaration:
        return True
    if _is_unconditional_terminator(previous_opcode):
        return True
    return _is_call(previous_opcode) and _starts_fresh_setup(opcode)


def _is_unconditional_terminator(opcode: str) -> bool:
    return opcode in {"Jmp", "JmpLong"} or opcode.startswith(("Ret", "Throw"))


def _is_call(opcode: str) -> bool:
    return opcode.startswith("Call") or opcode.startswith("Construct")


def _starts_fresh_setup(opcode: str) -> bool:
    return opcode.startswith(("CreateClosure", "GetGlobalObject", "TryGetById"))


def _format_operand(
    instruction: Instruction,
    operand_index: int,
    operand: Operand,
    instruction_offset: int,
    labels: dict[int, str],
    context: TasmContext,
) -> str:
    role = context.metadata.operand_role(instruction.opcode, operand_index)

    if role == "string" or operand.is_string:
        return _format_string_operand(operand, context)
    if role == "function":
        return f"fn@{operand.value}"
    if role == "bigint":
        return f"bigint@{operand.value}"
    if operand.type == "Reg8":
        return f"r{operand.value}"
    if operand.type == "Reg32":
        return f"r32:{operand.value}"
    if operand.type.startswith("Addr"):
        target = instruction_offset + operand.value
        return labels.get(target, f"addr{operand.type.removeprefix('Addr')}:{operand.value}")
    if operand.type.startswith("UInt"):
        return _format_uint_operand(instruction.opcode, operand_index, operand)
    if operand.type == "Imm32":
        return f"i32:{operand.value}"
    if operand.type == "Double":
        return f"f64:{operand.value}"
    return f"{operand.type}:{operand.value}"


def _format_string_operand(operand: Operand, context: TasmContext) -> str:
    encoded_string = context.encoded_strings.get(operand.value)
    if encoded_string is None:
        return f"s@{operand.value}"
    return f"s@{operand.value} {encoded_string}"


def _format_uint_operand(opcode: str, operand_index: int, operand: Operand) -> str:
    if opcode in {"Call", "Construct", "CallBuiltin", "CallBuiltinLong"} and operand_index == 2:
        return f"argc:{operand.value}"
    if opcode in {"LoadParam", "LoadParamLong"} and operand_index == 1:
        return f"param:{operand.value}"
    if opcode in {"StoreToEnvironment", "StoreNPToEnvironment"} and operand_index == 1:
        return f"slot:{operand.value}"
    if opcode in {"StoreToEnvironmentL", "StoreNPToEnvironmentL"} and operand_index == 1:
        return f"slot:{operand.value}"
    if opcode in {"LoadFromEnvironment", "LoadFromEnvironmentL"} and operand_index == 2:
        return f"slot:{operand.value}"
    if "ById" in opcode and operand.type == "UInt8" and operand_index == 2:
        return f"cache:{operand.value}"
    return str(operand.value)


def dump(hbc, path: str | Path, force: bool = False) -> None:
    output_path = Path(path)

    if output_path.exists():
        if not force:
            raise FileExistsError(f"{output_path} already exists; pass force=True to replace it")
        shutil.rmtree(output_path)

    output_path.mkdir(parents=True)
    _write_manifest(output_path)
    strings = _collect_strings(hbc)
    context = TasmContext.from_hbc(hbc, strings)
    (output_path / BUNDLE_FILE).write_text(json.dumps(hbc.getObj()))
    (output_path / STRINGS_FILE).write_text(json.dumps(strings, indent=2))

    with (output_path / FUNCTIONS_FILE).open("w") as out:
        out.write("# Talaria assembly v3\n\n")
        for index in range(hbc.getFunctionCount()):
            function = FunctionBody.from_hbc_tuple(hbc.getFunction(index))
            write_func(out, function, index, context)


def _write_manifest(output_path: Path) -> None:
    manifest = {
        "format": FORMAT_NAME,
        "formatVersion": FORMAT_VERSION,
        "files": {
            "bundle": BUNDLE_FILE,
            "strings": STRINGS_FILE,
            "functions": FUNCTIONS_FILE,
        },
    }
    (output_path / MANIFEST_FILE).write_text(json.dumps(manifest, indent=2))


def _collect_strings(hbc) -> list[dict[str, object]]:
    strings = []
    for index in range(hbc.getStringCount()):
        value, header = hbc.getString(index)
        strings.append({"id": index, "isUTF16": header[0] == 1, "value": value})
    return strings


def read_all_func(tasm: str, hbc) -> list[str | None]:
    function_count = hbc.getFunctionCount()
    functions: list[str | None] = [None] * function_count

    for match in FUNCTION_BLOCK_RE.finditer(tasm):
        func_asm = match.group(0)
        header = FUNCTION_ID_RE.search(func_asm)
        if not header:
            raise ValueError(f"Malformed function header: {func_asm}")

        function_id = int(header.group(1))
        if function_id < 0 or function_id >= function_count:
            raise ValueError(f"Function ID {function_id} is outside 0..{function_count - 1}")

        functions[function_id] = func_asm

    return functions


def read_func(func_asms: list[str | None], index: int, context: TasmContext) -> FunctionBody | None:
    func_asm = func_asms[index]
    if func_asm is None:
        return None

    return _read_function(func_asm, context)


def _read_function(func_asm: str, context: TasmContext) -> FunctionBody:
    lines = func_asm.splitlines()
    if not FUNCTION_ID_RE.match(lines[0]):
        raise ValueError(f"Malformed function header: {func_asm}")

    name: str | None = None
    param_count: int | None = None
    register_count: int | None = None
    symbol_count: int | None = None
    instruction_lines = []

    for line in lines[1:]:
        stripped = line.strip()
        if not stripped or stripped.startswith(";"):
            continue
        if stripped == ".end function":
            break
        if stripped.startswith(".name "):
            name = json.loads(stripped.removeprefix(".name "))
        elif stripped.startswith(".params "):
            param_count = int(stripped.removeprefix(".params "))
        elif stripped.startswith(".registers "):
            register_count = int(stripped.removeprefix(".registers "))
        elif stripped.startswith(".symbols "):
            symbol_count = int(stripped.removeprefix(".symbols "))
        elif stripped.startswith("."):
            raise ValueError(f"Unknown function directive: {stripped}")
        else:
            instruction_lines.append(stripped)

    if name is None or param_count is None or register_count is None or symbol_count is None:
        raise ValueError(f"Incomplete function header: {func_asm}")

    return FunctionBody(
        name=name,
        param_count=param_count,
        register_count=register_count,
        symbol_count=symbol_count,
        instructions=tuple(_read_instructions(instruction_lines, context)),
    )


def _read_instructions(lines: list[str], context: TasmContext) -> list[Instruction]:
    parsed_lines: list[tuple[int, str, list[str]]] = []
    labels: dict[str, int] = {}
    offset = 0

    for raw_line in lines:
        line = _strip_comment(raw_line).strip()
        if not line or line.startswith(";"):
            continue
        if _is_label(line):
            labels[line] = offset
            continue

        opcode, operands = _split_instruction(line)
        parsed_lines.append((offset, opcode, operands))
        offset += context.metadata.instruction_size_from_opcode(opcode)

    instructions = []
    for instruction_offset, opcode, operands in parsed_lines:
        expected_count = len(context.metadata.operands[opcode])
        if len(operands) != expected_count:
            raise ValueError(f"{opcode} expects {expected_count} operand(s), got {len(operands)}")

        operand_types = context.metadata.operand_types[opcode]
        operand_roles = context.metadata.operand_roles[opcode]
        parsed_operands = [
            _parse_rendered_operand(
                operand,
                opcode=opcode,
                expected_type=operand_types[operand_index],
                role=operand_roles[operand_index],
                instruction_offset=instruction_offset,
                labels=labels,
                context=context,
            )
            for operand_index, operand in enumerate(operands)
        ]
        instructions.append(Instruction(opcode, tuple(parsed_operands)))

    return instructions


def _strip_comment(line: str) -> str:
    if "#" not in line:
        return line

    in_string = False
    escaped = False
    for index, char in enumerate(line):
        if escaped:
            escaped = False
            continue
        if char == "\\" and in_string:
            escaped = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if char == "#" and not in_string:
            return line[:index]
    return line


def _is_label(line: str) -> bool:
    return line.startswith(":") and LABEL_RE.fullmatch(line) is not None


def _split_instruction(line: str) -> tuple[str, list[str]]:
    opcode, _, rest = line.partition(" ")
    rest = rest.strip()
    if not rest:
        return opcode, []
    return opcode, _split_operands(rest)


def _split_operands(operands: str) -> list[str]:
    if '"' not in operands:
        if ", " in operands:
            return operands.split(", ")
        return [operand.strip() for operand in operands.split(",")]

    parts = []
    start = 0
    in_string = False
    escaped = False

    for index, char in enumerate(operands):
        if escaped:
            escaped = False
            continue
        if char == "\\" and in_string:
            escaped = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if char == "," and not in_string:
            parts.append(operands[start:index].strip())
            start = index + 1

    parts.append(operands[start:].strip())
    return parts


def _parse_rendered_operand(
    operand: str,
    *,
    opcode: str,
    expected_type: str,
    role: str | None,
    instruction_offset: int,
    labels: dict[str, int],
    context: TasmContext,
) -> Operand:
    if role == "string":
        return _parse_string_operand(operand, expected_type, context)
    if role == "function":
        return _parse_prefixed_id_operand(operand, expected_type, "fn@", "function")
    if role == "bigint":
        return _parse_prefixed_id_operand(operand, expected_type, "bigint@", "bigint")

    if expected_type == "Reg8" and operand.startswith("r") and operand[1:].isdigit():
        return Operand("Reg8", False, int(operand[1:]))

    if expected_type.startswith("Addr") and operand.startswith(":"):
        if operand not in labels:
            raise ValueError(f"Unknown label {operand} in {opcode}")
        return Operand(expected_type, False, labels[operand] - instruction_offset)

    alias_value = _parse_numeric_alias(operand)
    if alias_value is not None:
        return Operand(expected_type, False, alias_value)

    typed_match = TYPED_OPERAND_RE.fullmatch(operand)
    if typed_match:
        operand_type = _operand_prefix_to_type(typed_match.group("prefix"))
        value = _parse_operand(operand_type, typed_match.group("value"))
        return Operand(operand_type, False, value)

    if _is_int(operand):
        return Operand(expected_type, False, int(operand))

    operand_type, value = operand.split(":", 1)
    return Operand(operand_type, False, _parse_operand(operand_type, value))


def _parse_string_operand(operand: str, expected_type: str, context: TasmContext) -> Operand:
    prefix, separator, rest = operand.partition("@")
    if separator and prefix in {"s", "str8", "str16", "str32"}:
        string_id_text, _, encoded_value = rest.partition(" ")
        if not string_id_text.isdigit():
            raise ValueError(f"Expected string reference, got: {operand}")

        string_id = int(string_id_text)
        encoded_value = encoded_value.strip()
        if encoded_value and encoded_value != context.encoded_strings.get(string_id):
            context.update_string(string_id, json.loads(encoded_value))

        operand_type = expected_type if prefix == "s" else f"UInt{prefix.removeprefix('str')}"
        return Operand(operand_type, True, string_id)

    if operand.startswith('"'):
        return Operand(expected_type, True, context.resolve_string_value(json.loads(operand)))

    raise ValueError(f"Expected string operand, got: {operand}")


def _parse_prefixed_id_operand(
    operand: str, expected_type: str, prefix: str, role_name: str
) -> Operand:
    if not operand.startswith(prefix):
        raise ValueError(f"Expected {role_name} reference, got: {operand}")
    value = operand.removeprefix(prefix)
    if not value.isdigit():
        raise ValueError(f"Expected {role_name} reference, got: {operand}")
    return Operand(expected_type, False, int(value))


def _parse_numeric_alias(operand: str) -> int | None:
    prefix, separator, value = operand.partition(":")
    if separator and prefix in NUMERIC_ALIAS_PREFIXES:
        return int(value)
    return None


def _is_int(value: str) -> bool:
    return value.isdigit() or (len(value) > 1 and value[0] == "-" and value[1:].isdigit())


def _operand_prefix_to_type(prefix: str) -> str:
    return {
        "r32": "Reg32",
        "u8": "UInt8",
        "u16": "UInt16",
        "u32": "UInt32",
        "i32": "Imm32",
        "imm32": "Imm32",
        "addr8": "Addr8",
        "addr32": "Addr32",
        "f64": "Double",
    }[prefix]


def _parse_operand(operand_type: str, value: str) -> Any:
    if operand_type == "Double":
        if value == "-nan":
            return value
        return float(value)
    return int(value)


def load(path: str | Path):
    input_path = Path(path)
    paths = _resolve_workspace_paths(input_path)

    for required_path in paths.values():
        if not required_path.exists():
            raise FileNotFoundError(required_path)

    hbc = hbcl.loado(json.loads(paths["bundle"].read_text()))
    tasm_content = paths["functions"].read_text()
    strings = json.loads(paths["strings"].read_text())
    context = TasmContext.from_hbc(hbc, strings)

    for string in strings:
        hbc.setString(string["id"], string["value"])

    func_asms = read_all_func(tasm_content, hbc)
    functions: list[tuple[int, FunctionBody]] = []
    for index, _ in enumerate(func_asms):
        func = read_func(func_asms, index, context)
        if func is not None:
            functions.append((index, func))

    for string_id, value in context.string_updates.items():
        hbc.setString(string_id, value)

    for index, func in functions:
        hbc.setFunction(index, func.to_hbc_tuple())

    return hbc


def _resolve_workspace_paths(input_path: Path) -> dict[str, Path]:
    manifest_path = input_path / MANIFEST_FILE
    if not manifest_path.exists():
        raise FileNotFoundError(manifest_path)

    manifest = json.loads(manifest_path.read_text())
    if manifest.get("format") != FORMAT_NAME:
        raise ValueError(f"Unsupported Talaria workspace format: {manifest.get('format')}")
    if manifest.get("formatVersion") != FORMAT_VERSION:
        raise ValueError(f"Unsupported Talaria TASM version: {manifest.get('formatVersion')}")

    files = manifest["files"]
    return {
        "bundle": input_path / files["bundle"],
        "strings": input_path / files["strings"],
        "functions": input_path / files["functions"],
    }
