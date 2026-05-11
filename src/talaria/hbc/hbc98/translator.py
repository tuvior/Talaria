import pathlib
import json
from talaria.util import *
from talaria.translator import disassemble_ops, assemble_ops

basepath = pathlib.Path(__file__).parent.absolute()

operand_type = {
    "Reg8": (1, to_uint8, from_uint8),
    "Reg32": (4, to_uint32, from_uint32),
    "UInt8": (1, to_uint8, from_uint8),
    "UInt16": (2, to_uint16, from_uint16),
    "UInt32": (4, to_uint32, from_uint32),
    "Addr8": (1, to_int8, from_int8),
    "Addr32": (4, to_int32, from_int32),
    "Imm32": (4, to_int32, from_int32),
    "Double": (8, to_double, from_double),
}

f = open(f"{basepath}/data/opcode.json", "r")
opcode_operand = json.load(f)
opcode_mapper = list(opcode_operand.keys())
opcode_mapper_inv = {}
for i, v in enumerate(opcode_mapper):
    opcode_mapper_inv[v] = i

f.close()


def disassemble(bc, strict=False):
    return disassemble_ops(bc, opcode_mapper, opcode_operand, operand_type, strict=strict)


def assemble(insts):
    return assemble_ops(insts, opcode_mapper_inv, opcode_operand, operand_type)
