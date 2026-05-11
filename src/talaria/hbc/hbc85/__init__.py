import pathlib
from talaria.hbc.generic import (
    NullTag,
    TrueTag,
    FalseTag,
    NumberTag,
    LongStringTag,
    ShortStringTag,
    ByteStringTag,
    IntegerTag,
    TagMask,
    INVALID_LENGTH,
    GenericParser,
    make_hbc_class,
)
from .translator import disassemble, assemble

basepath = pathlib.Path(__file__).parent.absolute()
HBC85 = make_hbc_class(85, GenericParser(basepath), disassemble, assemble)
