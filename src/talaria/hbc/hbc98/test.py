from talaria import hbc as hbcl, tasm
from .translator import assemble, disassemble
import unittest
import pathlib
import json

basepath = pathlib.Path(__file__).parent.absolute()


class TestHBC98(unittest.TestCase):
    def __init__(self, *args, **kwargs):
        super(TestHBC98, self).__init__(*args, **kwargs)
        self.hbc = hbcl.load(open(f"{basepath}/example/index.android.bundle", "rb"))

    def test_header_version(self):
        self.assertEqual(self.hbc.getVersion(), 98)
        self.assertEqual(self.hbc.getHeader()["version"], 98)
        self.assertEqual(self.hbc.getHeader()["bigIntCount"], 1)

    def test_get_function(self):
        functionCount = self.hbc.getFunctionCount()
        self.assertEqual(functionCount, 5)

        for i in range(functionCount):
            try:
                _, paramCount, registerCount, symbolCount, insts, funcHeader = self.hbc.getFunction(
                    i
                )
            except AssertionError:
                self.fail()

            self.assertGreaterEqual(paramCount, 0)
            self.assertGreaterEqual(registerCount, 0)
            self.assertGreaterEqual(symbolCount, 0)
            self.assertGreater(len(insts), 0)
            self.assertIn("loopDepth", funcHeader)

    def test_translator(self):
        functionCount = self.hbc.getFunctionCount()

        for i in range(functionCount):
            _, _, _, _, bc, _ = self.hbc.getFunction(i, disasm=False)

            self.assertEqual(assemble(disassemble(bc)), bc)


class TestParser98(unittest.TestCase):
    def test_hbc(self):
        f = open(f"{basepath}/example/index.android.bundle", "rb")
        hbc = hbcl.load(f)
        f.close()
        f = open("/tmp/talaria_hbc98_test.android.bundle", "wb")
        hbcl.dump(hbc, f)
        f.close()

        f = open(f"{basepath}/example/index.android.bundle", "rb")
        a = f.read()
        f.close()
        f = open("/tmp/talaria_hbc98_test.android.bundle", "rb")
        b = f.read()
        f.close()

        self.assertEqual(a, b)

    def test_tasm(self):
        f = open(f"{basepath}/example/index.android.bundle", "rb")
        a = hbcl.load(f)
        f.close()
        tasm.dump(a, "/tmp/talaria_hbc98_test", force=True)
        b = tasm.load("/tmp/talaria_hbc98_test")

        self.assertEqual(json.dumps(a.getObj()), json.dumps(b.getObj()))
