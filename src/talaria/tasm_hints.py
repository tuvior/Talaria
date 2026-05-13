from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from talaria.models import FunctionBody, Instruction, Operand
from talaria.tasm_labels import function_offsets_and_labels

KIND_RANKS = {
    "global": 100,
    "module_factory": 95,
    "export_getter": 90,
    "export_setter": 90,
    "generator_body": 85,
    "async_wrapper": 80,
    "runtime_helper": 75,
    "svg_component": 73,
    "react_component": 70,
    "react_hook": 65,
    "event_handler": 60,
    "initializer": 58,
    "parser": 55,
    "getter": 50,
    "setter": 50,
    "method_table": 45,
    "method": 40,
    "closure": 10,
}

CALLBACK_NAMES = frozenset(
    {
        "addEventListener",
        "addListener",
        "catch",
        "filter",
        "finally",
        "forEach",
        "map",
        "memo",
        "reduce",
        "setInterval",
        "setTimeout",
        "sort",
        "then",
        "useCallback",
        "useEffect",
        "useMemo",
        "useSelector",
    }
)

RUNTIME_HELPERS = {
    "_arrayLikeToArray": "babel.array_like_to_array",
    "_callSuper": "babel.call_super",
    "_classCallCheck": "babel.class_call_check",
    "_createClass": "babel.create_class",
    "_createSuper": "babel.create_super",
    "_createSuperInternal": "babel.create_super_internal",
    "_defineProperties": "babel.define_properties",
    "_getPrototypeOf": "babel.get_prototype_of",
    "_getRequireWildcardCache": "babel.get_require_wildcard_cache",
    "_inherits": "babel.inherits",
    "_interopRequireDefault": "babel.interop_require_default",
    "_interopRequireWildcard": "babel.interop_require_wildcard",
    "_isNativeReflectConstruct": "babel.is_native_reflect_construct",
    "_possibleConstructorReturn": "babel.possible_constructor_return",
    "_setPrototypeOf": "babel.set_prototype_of",
    "_slicedToArray": "babel.sliced_to_array",
    "_toConsumableArray": "babel.to_consumable_array",
    "_toPrimitive": "babel.to_primitive",
    "_toPropertyKey": "babel.to_property_key",
    "_typeof": "babel.typeof",
    "_unsupportedIterableToArray": "babel.unsupported_iterable_to_array",
}


def function_hints(
    functions: list[FunctionBody],
    strings: Mapping[int, str],
    metadata: Any,
) -> dict[int, list[str]]:
    builder = _HintBuilder()

    for index, function in enumerate(functions):
        if index == 0 or function.name == "global":
            builder.add(index, "kind global")

        offsets, labels = function_offsets_and_labels(function, metadata)
        _FunctionHintAnalyzer(index, function, offsets, labels, strings, builder).analyze()

    return builder.render()


@dataclass(slots=True)
class _HintBuilder:
    hints: dict[int, list[str]] = field(default_factory=dict)
    seen: dict[int, set[str]] = field(default_factory=dict)

    def add(self, function_id: int, hint: str) -> None:
        if hint.startswith("kind "):
            hint = self._coalesce_kind(function_id, hint)
            if not hint:
                return

        seen = self.seen.setdefault(function_id, set())
        if hint in seen:
            return

        seen.add(hint)
        self.hints.setdefault(function_id, []).append(hint)

    def add_values(
        self, function_id: int, key: str, values: list[str], *, limit: int = 12
    ) -> None:
        if not values:
            return

        hint = f"{key} {' '.join(values[:limit])}"
        if len(values) > limit:
            hint = f"{hint} more:{len(values) - limit}"
        self.add(function_id, hint)

    def render(self) -> dict[int, list[str]]:
        return {
            function_id: self._ordered_hints(hints)
            for function_id, hints in self.hints.items()
        }

    def _ordered_hints(self, hints: list[str]) -> list[str]:
        kinds = [hint for hint in hints if hint.startswith("kind ")]
        confidence = [hint for hint in hints if hint.startswith("confidence ")]
        rest = [
            hint
            for hint in hints
            if not hint.startswith("kind ") and not hint.startswith("confidence ")
        ]

        ordered = kinds[:1]
        if ordered and not confidence:
            ordered.append("confidence derived")
        ordered.extend(confidence[:1])
        ordered.extend(rest)
        return ordered

    def _coalesce_kind(self, function_id: int, hint: str) -> str | None:
        existing_hints = self.hints.get(function_id, [])
        existing_kinds = [value for value in existing_hints if value.startswith("kind ")]
        if not existing_kinds:
            return hint

        incoming_rank = _kind_rank(hint.removeprefix("kind "))
        best_existing_rank = max(
            _kind_rank(existing.removeprefix("kind ")) for existing in existing_kinds
        )
        if incoming_rank <= best_existing_rank:
            return None

        for existing in existing_kinds:
            self.seen.get(function_id, set()).discard(existing)
        self.hints[function_id] = [
            value for value in existing_hints if not value.startswith("kind ")
        ]
        return hint


@dataclass(frozen=True, slots=True)
class _AccessorEntry:
    object_reg: int
    prop: str
    function_id: int
    kind: str


@dataclass(slots=True)
class _RegisterFacts:
    functions: dict[int, int] = field(default_factory=dict)
    creation_opcodes: dict[int, str] = field(default_factory=dict)
    strings: dict[int, str] = field(default_factory=dict)
    numbers: dict[int, int] = field(default_factory=dict)
    array_sizes: dict[int, int] = field(default_factory=dict)
    properties: dict[int, str] = field(default_factory=dict)
    tags: dict[int, set[str]] = field(default_factory=dict)

    def function(self, reg: int) -> int | None:
        return self.functions.get(reg)

    def creation_opcode(self, reg: int) -> str:
        return self.creation_opcodes.get(reg, "")

    def string(self, reg: int) -> str | None:
        return self.strings.get(reg)

    def property(self, reg: int) -> str | None:
        return self.properties.get(reg)

    def number(self, reg: int) -> int | None:
        return self.numbers.get(reg)

    def array_size(self, reg: int) -> int | None:
        return self.array_sizes.get(reg)

    def has_tag(self, reg: int, tag: str) -> bool:
        return tag in self.tags.get(reg, set())

    def tag(self, operand: Operand, tag: str) -> None:
        reg = _reg_value(operand)
        if reg is not None:
            self.tags.setdefault(reg, set()).add(tag)

    def set_function(self, dst: int, function_id: int, opcode: str) -> None:
        self.clear_value(dst)
        self.functions[dst] = function_id
        self.creation_opcodes[dst] = opcode

    def set_string(self, operand: Operand, value: str | None) -> None:
        reg = _reg_value(operand)
        if reg is None:
            return
        self.clear_value(reg)
        if value is not None:
            self.strings[reg] = value

    def set_property(self, operand: Operand, value: str | None) -> None:
        reg = _reg_value(operand)
        if reg is None:
            return
        self.clear_value(reg)
        if value is not None:
            self.properties[reg] = value

    def set_number(self, operands: tuple[Operand, ...]) -> None:
        reg = _reg_value(operands[0])
        if reg is None:
            return
        self.clear_value(reg)
        self.numbers[reg] = 0 if len(operands) == 1 else int(operands[1].value)

    def set_array_size(self, operand: Operand, size: int) -> None:
        reg = _reg_value(operand)
        if reg is None:
            return
        self.clear_value(reg)
        self.array_sizes[reg] = size

    def clear_result(self, operand: Operand) -> None:
        reg = _reg_value(operand)
        if reg is not None:
            self.clear_value(reg)

    def clear_value(self, reg: int) -> None:
        self.functions.pop(reg, None)
        self.creation_opcodes.pop(reg, None)
        self.strings.pop(reg, None)
        self.numbers.pop(reg, None)
        self.array_sizes.pop(reg, None)
        self.properties.pop(reg, None)
        self.tags.pop(reg, None)


@dataclass(slots=True)
class _FunctionHintAnalyzer:
    index: int
    function: FunctionBody
    offsets: list[int]
    labels: dict[int, str]
    strings: Mapping[int, str]
    builder: _HintBuilder
    regs: _RegisterFacts = field(default_factory=_RegisterFacts)
    created_functions: list[str] = field(default_factory=list)
    methods: list[tuple[str, int]] = field(default_factory=list)
    accessor_entries: list[_AccessorEntry] = field(default_factory=list)
    exported_objects: set[int] = field(default_factory=set)
    property_reads: list[str] = field(default_factory=list)
    property_writes: list[str] = field(default_factory=list)
    calls: list[str] = field(default_factory=list)
    capture_slots: list[str] = field(default_factory=list)
    yield_points: list[str] = field(default_factory=list)
    flags: set[str] = field(default_factory=set)

    def analyze(self) -> None:
        for offset, instruction in zip(self.offsets, self.function.instructions, strict=True):
            self._record_instruction_facts(offset, instruction)
            self._handle_instruction(offset, instruction)

        self._emit_summary_hints()

    def _record_instruction_facts(self, offset: int, instruction: Instruction) -> None:
        opcode = instruction.opcode
        operands = instruction.operands

        if opcode == "Catch":
            self.flags.add("has_try")
        if opcode == "DirectEval":
            self.flags.add("uses_eval")
        if opcode.startswith("DelBy"):
            self.flags.add("uses_delete")
        if opcode in {
            "StartGenerator",
            "ResumeGenerator",
            "SaveGenerator",
            "SaveGeneratorLong",
            "CompleteGenerator",
        }:
            self.flags.add("generator_state_machine")
        if opcode in {"ReifyArguments", "GetArgumentsLength", "GetArgumentsPropByVal"}:
            self.flags.add("uses_arguments")
        if opcode in {"SaveGenerator", "SaveGeneratorLong"} and operands:
            self.yield_points.append(_format_hint_addr(offset, operands[0], self.labels))
        if _is_backward_branch(offset, operands):
            self.flags.add("has_loop")
        if opcode.startswith("LoadFromEnvironment") and len(operands) >= 3:
            self.capture_slots.append(f"slot:{operands[2].value}")
            self.flags.add("reads_environment")
        if opcode.startswith("Store") and "Environment" in opcode:
            self.flags.add("writes_environment")

    def _handle_instruction(self, offset: int, instruction: Instruction) -> None:
        opcode = instruction.opcode
        operands = instruction.operands

        if self._handle_load_const_string(opcode, operands):
            return
        if self._handle_load_number(opcode, operands):
            return
        if self._handle_new_array(opcode, operands):
            return
        if self._handle_property_read(opcode, operands):
            return
        if self._handle_create_closure(offset, opcode, operands):
            return
        if self._handle_create_generator(offset, opcode, operands):
            return
        if self._handle_property_write(opcode, operands):
            return
        if self._handle_accessor_definition(opcode, operands):
            return
        if self._handle_call(opcode, operands):
            return

        if operands:
            self.regs.clear_result(operands[0])

    def _handle_load_const_string(
        self, opcode: str, operands: tuple[Operand, ...]
    ) -> bool:
        if not opcode.startswith("LoadConstString") or len(operands) < 2:
            return False
        self.regs.set_string(operands[0], self._string_value(operands[1]))
        return True

    def _handle_load_number(self, opcode: str, operands: tuple[Operand, ...]) -> bool:
        if opcode not in {"LoadConstZero", "LoadConstUInt8", "LoadConstInt"} or not operands:
            return False
        self.regs.set_number(operands)
        return True

    def _handle_new_array(self, opcode: str, operands: tuple[Operand, ...]) -> bool:
        if not opcode.startswith("NewArray") or len(operands) < 2:
            return False
        self.regs.set_array_size(operands[0], int(operands[1].value))
        return True

    def _handle_property_read(self, opcode: str, operands: tuple[Operand, ...]) -> bool:
        if opcode not in {
            "GetById",
            "GetByIdShort",
            "GetByIdLong",
            "TryGetById",
            "TryGetByIdLong",
        }:
            return False
        if len(operands) < 4:
            return True

        prop = self._string_value(operands[3])
        self.regs.set_property(operands[0], prop)
        _add_capped_name(self.property_reads, prop)
        if prop == "exports":
            self.regs.tag(operands[0], "exports")
        if prop == "prototype":
            self.regs.tag(operands[0], "prototype")
        return True

    def _handle_create_closure(
        self, offset: int, opcode: str, operands: tuple[Operand, ...]
    ) -> bool:
        if not (
            opcode.startswith("CreateClosure")
            or opcode.startswith("CreateGeneratorClosure")
        ):
            return False
        if len(operands) < 3:
            return True

        function_id = int(operands[2].value)
        dst = int(operands[0].value)
        env = int(operands[1].value)
        self.regs.set_function(dst, function_id, opcode)
        self.created_functions.append(f"fn@{function_id}")

        kind = "async_wrapper" if "Generator" in opcode else "closure"
        self.builder.add(function_id, f"kind {kind}")
        self.builder.add(function_id, f"parent fn@{self.index}")
        self.builder.add(function_id, f"created_at {_format_hint_offset(offset, self.labels)}")
        self.builder.add(function_id, f"created_by {opcode} env:r{env} dst:r{dst}")
        return True

    def _handle_create_generator(
        self, offset: int, opcode: str, operands: tuple[Operand, ...]
    ) -> bool:
        if not opcode.startswith("CreateGenerator"):
            return False
        if len(operands) >= 3:
            body_id = int(operands[2].value)
            self.created_functions.append(f"fn@{body_id}")
            self.builder.add(self.index, f"creates_generator_body fn@{body_id}")
            self.builder.add(body_id, "kind generator_body")
            self.builder.add(body_id, f"wrapped_by fn@{self.index}")
            self.builder.add(body_id, f"created_at {_format_hint_offset(offset, self.labels)}")
        if operands:
            self.regs.clear_result(operands[0])
        return True

    def _handle_property_write(self, opcode: str, operands: tuple[Operand, ...]) -> bool:
        if opcode.startswith(("PutById", "TryPutById")) and len(operands) >= 4:
            obj_reg = int(operands[0].value)
            value_reg = int(operands[1].value)
            prop = self._string_value(operands[3])
            self._record_property_write(obj_reg, value_reg, prop)
            return True

        if opcode.startswith("PutNewOwnById") and len(operands) >= 3:
            value_reg = int(operands[1].value)
            prop = self._string_value(operands[2])
            self._record_property_write(-1, value_reg, prop)
            return True

        return False

    def _record_property_write(self, obj_reg: int, value_reg: int, prop: str | None) -> None:
        _add_capped_name(self.property_writes, prop)
        if prop in {"exports", "default", "__esModule"} or self.regs.has_tag(
            obj_reg, "exports"
        ):
            self.flags.add("mutates_exports")
        if prop == "exports" and any(
            value_reg == entry.object_reg for entry in self.accessor_entries
        ):
            self.exported_objects.add(value_reg)

        self._assign_function_hint(obj_reg, value_reg, prop)

    def _assign_function_hint(self, obj_reg: int, value_reg: int, prop: str | None) -> None:
        if prop is None:
            return

        function_id = self.regs.function(value_reg)
        if function_id is None:
            return

        if self.regs.has_tag(obj_reg, "exports"):
            self.builder.add(function_id, f"exported_as {json.dumps(prop)}")
        elif prop == "exports":
            self.builder.add(function_id, 'exported_as "module.exports"')

        if prop != "__esModule":
            self.builder.add(function_id, f"assigned_as {json.dumps(prop)}")
            if self.regs.creation_opcode(value_reg).startswith("CreateGeneratorClosure"):
                self.builder.add(function_id, "kind async_wrapper")
            else:
                self.builder.add(function_id, "kind method")
            self.methods.append((prop, function_id))

        if prop == "default" and self.regs.has_tag(obj_reg, "exports"):
            self.builder.add(self.index, f"exported_as {json.dumps(prop)}")

    def _handle_accessor_definition(
        self, opcode: str, operands: tuple[Operand, ...]
    ) -> bool:
        if opcode not in {"PutOwnGetterSetterByVal", "DefineOwnGetterSetterByVal"}:
            return False
        if len(operands) < 5:
            return True

        obj_reg = int(operands[0].value)
        prop_reg = int(operands[1].value)
        prop = self.regs.string(prop_reg)
        if prop is not None:
            self._record_accessor(obj_reg, prop, operands[2], "getter")
            self._record_accessor(obj_reg, prop, operands[3], "setter")
        self.flags.add("defines_accessors")
        return True

    def _record_accessor(
        self, obj_reg: int, prop: str, accessor_operand: Operand, accessor_kind: str
    ) -> None:
        accessor_reg = int(accessor_operand.value)
        function_id = self.regs.function(accessor_reg)
        if function_id is None:
            return

        self.accessor_entries.append(
            _AccessorEntry(obj_reg, prop, function_id, accessor_kind)
        )
        self.builder.add(function_id, f"kind {accessor_kind}")
        self.builder.add(function_id, f"assigned_as {json.dumps(prop)}")
        self.methods.append((prop, function_id))

    def _handle_call(self, opcode: str, operands: tuple[Operand, ...]) -> bool:
        if not _is_call(opcode):
            return False

        call_name = None
        if len(operands) >= 2 and operands[1].type.startswith("Reg"):
            call_name = self.regs.property(int(operands[1].value))

        if call_name == "__d" and len(operands) >= 6:
            self._add_metro_module_hint(operands)
        if call_name:
            _add_capped_name(self.calls, call_name)
            self._add_callback_hints(call_name, operands)
        if operands:
            self.regs.clear_result(operands[0])
        return True

    def _add_metro_module_hint(self, operands: tuple[Operand, ...]) -> None:
        factory_id = _reg_value(operands[3])
        if factory_id is None:
            return

        function_id = self.regs.function(factory_id)
        if function_id is None:
            return

        self.builder.add(function_id, "kind module_factory")

        module_reg = _reg_value(operands[4])
        if module_reg is not None:
            module_id = self.regs.number(module_reg)
            if module_id is not None:
                self.builder.add(function_id, f"metro_module_id {module_id}")

        deps_reg = _reg_value(operands[5])
        if deps_reg is not None:
            dependency_count = self.regs.array_size(deps_reg)
            if dependency_count is not None:
                self.builder.add(function_id, f"metro_dependencies count:{dependency_count}")

        self.builder.add(self.index, f"metro_module fn@{function_id}")

    def _add_callback_hints(self, call_name: str, operands: tuple[Operand, ...]) -> None:
        if call_name not in CALLBACK_NAMES:
            return

        for arg_index, operand in enumerate(operands[3:]):
            arg_reg = _reg_value(operand)
            if arg_reg is None:
                continue
            function_id = self.regs.function(arg_reg)
            if function_id is None:
                continue
            self.builder.add(function_id, f"callback_for {json.dumps(call_name)} arg:{arg_index}")
            self.builder.add(function_id, "kind closure")

    def _emit_summary_hints(self) -> None:
        if self.created_functions:
            self.builder.add_values(self.index, "creates", self.created_functions, limit=16)
        if self.methods:
            for prop, function_id in self.methods[:20]:
                self.builder.add(self.index, f"method {json.dumps(prop)} fn@{function_id}")
            if len(self.methods) > 20:
                self.builder.add(self.index, f"method_count {len(self.methods)}")

        self._emit_exported_accessor_hints()

        self.builder.add_values(
            self.index, "captures", sorted(set(self.capture_slots)), limit=12
        )
        self.builder.add_values(
            self.index, "calls", [json.dumps(name) for name in self.calls], limit=10
        )
        self.builder.add_values(
            self.index,
            "property_reads",
            [json.dumps(name) for name in self.property_reads],
            limit=10,
        )
        self.builder.add_values(
            self.index,
            "property_writes",
            [json.dumps(name) for name in self.property_writes],
            limit=10,
        )
        self.builder.add_values(self.index, "yield_points", self.yield_points, limit=12)
        self._emit_named_hints()
        self._emit_size_flags()
        if self.flags:
            self.builder.add(self.index, f"flags {' '.join(sorted(self.flags))}")

    def _emit_exported_accessor_hints(self) -> None:
        for entry in self.accessor_entries:
            if entry.object_reg not in self.exported_objects:
                continue
            export_kind = f"export_{entry.kind}"
            self.builder.add(entry.function_id, f"kind {export_kind}")
            self.builder.add(entry.function_id, f"exported_as {json.dumps(entry.prop)}")
            self.builder.add(
                self.index,
                f"{export_kind} {json.dumps(entry.prop)} fn@{entry.function_id}",
            )
            self.flags.add("lazy_exports")

        for obj_reg in sorted(self.exported_objects):
            self.builder.add(self.index, f"exports_object r{obj_reg}")

    def _emit_named_hints(self) -> None:
        helper = RUNTIME_HELPERS.get(self.function.name)
        if helper is not None:
            self.builder.add(self.index, "kind runtime_helper")
            self.builder.add(self.index, f"helper {helper}")

        inferred_kind = _infer_named_kind(self.function.name)
        if inferred_kind is not None:
            self.builder.add(self.index, f"kind {inferred_kind}")

    def _emit_size_flags(self) -> None:
        if self.function.register_count > 64 or len(self.function.instructions) > 500:
            self.flags.add("large_function")
        if self.function.register_count > 255:
            self.flags.add("wide_registers")

    def _string_value(self, operand: Operand) -> str | None:
        if operand.is_string:
            return self.strings.get(int(operand.value))
        return None


def _kind_rank(kind: str) -> int:
    return KIND_RANKS.get(kind, 0)


def _infer_named_kind(name: str) -> str | None:
    if not name:
        return None
    if name == "initializer":
        return "initializer"
    if name == "SvgComponent":
        return "svg_component"
    if name == "parse" or name.startswith("parse"):
        return "parser"
    if name.startswith("use") and len(name) > 3 and name[3].isupper():
        return "react_hook"
    if name.startswith("on") and len(name) > 2 and name[2].isupper():
        return "event_handler"
    if name[:1].isupper() and not name.startswith("_"):
        return "react_component"
    return None


def _format_hint_offset(offset: int, labels: dict[int, str]) -> str:
    return labels.get(offset, f"offset:0x{offset:04x}")


def _format_hint_addr(offset: int, operand: Operand, labels: dict[int, str]) -> str:
    if not operand.type.startswith("Addr"):
        return f"offset:0x{offset:04x}"
    target = offset + int(operand.value)
    return labels.get(target, f"offset:0x{target:04x}")


def _is_backward_branch(offset: int, operands: tuple[Operand, ...]) -> bool:
    return any(
        operand.type.startswith("Addr") and offset + int(operand.value) < offset
        for operand in operands
    )


def _is_call(opcode: str) -> bool:
    return opcode.startswith("Call") or opcode.startswith("Construct")


def _reg_value(operand: Operand) -> int | None:
    if operand.type.startswith("Reg"):
        return int(operand.value)
    return None


def _add_capped_name(names: list[str], name: str | None, *, limit: int = 40) -> None:
    if not name or name in names or len(names) >= limit:
        return
    names.append(name)
