import math
from contextlib import suppress
from struct import pack, unpack


# File Object
class BitWriter:
    def __init__(self, f):
        self.accumulator = 0
        self.bcount = 0
        self.out = f
        self.write = 0
        self.remained = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.flush()

    def __del__(self):
        with suppress(ValueError):  # I/O operation on closed file.
            self.flush()

    def _writebit(self, bit, remaining=-1):
        if remaining > -1:
            self.accumulator |= bit << (remaining - 1)
        else:
            self.accumulator |= bit << (7 - self.bcount + self.remained)

        self.bcount += 1

        if self.bcount == 8:
            self.flush()

    def _clearbits(self, remaining):
        self.remained = remaining

    def _writebyte(self, b):
        if self.bcount:
            raise RuntimeError("Cannot write a byte while bit buffer is not empty")
        self.out.write(bytes([b]))
        self.write += 1

    def writebits(self, v, n, remained=False):
        i = n
        while i > 0:
            self._writebit((v & (1 << i - 1)) >> (i - 1), remaining=(i if remained else -1))
            i -= 1

        if remained:
            self._clearbits(n)

    def writebytes(self, v, n):
        while n > 0:
            self._writebyte(v & 0xFF)
            v = v >> 8
            n -= 1

        return v

    def flush(self):
        if self.bcount == 0 and self.accumulator == 0 and self.remained == 0:
            return
        self.out.write(bytes([self.accumulator]))
        self.accumulator = 0
        self.bcount = 0
        self.remained = 0
        self.write += 1

    def seek(self, i):
        self.out.seek(i)
        self.write = i

    def tell(self):
        return self.write

    def pad(self, alignment):
        _validate_alignment(alignment)
        offset = self.tell()
        if offset % alignment == 0:
            return

        b = alignment - (offset % alignment)
        self.writeall([0] * (b))

    def writeall(self, bs):
        self.out.write(bytes(bs))
        self.write += len(bs)


class BitReader:
    def __init__(self, f):
        self.input = f
        self.accumulator = 0
        self.bcount = 0
        self.read = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def _readbit(self, remaining=-1):
        if not self.bcount:
            a = self.input.read(1)
            self.read += 1
            if a:
                self.accumulator = ord(a)
            self.bcount = 8

        if remaining > -1:
            if remaining > self.bcount:
                raise ValueError(f"Cannot read {remaining} remaining bits from {self.bcount}")
            return (self.accumulator & (1 << remaining - 1)) >> remaining - 1

        rv = (self.accumulator & (1 << self.bcount - 1)) >> self.bcount - 1
        self.bcount -= 1
        return rv

    def _clearbits(self, remaining):
        self.bcount -= remaining
        self.accumulator = self.accumulator >> remaining

    def _readbyte(self):
        if self.bcount:
            raise RuntimeError("Cannot read a byte while bit buffer is not empty")
        a = self.input.read(1)
        self.read += 1
        if not a:
            raise EOFError("Unexpected end of byte stream")
        return ord(a)

    def readbits(self, n, remained=False):
        v = 0
        i = n
        while i > 0:
            v = (v << 1) | self._readbit(remaining=(i if remained else -1))
            i -= 1

        if remained:
            self._clearbits(n)

        return v

    def readbytes(self, n=1):
        v = 0
        while n > 0:
            v = (v << 8) | self._readbyte()
            n -= 1

        return v

    def seek(self, i):
        self.input.seek(i)
        self.read = i

    def tell(self):
        return self.read

    def pad(self, alignment):
        _validate_alignment(alignment)
        offset = self.tell()
        if offset % alignment == 0:
            return

        b = alignment - (offset % alignment)
        self.seek(offset + b)

    def readall(self):
        a = self.input.read()
        self.read += len(a)
        return list(a)


# File utilization function
# Read
def _validate_alignment(alignment):
    if alignment <= 0 or alignment > 8 or (alignment & (alignment - 1)) != 0:
        raise ValueError("Alignment must be a power of two no larger than 8 bytes")


def readuint(f, bits=64, signed=False):
    if bits % 8 != 0:
        raise ValueError("Integer widths must be byte-aligned")
    if bits == 8:
        return f.readbytes(1)

    x = 0
    s = 0
    for _ in range(bits // 8):
        b = f.readbytes(1)
        x |= (b & 0xFF) << s
        s += 8

    if signed and (x & (1 << (bits - 1))):
        x = -((1 << (bits)) - x)

    if x.bit_length() > bits:
        print(f"--> Int {x} longer than {bits} bits")
    return x


def readint(f, bits=64):
    return readuint(f, bits, signed=True)


def readbits(f, bits=8):
    x = 0
    s = 0

    if f.bcount % 8 != 0 and bits >= f.bcount:
        buffered_bits = f.bcount
        b = f.readbits(buffered_bits)
        x |= (b & 0xFF) << s
        s += buffered_bits
        bits -= buffered_bits

    for _ in range(bits // 8):
        b = f.readbits(8)
        x |= (b & 0xFF) << s
        s += 8

    r = bits % 8
    if r != 0:
        b = f.readbits(r, remained=True)
        x |= (b & ((1 << r) - 1)) << s
        s += r

    return x


def read(f, format):
    data_type = format[0]
    bits = format[1]
    n = format[2]
    r = []
    for _ in range(n):
        if data_type == "uint":
            r.append(readuint(f, bits=bits))
        elif data_type == "int":
            r.append(readint(f, bits=bits))
        elif data_type == "bit":
            r.append(readbits(f, bits=bits))
        else:
            raise ValueError(f"Data type {data_type} is not supported")

    if len(r) == 1:
        return r[0]
    return r


# Write
def writeuint(f, v, bits=64, signed=False):
    if bits % 8 != 0:
        raise ValueError("Integer widths must be byte-aligned")

    if signed:
        v += 1 << bits

    if bits == 8:
        f.writebytes(v, 1)
        return

    s = 0
    for _ in range(bits // 8):
        f.writebytes(v & 0xFF, 1)
        v = v >> 8
        s += 8


def writeint(f, v, bits=64):
    return writeuint(f, v, bits, signed=True)


def writebits(f, v, bits=8):
    s = 0
    if f.bcount % 8 != 0 and bits >= 8 - f.bcount:
        buffered_bits = 8 - f.bcount
        f.writebits(v & ((1 << buffered_bits) - 1), buffered_bits)
        v = v >> buffered_bits
        s += buffered_bits
        bits -= buffered_bits

    for _ in range(bits // 8):
        f.writebits(v & 0xFF, 8)
        v = v >> 8
        s += 8

    r = bits % 8
    if r != 0:
        f.writebits(v & ((1 << bits) - 1), r, remained=True)
        v = v >> r
        s += r


def write(f, v, format):
    t = format[0]
    bits = format[1]
    n = format[2]

    if not isinstance(v, list):
        v = [v]

    for i in range(n):
        if t == "uint":
            writeuint(f, v[i], bits=bits)
        elif t == "int":
            writeint(f, v[i], bits=bits)
        elif t == "bit":
            writebits(f, v[i], bits=bits)
        else:
            raise ValueError(f"Data type {t} is not supported")


# Unpacking
def to_uint8(buf):
    return buf[0]


def to_uint16(buf):
    return unpack("<H", bytes(buf[:2]))[0]


def to_uint32(buf):
    return unpack("<L", bytes(buf[:4]))[0]


def to_int8(buf):
    return unpack("<b", bytes([buf[0]]))[0]


def to_int32(buf):
    return unpack("<i", bytes(buf[:4]))[0]


def to_double(buf):
    # Python doesn't differentiate between NaN and -NaN on unpacking
    b = bytes(buf[:8])
    d = unpack("<d", b)[0]
    if math.isnan(d) and b[7] == 0xFF:
        return "-nan"
    return d


# Packing
def from_uint8(val):
    return [val]


def from_uint16(val):
    return list(pack("<H", val))


def from_uint32(val):
    return list(pack("<L", val))


def from_int8(val):
    return list(pack("<b", val))


def from_int32(val):
    return list(pack("<i", val))


def from_double(val):
    if val == "-nan":
        return list(bytes.fromhex("000000000000f8ff"))
    return list(pack("<d", val))


# Buf Function


def memcpy(dest, src, start, length):
    for offset, value in enumerate(src[:length]):
        dest[start + offset] = value
