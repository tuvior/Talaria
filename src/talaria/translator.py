RAW_OPCODE = ".raw"


class DecodeError(Exception):
    def __init__(
        self,
        offset: int,
        opcode_byte: int,
        opcode: str,
        operand_type: str | None,
        needed: int,
        remaining: int,
    ) -> None:
        self.offset = offset
        self.opcode_byte = opcode_byte
        self.opcode = opcode
        self.operand_type = operand_type
        self.needed = needed
        self.remaining = remaining
        super().__init__(
            f"Cannot decode {opcode} at byte {offset}: operand {operand_type} "
            f"needs {needed} byte(s), only {remaining} remain"
        )


def disassemble_ops(bc, opcode_mapper, opcode_operand, operand_type, strict=False):
    i = 0
    insts = []
    while i < len(bc):
        opcode_start = i
        opcode_byte = bc[i]
        try:
            opcode = opcode_mapper[opcode_byte]
        except IndexError:
            if strict:
                raise DecodeError(opcode_start, opcode_byte, "<unknown>", None, 1, 0) from None
            insts.append((RAW_OPCODE, [("UInt8", False, v) for v in bc[opcode_start:]]))
            break

        i += 1
        inst = (opcode, [])
        operand_ts = opcode_operand[opcode]
        for oper_t in operand_ts:
            is_str = oper_t.endswith(":S")
            if is_str:
                oper_t = oper_t[:-2]

            size, conv_to, _ = operand_type[oper_t]
            remaining = len(bc) - i
            if remaining < size:
                if strict:
                    raise DecodeError(opcode_start, opcode_byte, opcode, oper_t, size, remaining)
                insts.append((RAW_OPCODE, [("UInt8", False, v) for v in bc[opcode_start:]]))
                return insts

            val = conv_to(bc[i : i + size])
            inst[1].append((oper_t, is_str, val))
            i += size

        insts.append(inst)

    return insts


def assemble_ops(insts, opcode_mapper_inv, opcode_operand, operand_type):
    bc = []
    for opcode, operands in insts:
        if opcode == RAW_OPCODE:
            bc.extend(val for oper_t, _, val in operands if oper_t == "UInt8")
            continue

        op = opcode_mapper_inv[opcode]
        bc.append(op)
        if len(opcode_operand[opcode]) != len(operands):
            raise ValueError(f"Invalid instruction operand count: {op}, {operands}")
        for oper_t, _, val in operands:
            if oper_t not in operand_type:
                raise ValueError(f"Invalid operand type: {oper_t}")
            _, _, conv_from = operand_type[oper_t]
            bc.extend(conv_from(val))

    return bc
