import hashlib
import importlib
import io
from typing import BinaryIO

from talaria.util import BitReader, BitWriter, read

MAGIC = 2240826417119764422
INIT_HEADER = {"magic": ["uint", 64, 1], "version": ["uint", 32, 1]}
BYTECODE_ALIGNMENT = 4

SUPPORTED_VERSIONS = (59, 62, 74, 76, 84, 85, 90, 94, 96, 98)


def _load_hbc_classes() -> dict[int, type]:
    hbc_classes = {}
    for version in SUPPORTED_VERSIONS:
        module = importlib.import_module(f"talaria.hbc.hbc{version}")
        hbc_classes[version] = getattr(module, f"HBC{version}")
    return hbc_classes


HBC = _load_hbc_classes()


def load(source: BinaryIO):
    data = source.read()
    reader = BitReader(io.BytesIO(data))
    magic = read(reader, INIT_HEADER["magic"])
    version = read(reader, INIT_HEADER["version"])
    reader.seek(0)
    if magic != MAGIC:
        raise ValueError(f"The magic ({hex(magic)}) is invalid. (must be {hex(MAGIC)})")
    if version not in HBC:
        raise ValueError(f"The HBC version ({version}) is not supported.")

    hbco = HBC[version](reader)
    warnings = []
    header = hbco.getHeader()
    file_length = header.get("fileLength")
    if file_length is not None and len(data) < file_length:
        warnings.append(f"File is shorter than header fileLength ({len(data)} < {file_length})")
    elif file_length is not None and len(data) > file_length:
        warnings.append(f"File has {len(data) - file_length} byte(s) after header fileLength")

    if version > 74 and file_length is not None and len(data) >= file_length:
        expected = hashlib.sha1(data[: file_length - 20]).digest()
        actual = data[file_length - 20 : file_length]
        if actual != expected:
            warnings.append("Footer SHA-1 does not match bytecode contents")

    if warnings:
        hbco.getObj()["_validationWarnings"] = warnings

    return hbco


def loado(obj):
    magic = obj["header"]["magic"]
    version = obj["header"]["version"]

    if magic != MAGIC:
        raise ValueError(f"The magic ({hex(magic)}) is invalid. (must be {hex(MAGIC)})")
    if version not in HBC:
        raise ValueError(f"The HBC version ({version}) is not supported.")

    hbco = HBC[version]()
    hbco.setObj(obj)
    return hbco


def dump(hbco, output: BinaryIO) -> None:
    out = io.BytesIO()
    writer = BitWriter(out)
    hbco.export(writer)
    writer.flush()
    data = bytearray(out.getvalue())

    if hbco.getVersion() > 74:
        file_length = hbco.getHeader().get("fileLength")
        if file_length is not None and file_length >= 20 and file_length <= len(data):
            sha1 = hashlib.sha1(data[: file_length - 20]).digest()
            data[file_length - 20 : file_length] = sha1
    output.write(bytes(data))


def dumpo(hbco):
    return hbco.getObj()
