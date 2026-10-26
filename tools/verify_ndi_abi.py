"""Compare ctypes against the ACTUAL official SDK headers. No linking/runtime needed.

Usage: python tools/verify_ndi_abi.py /path/to/official-sdk/include
Requires an existing C++ compiler (CXX or c++). Creates only temporary build files.
"""
import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ndi_sender import NDIlib_send_create_t, NDIlib_video_frame_v2_t, fourcc


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Uso: python tools/verify_ndi_abi.py <SDK/include>")
    include = Path(sys.argv[1]).resolve()
    if not (include / "Processing.NDI.Lib.h").is_file():
        raise SystemExit("No se encuentra Processing.NDI.Lib.h oficial")
    structures = (NDIlib_send_create_t, NDIlib_video_frame_v2_t)
    lines = ['#include <Processing.NDI.Lib.h>', '#include <cstddef>', '#include <iostream>',
             'int main() {']
    expected = {}
    for structure in structures:
        name = structure.__name__
        expected[name + ".size"] = ctypes.sizeof(structure)
        lines.append(f'std::cout << "{name}.size " << sizeof({name}) << "\\n";')
        for field, _ in structure._fields_:
            key = name + "." + field
            expected[key] = getattr(structure, field).offset
            lines.append(f'std::cout << "{key} " << offsetof({name}, {field}) << "\\n";')
    for key, expression, value in (
        ("BGRA", "NDIlib_FourCC_type_BGRA", fourcc(b"BGRA")),
        ("progressive", "NDIlib_frame_format_type_progressive", 1),
        ("synthesize", "NDIlib_send_timecode_synthesize", (1 << 63) - 1),
    ):
        expected[key] = value
        lines.append(f'std::cout << "{key} " << {expression} << "\\n";')
    lines.append('}')
    with tempfile.TemporaryDirectory(prefix="ndi-abi-") as directory:
        source = Path(directory) / "probe.cpp"
        binary = Path(directory) / ("probe.exe" if os.name == "nt" else "probe")
        source.write_text("\n".join(lines), encoding="utf-8")
        subprocess.run([os.environ.get("CXX", "c++"), "-std=c++11", "-I", str(include),
                        str(source), "-o", str(binary)], check=True)
        output = subprocess.check_output([str(binary)], text=True)
    actual = {key: int(value) for key, value in (line.split() for line in output.splitlines())}
    if actual != expected:
        raise SystemExit("ABI incompatible: " + json.dumps({"SDK": actual, "ctypes": expected}))
    print("OK ABI: tamaños, offsets y constantes coinciden con headers oficiales")


if __name__ == "__main__":
    main()
