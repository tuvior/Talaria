import pathlib
from talaria.hbc.generic import GenericParser, INVALID_LENGTH

basepath = pathlib.Path(__file__).parent.absolute()
_parser = GenericParser(basepath)


def parse(f):
    return _parser.parse(f)


def export(obj, f):
    return _parser.export(obj, f)
