import copy
import json
import pathlib
from struct import unpack
from typing import Any

from talaria.util import memcpy, read, readuint, write, writeuint

BYTECODE_ALIGNMENT = 4
INVALID_LENGTH = (1 << 8) - 1

NullTag = 0
TrueTag = 1 << 4
FalseTag = 2 << 4
NumberTag = 3 << 4
LongStringTag = 4 << 4
ShortStringTag = 5 << 4
ByteStringTag = 6 << 4
IntegerTag = 7 << 4
TagMask = 0x70


class GenericParser:
    def __init__(self, basepath):
        self.basepath = pathlib.Path(basepath)
        self.structure = json.loads((self.basepath / "data" / "structure.json").read_text())

    def align(self, f):
        f.pad(BYTECODE_ALIGNMENT)

    def _read_record(self, f, spec):
        record = {}
        for key in spec:
            record[key] = read(f, spec[key])
        return record

    def _write_record(self, f, record, spec):
        for key in spec:
            write(f, record[key], spec[key])

    def _read_record_array(self, f, count, spec):
        return [self._read_record(f, spec) for _ in range(count)]

    def _write_record_array(self, f, records, count, spec):
        for i in range(count):
            self._write_record(f, records[i], spec)

    def _large_header_offset(self, function_header):
        if "loopDepth" in function_header:
            return (function_header["functionName"] << 24) | function_header["offset"]
        return (function_header["infoOffset"] << 16) | function_header["offset"]

    def parse(self, f):
        s = self.structure
        obj = {}

        header = self._read_record(f, s["header"])
        obj["header"] = header
        self.align(f)

        function_headers = []
        for _ in range(header["functionCount"]):
            function_header = self._read_record(f, s["SmallFuncHeader"])
            if (function_header["flags"] >> 5) & 1:
                function_header["small"] = copy.deepcopy(function_header)
                saved_pos = f.tell()
                f.seek(self._large_header_offset(function_header))
                function_header.update(self._read_record(f, s["FuncHeader"]))
                f.seek(saved_pos)
            function_headers.append(function_header)

        obj["functionHeaders"] = function_headers
        self.align(f)

        obj["stringKinds"] = [readuint(f, bits=32) for _ in range(header["stringKindCount"])]
        self.align(f)

        obj["identifierHashes"] = [readuint(f, bits=32) for _ in range(header["identifierCount"])]
        self.align(f)

        obj["stringTableEntries"] = self._read_record_array(
            f, header["stringCount"], s["SmallStringTableEntry"]
        )
        self.align(f)

        obj["stringTableOverflowEntries"] = self._read_record_array(
            f, header["overflowStringCount"], s["OverflowStringTableEntry"]
        )
        self.align(f)

        string_storage_s = s["StringStorage"]
        string_storage_s[2] = header["stringStorageSize"]
        obj["stringStorage"] = read(f, string_storage_s)
        self.align(f)

        if "LiteralValueBuffer" in s:
            literal_s = s["LiteralValueBuffer"]
            literal_s[2] = header["literalValueBufferSize"]
            obj["literalValueBuffer"] = read(f, literal_s)
            self.align(f)
        else:
            array_s = s["ArrayBuffer"]
            array_s[2] = header["arrayBufferSize"]
            obj["arrayBuffer"] = read(f, array_s)
            self.align(f)

        obj_key_s = s["ObjKeyBuffer"]
        obj_key_s[2] = header["objKeyBufferSize"]
        obj["objKeyBuffer"] = read(f, obj_key_s)
        self.align(f)

        if "ObjShapeTableEntry" in s:
            obj["objShapeTable"] = self._read_record_array(
                f, header["objShapeTableCount"], s["ObjShapeTableEntry"]
            )
            self.align(f)
        else:
            obj_value_s = s["ObjValueBuffer"]
            obj_value_s[2] = header["objValueBufferSize"]
            obj["objValueBuffer"] = read(f, obj_value_s)
            self.align(f)

        if "BigIntTableEntry" in s:
            obj["bigIntTable"] = self._read_record_array(
                f, header["bigIntCount"], s["BigIntTableEntry"]
            )
            self.align(f)

            big_int_storage_s = s["BigIntStorage"]
            big_int_storage_s[2] = header["bigIntStorageSize"]
            obj["bigIntStorage"] = read(f, big_int_storage_s)
            self.align(f)

        obj["regExpTable"] = self._read_record_array(
            f, header["regExpCount"], s["RegExpTableEntry"]
        )
        self.align(f)

        regexp_storage_s = s["RegExpStorage"]
        regexp_storage_s[2] = header["regExpStorageSize"]
        obj["regExpStorage"] = read(f, regexp_storage_s)
        self.align(f)

        obj["cjsModuleTable"] = self._read_record_array(
            f, header["cjsModuleCount"], s["CJSModuleTable"]
        )
        self.align(f)

        if "FunctionSourceTable" in s:
            obj["funSourceTable"] = self._read_record_array(
                f, header["functionSourceCount"], s["FunctionSourceTable"]
            )
            self.align(f)

        obj["instOffset"] = f.tell()
        obj["inst"] = f.readall()
        return obj

    def export(self, obj, f):
        s = self.structure
        header = obj["header"]

        self._write_record(f, header, s["header"])
        self.align(f)

        overflowed_function_headers = []
        for i in range(header["functionCount"]):
            function_header = obj["functionHeaders"][i]
            if "small" in function_header:
                self._write_record(f, function_header["small"], s["SmallFuncHeader"])
                overflowed_function_headers.append(function_header)
            else:
                self._write_record(f, function_header, s["SmallFuncHeader"])
        self.align(f)

        for i in range(header["stringKindCount"]):
            writeuint(f, obj["stringKinds"][i], bits=32)
        self.align(f)

        for i in range(header["identifierCount"]):
            writeuint(f, obj["identifierHashes"][i], bits=32)
        self.align(f)

        self._write_record_array(
            f, obj["stringTableEntries"], header["stringCount"], s["SmallStringTableEntry"]
        )
        self.align(f)

        self._write_record_array(
            f,
            obj["stringTableOverflowEntries"],
            header["overflowStringCount"],
            s["OverflowStringTableEntry"],
        )
        self.align(f)

        string_storage_s = s["StringStorage"]
        string_storage_s[2] = header["stringStorageSize"]
        write(f, obj["stringStorage"], string_storage_s)
        self.align(f)

        if "LiteralValueBuffer" in s:
            literal_s = s["LiteralValueBuffer"]
            literal_s[2] = header["literalValueBufferSize"]
            write(f, obj["literalValueBuffer"], literal_s)
            self.align(f)
        else:
            array_s = s["ArrayBuffer"]
            array_s[2] = header["arrayBufferSize"]
            write(f, obj["arrayBuffer"], array_s)
            self.align(f)

        obj_key_s = s["ObjKeyBuffer"]
        obj_key_s[2] = header["objKeyBufferSize"]
        write(f, obj["objKeyBuffer"], obj_key_s)
        self.align(f)

        if "ObjShapeTableEntry" in s:
            self._write_record_array(
                f, obj["objShapeTable"], header["objShapeTableCount"], s["ObjShapeTableEntry"]
            )
            self.align(f)
        else:
            obj_value_s = s["ObjValueBuffer"]
            obj_value_s[2] = header["objValueBufferSize"]
            write(f, obj["objValueBuffer"], obj_value_s)
            self.align(f)

        if "BigIntTableEntry" in s:
            self._write_record_array(
                f, obj["bigIntTable"], header["bigIntCount"], s["BigIntTableEntry"]
            )
            self.align(f)

            big_int_storage_s = s["BigIntStorage"]
            big_int_storage_s[2] = header["bigIntStorageSize"]
            write(f, obj["bigIntStorage"], big_int_storage_s)
            self.align(f)

        self._write_record_array(
            f, obj["regExpTable"], header["regExpCount"], s["RegExpTableEntry"]
        )
        self.align(f)

        regexp_storage_s = s["RegExpStorage"]
        regexp_storage_s[2] = header["regExpStorageSize"]
        write(f, obj["regExpStorage"], regexp_storage_s)
        self.align(f)

        self._write_record_array(
            f, obj["cjsModuleTable"], header["cjsModuleCount"], s["CJSModuleTable"]
        )
        self.align(f)

        if "FunctionSourceTable" in s:
            self._write_record_array(
                f,
                obj["funSourceTable"],
                header["functionSourceCount"],
                s["FunctionSourceTable"],
            )
            self.align(f)

        f.writeall(obj["inst"])

        for overflowed_function_header in overflowed_function_headers:
            small_function_header = overflowed_function_header["small"]
            f.seek(self._large_header_offset(small_function_header))
            self._write_record(f, overflowed_function_header, s["FuncHeader"])


class GenericHBC:
    version = None
    parser = None
    disassemble_func = None
    assemble_func = None

    def __init__(self, f=None):
        self.obj = self.parser.parse(f) if f else None

    def export(self, f) -> None:
        self.parser.export(self.getObj(), f)

    def getObj(self) -> dict[str, Any]:
        if self.obj is None:
            raise RuntimeError("HBC object is not set")
        return self.obj

    def setObj(self, obj: dict[str, Any]) -> None:
        self.obj = obj

    def getVersion(self) -> int:
        return self.version

    def getHeader(self) -> dict[str, Any]:
        return self.getObj()["header"]

    def getFunctionCount(self) -> int:
        return self.getObj()["header"]["functionCount"]

    @staticmethod
    def _check_index(index: int, count: int, label: str) -> None:
        if index < 0 or index >= count:
            raise IndexError(f"Invalid {label} ID: {index} (expected 0..{count - 1})")

    def _function_symbol_count(self, function_header):
        return function_header.get("environmentSize", function_header.get("loopDepth", 0))

    def _set_function_symbol_count(self, function_header, value):
        if "environmentSize" in function_header:
            function_header["environmentSize"] = value
        elif "loopDepth" in function_header:
            function_header["loopDepth"] = value

    def getFunction(self, fid: int, disasm: bool = True):
        self._check_index(fid, self.getFunctionCount(), "function")

        function_header = self.getObj()["functionHeaders"][fid]
        offset = function_header["offset"]
        param_count = function_header["paramCount"]
        register_count = function_header["frameSize"]
        symbol_count = self._function_symbol_count(function_header)
        bytecode_size = function_header["bytecodeSizeInBytes"]
        function_name = function_header["functionName"]

        inst_offset = self.getObj()["instOffset"]
        start = offset - inst_offset
        end = start + bytecode_size
        bc = self.getObj()["inst"][start:end]
        insts = self.disassemble_func(bc) if disasm else bc

        function_name_str, _ = self.getString(function_name)
        return (
            function_name_str,
            param_count,
            register_count,
            symbol_count,
            insts,
            function_header,
        )

    def setFunction(self, fid: int, func, disasm: bool = True) -> None:
        self._check_index(fid, self.getFunctionCount(), "function")

        _, param_count, register_count, symbol_count, insts, _ = func
        function_header = self.getObj()["functionHeaders"][fid]
        function_header["paramCount"] = param_count
        function_header["frameSize"] = register_count
        self._set_function_symbol_count(function_header, symbol_count)

        offset = function_header["offset"]
        bytecode_size = function_header["bytecodeSizeInBytes"]
        inst_offset = self.getObj()["instOffset"]
        start = offset - inst_offset

        bc = self.assemble_func(insts) if disasm else insts
        if len(bc) > bytecode_size:
            raise ValueError("Overflowed instruction length is not supported yet")
        function_header["bytecodeSizeInBytes"] = len(bc)
        memcpy(self.getObj()["inst"], bc, start, len(bc))

    def getStringCount(self) -> int:
        return self.getObj()["header"]["stringCount"]

    def getString(self, sid: int):
        self._check_index(sid, self.getStringCount(), "string")

        string_table_entry = self.getObj()["stringTableEntries"][sid]
        string_storage = self.getObj()["stringStorage"]
        string_table_overflow_entries = self.getObj()["stringTableOverflowEntries"]

        is_utf16 = string_table_entry["isUTF16"]
        offset = string_table_entry["offset"]
        length = string_table_entry["length"]

        if length >= INVALID_LENGTH:
            string_table_overflow_entry = string_table_overflow_entries[offset]
            offset = string_table_overflow_entry["offset"]
            length = string_table_overflow_entry["length"]

        byte_length = length * 2 if is_utf16 else length
        s = bytes(string_storage[offset : offset + byte_length])
        return s.hex() if is_utf16 else s.decode("utf-8"), (is_utf16, offset, byte_length)

    def setString(self, sid: int, val: str) -> None:
        self._check_index(sid, self.getStringCount(), "string")

        string_table_entry = self.getObj()["stringTableEntries"][sid]
        string_storage = self.getObj()["stringStorage"]
        string_table_overflow_entries = self.getObj()["stringTableOverflowEntries"]

        is_utf16 = string_table_entry["isUTF16"]
        offset = string_table_entry["offset"]
        length = string_table_entry["length"]

        if length >= INVALID_LENGTH:
            string_table_overflow_entry = string_table_overflow_entries[offset]
            offset = string_table_overflow_entry["offset"]
            length = string_table_overflow_entry["length"]

        if is_utf16:
            s = list(bytes.fromhex(val))
            logical_length = len(s) // 2
        else:
            s = val.encode("utf-8")
            logical_length = len(s)

        if logical_length > length:
            raise ValueError("Overflowed string length is not supported yet")
        byte_capacity = length * 2 if is_utf16 else length
        memcpy(string_storage, list(s) + [0] * (byte_capacity - len(s)), offset, byte_capacity)

    def _literal_buffer_name(self):
        return "literalValueBuffer" if "literalValueBuffer" in self.getObj() else "arrayBuffer"

    def _obj_value_buffer_name(self):
        return "literalValueBuffer" if "literalValueBuffer" in self.getObj() else "objValueBuffer"

    def _checkBufferTag(self, buf, iid):
        key_tag = buf[iid]
        if key_tag & 0x80:
            return (((key_tag & 0x0F) << 8) | (buf[iid + 1]), key_tag & TagMask)
        return (key_tag & 0x0F, key_tag & TagMask)

    def _SLPToString(self, tag, buf, iid, ind):
        start = iid + ind
        if tag == ByteStringTag:
            value_type = "String"
            val = buf[start]
            ind += 1
        elif tag == ShortStringTag:
            value_type = "String"
            val = unpack("<H", bytes(buf[start : start + 2]))[0]
            ind += 2
        elif tag == LongStringTag:
            value_type = "String"
            val = unpack("<L", bytes(buf[start : start + 4]))[0]
            ind += 4
        elif tag == NumberTag:
            value_type = "Number"
            val = unpack("<d", bytes(buf[start : start + 8]))[0]
            ind += 8
        elif tag == IntegerTag:
            value_type = "Integer"
            val = unpack("<L", bytes(buf[start : start + 4]))[0]
            ind += 4
        elif tag == NullTag:
            value_type = "Null"
            val = None
        elif tag == TrueTag:
            value_type = "Boolean"
            val = True
        elif tag == FalseTag:
            value_type = "Boolean"
            val = False
        else:
            value_type = "Empty"
            val = None
        return value_type, val, ind

    def getArrayBufferSize(self) -> int:
        header = self.getObj()["header"]
        return header.get("literalValueBufferSize", header.get("arrayBufferSize"))

    def getArray(self, aid: int):
        self._check_index(aid, self.getArrayBufferSize(), "array")
        buf = self.getObj()[self._literal_buffer_name()]
        tag = self._checkBufferTag(buf, aid)
        ind = 2 if tag[0] > 0x0F else 1
        arr = []
        value_type = None
        for _ in range(tag[0]):
            value_type, val, ind = self._SLPToString(tag[1], buf, aid, ind)
            arr.append(val)
        return value_type, arr

    def getObjKeyBufferSize(self) -> int:
        return self.getObj()["header"]["objKeyBufferSize"]

    def getObjKey(self, kid: int):
        self._check_index(kid, self.getObjKeyBufferSize(), "object key")
        buf = self.getObj()["objKeyBuffer"]
        tag = self._checkBufferTag(buf, kid)
        ind = 2 if tag[0] > 0x0F else 1
        keys = []
        value_type = None
        for _ in range(tag[0]):
            value_type, val, ind = self._SLPToString(tag[1], buf, kid, ind)
            keys.append(val)
        return value_type, keys

    def getObjValueBufferSize(self) -> int:
        header = self.getObj()["header"]
        return header.get("literalValueBufferSize", header.get("objValueBufferSize"))

    def getObjValue(self, vid: int):
        self._check_index(vid, self.getObjValueBufferSize(), "object value")
        buf = self.getObj()[self._obj_value_buffer_name()]
        tag = self._checkBufferTag(buf, vid)
        ind = 2 if tag[0] > 0x0F else 1
        values = []
        value_type = None
        for _ in range(tag[0]):
            value_type, val, ind = self._SLPToString(tag[1], buf, vid, ind)
            values.append(val)
        return value_type, values


def make_hbc_class(version, parser, disassemble_func, assemble_func):
    return type(
        f"HBC{version}",
        (GenericHBC,),
        {
            "version": version,
            "parser": parser,
            "disassemble_func": staticmethod(disassemble_func),
            "assemble_func": staticmethod(assemble_func),
        },
    )
