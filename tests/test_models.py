from talaria.models import FunctionBody, Instruction, Operand


def test_function_body_converts_hbc_boundary_tuple():
    legacy = (
        "main",
        1,
        2,
        3,
        [("LoadConstUInt8", [("Reg8", False, 0), ("UInt8", False, 7)])],
        {"offset": 12},
    )

    function = FunctionBody.from_hbc_tuple(legacy)

    assert function.name == "main"
    assert function.param_count == 1
    assert function.instructions == (
        Instruction(
            "LoadConstUInt8",
            (Operand("Reg8", False, 0), Operand("UInt8", False, 7)),
        ),
    )
    assert function.to_hbc_tuple() == legacy
