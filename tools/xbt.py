"""Read and rewrite Kodi's texture pack (media/Textures.xbt, the XBTF format of Kodi's TextureBundleXBT).

Bald's pack is Estuary's. Kodi looks a texture up in the pack before the loose files in media/, so a texture Bald
draws itself under one of Estuary's names (the toasts' DefaultIconInfo.png, which Kodi names in code) only shows once
the pack no longer has it. This drops named textures from the pack, keeping every other frame byte for byte.

  python3 tools/xbt.py list
  python3 tools/xbt.py drop defaulticoninfo.png defaulticonwarning.png ...

Layout (little-endian): "XBTF", the version ("3" in Kodi 22; "2" is laid out the same), file count (u32); per file a 256-byte path, loop (u32), frame count
(u32) and per frame width, height, format (u32 each), packed size, unpacked size (u64 each), duration (u32) and the
offset of its data from the start of the pack (u64); then the frames' data, identical frames stored once.
"""

import struct
import sys
from pathlib import Path

PACK = Path(__file__).resolve().parents[1] / "media" / "Textures.xbt"
FRAME = struct.Struct("<IIIQQIQ")


def read(path=PACK):
    """(version, [(name, loop, [(width, height, format, unpacked, duration, data)])]) in the pack's order."""
    blob = path.read_bytes()
    if blob[:4] != b"XBTF" or blob[4:5] not in (b"2", b"3"):
        raise ValueError(f"{path} is not an XBTF version 2 or 3 pack")
    (count,) = struct.unpack_from("<I", blob, 5)
    at, files = 9, []
    for _ in range(count):
        name = blob[at:at + 256].split(b"\0", 1)[0].decode("utf-8")
        loop, frames = struct.unpack_from("<II", blob, at + 256)
        at += 264
        found = []
        for _ in range(frames):
            width, height, fmt, packed, unpacked, duration, offset = FRAME.unpack_from(blob, at)
            at += FRAME.size
            found.append((width, height, fmt, unpacked, duration, blob[offset:offset + packed]))
        files.append((name, loop, found))
    return blob[4:5], files


def write(version, files, path=PACK):
    header = 9 + sum(264 + FRAME.size * len(frames) for _, _, frames in files)
    head = bytearray(b"XBTF" + version + struct.pack("<I", len(files)))
    data, placed = bytearray(), {}
    for name, loop, frames in files:
        head += name.encode("utf-8").ljust(256, b"\0") + struct.pack("<II", loop, len(frames))
        for width, height, fmt, unpacked, duration, frame in frames:
            # Identical frames share their data, as Kodi's TexturePacker writes them.
            if frame not in placed:
                placed[frame] = header + len(data)
                data += frame
            head += FRAME.pack(width, height, fmt, len(frame), unpacked, duration, placed[frame])
    path.write_bytes(bytes(head + data))


def drop(names, path=PACK):
    wanted = {name.lower() for name in names}
    version, files = read(path)
    kept = [f for f in files if f[0].lower() not in wanted]
    missing = wanted - {f[0].lower() for f in files}
    if missing:
        raise SystemExit(f"not in the pack: {', '.join(sorted(missing))}")
    write(version, kept, path)
    return len(files) - len(kept)


if __name__ == "__main__":
    if sys.argv[1:2] == ["list"]:
        for name, _, frames in read()[1]:
            print(name, *(f"{w}x{h}" for w, h, *_ in frames))
    elif sys.argv[1:2] == ["drop"] and len(sys.argv) > 2:
        print(f"dropped {drop(sys.argv[2:])}")
    else:
        raise SystemExit(__doc__)
