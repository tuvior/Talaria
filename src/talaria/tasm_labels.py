from __future__ import annotations

from typing import Any

from talaria.models import FunctionBody


def function_offsets_and_labels(
    function: FunctionBody, metadata: Any
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
