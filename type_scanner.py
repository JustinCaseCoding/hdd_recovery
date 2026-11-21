#!/usr/bin/env python3
# type_scanner.py - scan a (partial) raw image for common file signatures.
# usage: python3 type_scanner.py <image> [maxGB]
# gives a quick picture of what file types are recoverable from a rescued
# disk image without mounting it. read-only.
import os, sys, collections

if len(sys.argv) < 2:
    print("usage: %s <image> [maxGB]" % sys.argv[0], flush=True)
    sys.exit(1)

path = sys.argv[1]
maxgb = float(sys.argv[2]) if len(sys.argv) > 2 else 4.0
size = os.path.getsize(path)
end = min(size, int(maxgb * 1024**3))
print("image size: %.2f GB, scanning up to %.1f GB" % (size / 1e9, end / 1e9), flush=True)

sig = [
    (b"\xff\xd8\xff", ".jpg"),
    (b"\x89PNG\r\n\x1a\n", ".png"),
    (b"GIF8", ".gif"),
    (b"%PDF", ".pdf"),
    (b"PK\x03\x04", ".zip/office"),
    (b"ID3", ".mp3"),
    (b"\xff\xfb", ".mp3"),
    (b"\x00\x00\x00\x18ftyp", ".mp4"),
    (b"\x00\x00\x00 ftyp", ".mp4"),
    (b"BM", ".bmp"),
    (b"II*\x00", ".tif"),
    (b"MM\x00*", ".tif"),
    (b"\x1aE\xdf\xa3", ".mkv"),
    (b"RIFF", ".wav/avi"),
]
counts = collections.Counter()
off = 0
CH = 4 * 1024 * 1024
while off < end:
    f = os.open(path, os.O_RDONLY)
    try:
        data = os.pread(f, CH, off)
    finally:
        os.close(f)
    if not data:
        break
    k = 0
    while k < len(data) - 8:
        hit = next((e for s, e in sig if data.startswith(s, k)), None)
        if hit:
            counts[hit] += 1
            k += 4096          # skip past the file once found
        else:
            k += 64            # coarse stride while scanning
    off += CH
    if off % (256 * 1024 * 1024) == 0:
        print("  ...%.1f GB scanned, hits: %d" % (off / 1e9, sum(counts.values())), flush=True)

print("result:", flush=True)
for ext, n in counts.most_common():
    print("  %-10s %d" % (ext, n), flush=True)
print("total signature hits: %d" % sum(counts.values()), flush=True)
