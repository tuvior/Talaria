#!/usr/bin/env python3
import argparse
import json
import pathlib
import re

JMP_OPERAND = {
    "1": ["Addr8"],
    "1Long": ["Addr32"],
    "2": ["Addr8", "Reg8"],
    "2Long": ["Addr32", "Reg8"],
    "3": ["Addr8", "Reg8", "Reg8"],
    "3Long": ["Addr32", "Reg8", "Reg8"],
}


def generate(bytecode_list_path):
    opcode = 0
    json_op = {}

    def add_op(name, operands):
        nonlocal opcode
        json_op[name] = operands
        opcode += 1

    for line_num, line in enumerate(bytecode_list_path.read_text().splitlines(), 1):
        if line.startswith("DEFINE_OPCODE_"):
            match = re.search(r"\((\w+)((, \w+)*)\)", line)
            if not match:
                raise ValueError(f"Unhandled opcode definition at line {line_num}: {line}")
            name = match.group(1)
            operands = match.group(2).split(", ")[1:]
            add_op(name, operands)

        elif line.startswith("OPERAND_STRING_ID"):
            match = re.search(r"\((\w+), (\w+)\)", line)
            if not match:
                raise ValueError(f"Unhandled string operand marker at line {line_num}: {line}")
            name = match.group(1)
            operand_id = int(match.group(2)) - 1
            if name not in json_op:
                raise ValueError(f"Opcode not found at line {line_num}: {name}")
            if operand_id >= len(json_op[name]):
                raise ValueError(f"Operand not found at line {line_num}: {operand_id}")
            json_op[name][operand_id] += ":S"

        elif line.startswith("DEFINE_JUMP_LONG_VARIANT"):
            continue

        elif line.startswith("DEFINE_JUMP_"):
            match = re.search(r"(\d)\((\w+)\)", line)
            if not match:
                raise ValueError(f"Unhandled jump definition at line {line_num}: {line}")
            num_op = match.group(1)
            name = match.group(2)
            add_op(name, JMP_OPERAND[f"{num_op}"])
            add_op(f"{name}Long", JMP_OPERAND[f"{num_op}Long"])

        elif (
            line.startswith("ASSERT_")
            or line.startswith("DEFINE_RET_TARGET")
            or line.startswith("DEFINE_OPERAND_TYPE")
            or line.startswith("OPERAND_FUNCTION_ID")
            or line.startswith("OPERAND_BIGINT_ID")
            or line.startswith("#")
            or line.startswith("//")
            or line.startswith("/*")
            or line.startswith(" *")
            or line.startswith("  ")
            or not line
        ):
            continue

        else:
            raise ValueError(f"Unhandled BytecodeList.def line {line_num}: {line}")

    return json_op


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("bytecode_list", type=pathlib.Path)
    parser.add_argument("-o", "--output", type=pathlib.Path)
    args = parser.parse_args()

    json_op = generate(args.bytecode_list)
    text = json.dumps(json_op, indent=4) + "\n"
    if args.output:
        args.output.write_text(text)
    else:
        print(text)


if __name__ == "__main__":
    main()
