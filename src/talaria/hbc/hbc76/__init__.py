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
HBC76 = make_hbc_class(76, GenericParser(basepath), disassemble, assemble)
