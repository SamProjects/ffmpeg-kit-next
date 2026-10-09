#!/usr/bin/env python3
"""Package same-build, unstripped Android libraries into the AAR and Play ZIP."""

import argparse
import os
from pathlib import Path
import re
import struct
import tempfile
import zipfile


ABI_MACHINES = {"armeabi-v7a": (1, 40), "arm64-v8a": (2, 183),
                "x86": (1, 3), "x86_64": (2, 62)}


def inspect_elf(data):
    if data[:4] != b"\x7fELF" or data[4:6] not in (b"\x01\x01", b"\x02\x01"):
        raise ValueError("expected a little-endian ELF32 or ELF64 library")
    elf_class = data[4]
    header = struct.unpack_from("<" + ("HHIIIIIHHHHHH" if elf_class == 1
                                      else "HHIQQQIHHHHHH"), data, 16)
    if header[0] != 3:
        raise ValueError("expected an ELF shared library")
    section_offset, entry_size, count, name_index = (header[5], header[10],
                                                    header[11], header[12])
    section_format = "<" + ("IIIIIIIIII" if elf_class == 1 else "IIQQQQIIQQ")
    if not count or entry_size != struct.calcsize(section_format):
        raise ValueError("missing or unsupported ELF section headers")
    headers = [struct.unpack_from(section_format, data, section_offset + i * entry_size)
               for i in range(count)]
    names_header = headers[name_index]
    names = data[names_header[4]:names_header[4] + names_header[5]]
    sections = {}
    allocated = {}
    for h in headers:
        name = names[h[0]:].split(b"\0", 1)[0].decode("ascii")
        content = data[h[4]:h[4] + h[5]] if h[1] != 8 else b""
        if h[1] != 8 and len(content) != h[5]:
            raise ValueError(f"truncated ELF section {name}")
        sections[name] = (h[5], content)
        if h[2] & 2:  # SHF_ALLOC: includes code, relocations, dynamic symbols and BSS.
            allocated[name] = (h[1], h[2], h[3], h[5], content)

    build_id = None
    note = sections.get(".note.gnu.build-id", (0, b""))[1]
    offset = 0
    while offset < len(note):
        name_size, desc_size, note_type = struct.unpack_from("<III", note, offset)
        offset += 12
        owner = note[offset:offset + name_size]
        offset += (name_size + 3) & ~3
        descriptor = note[offset:offset + desc_size]
        offset += (desc_size + 3) & ~3
        if owner == b"GNU\0" and note_type == 3 and desc_size:
            if len(descriptor) != desc_size:
                raise ValueError("truncated GNU Build ID")
            build_id = descriptor.hex()
    if not build_id:
        raise ValueError("missing GNU Build ID; rebuild with -Wl,--build-id=sha1")
    return (elf_class, header[1], header[6]), sections, allocated, build_id


def package(aar_path, native_root, abis, symbols_zip):
    native_root = native_root.resolve()
    if not abis or len(set(abis)) != len(abis) or not set(abis) <= ABI_MACHINES.keys():
        raise ValueError("expected a unique list of supported Android ABIs")
    replacements = {}
    with zipfile.ZipFile(aar_path) as aar:
        if len(aar.namelist()) != len(set(aar.namelist())):
            raise ValueError("duplicate entries in AAR")
        found_abis = set()
        for entry in aar.infolist():
            if not entry.filename.startswith("jni/") or not entry.filename.endswith(".so"):
                continue
            match = re.fullmatch(r"jni/([^/]+)/([^/]+\.so)", entry.filename)
            if not match or match[1] not in abis:
                raise ValueError(f"unexpected JNI library {entry.filename}")
            abi, library = match.groups()
            found_abis.add(abi)
            source = (native_root / abi / library).resolve()
            if not source.is_relative_to(native_root):
                raise ValueError(f"library escapes native output directory: {source}")
            unstripped = source.read_bytes()
            try:
                identity, sections, allocated, build_id = inspect_elf(unstripped)
            except ValueError as error:
                raise ValueError(f"{abi}/{library}: native output: {error}") from error
            if identity[:2] != ABI_MACHINES[abi]:
                raise ValueError(f"{abi}/{library}: ELF architecture does not match ABI")
            # No silent downgrade to SYMBOL_TABLE, including for prebuilt dependencies.
            for section in (".symtab", ".debug_info", ".debug_line"):
                if not sections.get(section, (0, b""))[0]:
                    raise ValueError(f"{abi}/{library}: missing {section}; FULL symbols required")
            try:
                old_identity, _, old_allocated, old_build_id = inspect_elf(aar.read(entry))
            except ValueError as error:
                raise ValueError(f"{abi}/{library}: AAR: {error}") from error
            if identity != old_identity or build_id != old_build_id or allocated != old_allocated:
                raise ValueError(f"{abi}/{library}: AAR and native output are not the same build")
            replacements[entry.filename] = unstripped
            print(f"{abi}/{library}: FULL symbols, Build ID {build_id}")
        if found_abis != set(abis):
            raise ValueError(f"missing ABI libraries: {sorted(set(abis) - found_abis)}")

        # Validate every library before touching either output, then replace the AAR atomically.
        symbols_zip.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=aar_path.parent) as temporary:
            staged_aar = Path(temporary) / "unstripped.aar"
            staged_symbols = Path(temporary) / "symbols.zip"
            with zipfile.ZipFile(staged_aar, "w") as output:
                for entry in aar.infolist():
                    data = (replacements[entry.filename] if entry.filename in replacements
                            else aar.read(entry))
                    output.writestr(entry, data)
            with zipfile.ZipFile(staged_symbols, "w", zipfile.ZIP_DEFLATED) as output:
                for name, data in sorted(replacements.items()):
                    output.writestr(name.removeprefix("jni/"), data)
            with zipfile.ZipFile(staged_aar) as output:
                if output.testzip() is not None:
                    raise ValueError("invalid repackaged AAR")
            # symbols_zip may live on another filesystem (e.g. RUNNER_TEMP).
            with tempfile.NamedTemporaryFile(dir=symbols_zip.parent, delete=False) as output:
                symbols_temp = Path(output.name)
                try:
                    output.write(staged_symbols.read_bytes())
                except BaseException:
                    symbols_temp.unlink()
                    raise
            try:
                os.replace(staged_aar, aar_path)
                os.replace(symbols_temp, symbols_zip)
            finally:
                symbols_temp.unlink(missing_ok=True)
    print(f"Packaged {len(replacements)} unstripped libraries into {aar_path} and {symbols_zip}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aar", required=True, type=Path)
    parser.add_argument("--native-root", required=True, type=Path)
    parser.add_argument("--abis", required=True, nargs="+")
    parser.add_argument("--symbols-zip", required=True, type=Path)
    args = parser.parse_args()
    try:
        package(args.aar, args.native_root, args.abis, args.symbols_zip)
    except (ValueError, OSError, struct.error, IndexError, zipfile.BadZipFile) as error:
        parser.exit(1, f"ERROR: {error}\n")


if __name__ == "__main__":
    main()
