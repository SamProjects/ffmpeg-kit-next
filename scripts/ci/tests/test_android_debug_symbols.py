import contextlib
import importlib.util
import io
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile


spec = importlib.util.spec_from_file_location(
    "package_symbols", Path(__file__).resolve().parents[1] / "package-android-debug-symbols.py")
symbols = importlib.util.module_from_spec(spec)
spec.loader.exec_module(symbols)


class AndroidDebugSymbolsTest(unittest.TestCase):
    """Exercise real ELF stripping/repackaging; the runner must be Linux x86_64."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.native = self.root / "obj" / "x86_64"
        self.native.mkdir(parents=True)
        self.library = self.native / "libexample.so"
        self.aar = self.root / "example.aar"
        self.output = self.root / "symbols.zip"
        self.compile(self.library)
        stripped = self.root / "stripped.so"
        subprocess.run(["objcopy", "--strip-unneeded", self.library, stripped], check=True)
        with zipfile.ZipFile(self.aar, "w", zipfile.ZIP_DEFLATED) as aar:
            aar.writestr("AndroidManifest.xml", b"manifest unchanged")
            aar.writestr("classes.jar", b"classes unchanged")
            aar.write(stripped, "jni/x86_64/libexample.so")
        self.original_aar = self.aar.read_bytes()

    def compile(self, destination, value=1, build_id=True):
        source = self.root / "example.c"
        source.write_text(f"int example(int n) {{ int result = n + {value}; return result; }}\n")
        subprocess.run(["cc", "-shared", "-fPIC", "-g", "-O2",
                        "-Wl,--build-id=sha1" if build_id else "-Wl,--build-id=none",
                        source, "-o", destination], check=True)

    def package(self, abis=None):
        with contextlib.redirect_stdout(io.StringIO()):
            symbols.package(self.aar, self.root / "obj", abis or ["x86_64"], self.output)

    def assert_rejected(self, message, abis=None):
        with self.assertRaisesRegex(ValueError, message):
            self.package(abis)
        self.assertEqual(self.aar.read_bytes(), self.original_aar)
        self.assertFalse(self.output.exists())

    def test_packages_full_symbols_into_aar_and_play_zip_and_is_repeatable(self):
        self.package()
        with zipfile.ZipFile(self.aar) as aar, zipfile.ZipFile(self.output) as debug:
            self.assertEqual(aar.read("AndroidManifest.xml"), b"manifest unchanged")
            self.assertEqual(aar.read("classes.jar"), b"classes unchanged")
            data = aar.read("jni/x86_64/libexample.so")
            self.assertEqual(data, self.library.read_bytes())
            self.assertEqual(data, debug.read("x86_64/libexample.so"))
            self.assertEqual(debug.namelist(), ["x86_64/libexample.so"])
            _, sections, _, build_id = symbols.inspect_elf(data)
            self.assertTrue(build_id)
            self.assertTrue(sections[".debug_info"][0])
            self.assertTrue(sections[".debug_line"][0])
        self.package()

    def test_rejects_symbols_from_another_build_without_changing_aar(self):
        self.compile(self.library, value=2)
        self.assert_rejected("not the same build")

    def test_rejects_symbol_table_only_instead_of_claiming_full_symbols(self):
        subprocess.run(["objcopy", "--strip-debug", self.library], check=True)
        self.assert_rejected("missing .debug_info")

    def test_rejects_missing_line_information(self):
        subprocess.run(["objcopy", "--remove-section=.debug_line", self.library], check=True)
        self.assert_rejected("missing .debug_line")

    def test_rejects_missing_build_id(self):
        self.compile(self.library, build_id=False)
        self.assert_rejected("missing GNU Build ID")

    def test_rejects_stripped_symbol_table(self):
        subprocess.run(["objcopy", "--strip-unneeded", self.library], check=True)
        self.assert_rejected("missing .symtab")

    def test_rejects_missing_abi(self):
        self.assert_rejected("missing ABI libraries", ["x86_64", "arm64-v8a"])

    def test_rejects_wrong_elf_architecture(self):
        data = bytearray(self.library.read_bytes())
        data[18:20] = (183).to_bytes(2, "little")  # EM_AARCH64 in an x86_64 directory.
        self.library.write_bytes(data)
        self.assert_rejected("architecture does not match ABI")

    def test_rejects_runtime_changes_even_if_build_id_is_preserved(self):
        data = self.library.read_bytes()
        _, sections, _, _ = symbols.inspect_elf(data)
        text = sections[".text"][1]
        offset = data.index(text)
        corrupted = bytearray(data)
        corrupted[offset] ^= 1
        self.library.write_bytes(corrupted)
        self.assert_rejected("not the same build")


if __name__ == "__main__":
    unittest.main()
