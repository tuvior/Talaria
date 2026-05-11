from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Self


@dataclass(frozen=True, slots=True)
class Operand:
    type: str
    is_string: bool
    value: Any

    @classmethod
    def from_hbc_tuple(cls, operand: tuple[str, bool, Any]) -> Self:
        operand_type, is_string, value = operand
        return cls(type=operand_type, is_string=is_string, value=value)

    def to_hbc_tuple(self) -> tuple[str, bool, Any]:
        return self.type, self.is_string, self.value


@dataclass(frozen=True, slots=True)
class Instruction:
    opcode: str
    operands: tuple[Operand, ...]

    @classmethod
    def from_hbc_tuple(cls, instruction: tuple[str, list[tuple[str, bool, Any]]]) -> Self:
        opcode, operands = instruction
        parsed_operands = tuple(Operand.from_hbc_tuple(operand) for operand in operands)
        return cls(opcode=opcode, operands=parsed_operands)

    def to_hbc_tuple(self) -> tuple[str, list[tuple[str, bool, Any]]]:
        return self.opcode, [operand.to_hbc_tuple() for operand in self.operands]


@dataclass(frozen=True, slots=True)
class FunctionBody:
    name: str
    param_count: int
    register_count: int
    symbol_count: int
    instructions: tuple[Instruction, ...]
    header: dict[str, Any] | None = None

    @classmethod
    def from_hbc_tuple(cls, func) -> Self:
        name, param_count, register_count, symbol_count, instructions, header = func
        return cls(
            name=name,
            param_count=param_count,
            register_count=register_count,
            symbol_count=symbol_count,
            instructions=tuple(
                Instruction.from_hbc_tuple(instruction) for instruction in instructions
            ),
            header=header,
        )

    def to_hbc_tuple(self):
        return (
            self.name,
            self.param_count,
            self.register_count,
            self.symbol_count,
            [instruction.to_hbc_tuple() for instruction in self.instructions],
            self.header,
        )
