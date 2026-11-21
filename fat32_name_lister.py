#!/usr/bin/env python3
# fat32_name_lister.py - read-only FAT32 file/dir name lister for a damaged
# boot sector.
# usage: python3 fat32_name_lister.py <device-or-image> > listing.txt
#
# Strategy (in order):
#  1) locate a boot sector copy (primary / backup / injected) -> walk via FAT
#  2) else: reconstruct geometry from the FAT32 FAT-start signature and walk
#  3) else: quick file-TYPE sampling (no names) + clear message.
# Never writes to the source; works on block devices and image files alike.
import os, sys, struct, collections

if len(sys.argv) < 2:
    print("usage: %s <device-or-image>" % sys.argv[0], flush=True)
    sys.exit(1)

dev = sys.argv[1]
try:
    fd = os.open(dev, os.O_RDONLY)
except OSError as e:
    print("cannot open %s: %s" % (dev, e), flush=True)
    sys.exit(1)
BS = 512

def rd(off, size):
    out = b""
    while len(out) < size:
        try:
            chunk = os.pread(fd, size - len(out), off + len(out))
        except OSError:
            return None
        if not chunk:
            return None
        out += chunk
    return out

def parse_bootsec(s):
    if not s or len(s) < 512 or s[510:512] != b"\x55\xaa" or s[0] not in (0xEB, 0xE9):
        return None
    bps = struct.unpack_from("<H", s, 11)[0]
    spc = s[13]
    rsv = struct.unpack_from("<H", s, 14)[0]
    nfat = s[16]
    fatsz = struct.unpack_from("<I", s, 36)[0]
    total = struct.unpack_from("<I", s, 32)[0]
    rootcl = struct.unpack_from("<I", s, 44)[0]
    if bps in (512, 1024, 2048, 4096) and spc and f"{spc:b}".count("1") == 1 \
       and 1 <= rsv <= 128 and 1 <= nfat <= 4 and fatsz > 10 and rootcl >= 2 \
       and total > fatsz:
        return dict(bps=bps, spc=spc, rsv=rsv, nfat=nfat, fatsz=fatsz,
                    total=total, rootcl=rootcl)
    return None

# -- 1. boot sector copies -----------------------------------------------------
geo = None
for i in (0, 1, 6, 11, 12, 13, 16, 32, 48, 64, 96, 128, 256, 512, 1024, 2048):
    g = parse_bootsec(rd(i * BS, BS))
    if g:
        geo = g
        print("# boot sector copy at sector %d" % i, flush=True)
        break
if geo:
    print("# geometry bps=%d spc=%d rsv=%d nfat=%d fatsz=%d rootcl=%d" % (
        geo["bps"], geo["spc"], geo["rsv"], geo["nfat"], geo["fatsz"], geo["rootcl"]), flush=True)

def tree_entries(fat, csize, data_off, rootcl):
    """walk the dir tree; returns (entries[(type,size,path)], ext-counter, total)"""
    def nxt(cl):
        b = fat[cl * 4: cl * 4 + 4]
        if len(b) < 4:
            return None
        v = struct.unpack("<I", b)[0] & 0x0FFFFFFF
        return None if v >= 0x0FFFFFF8 else v
    entries = []
    names = collections.defaultdict(int)
    total = 0
    seen = set()
    def parse(cl, path, depth):
        nonlocal total
        if depth > 14 or len(entries) > 300000 or cl in seen or cl is None:
            return
        seen.add(cl)
        while cl is not None:
            data = rd(data_off + (cl - 2) * csize, csize)
            if data is None:
                return
            ne, lfn = 0, {}
            while ne + 32 <= len(data):
                e = data[ne:ne + 32]
                ne += 32
                attr = e[11]
                if e[0] == 0x00:
                    return
                if e[0] == 0xE5 or (attr & 0x08):   # deleted / volume label
                    lfn = {}
                    continue
                if attr == 0x0F:                     # long filename part
                    if e[0] & 0x40:
                        lfn = {}
                    raw = e[1:11] + e[14:26] + e[28:32]
                    lfn[e[0] & 0x1F] = raw.decode("utf-16-le", "replace").split("\x00")[0]
                    continue
                if lfn:
                    name = "".join(lfn[k] for k in sorted(lfn)); lfn = {}
                else:
                    n8 = e[0:8].decode("cp850", "replace").strip()
                    x3 = e[8:11].decode("cp850", "replace").strip()
                    name = n8 + ("." + x3 if x3 else "")
                if e[0:11].decode("cp850", "replace").strip() in (".", ".."):
                    continue
                size = struct.unpack("<I", e[28:32])[0]
                fcl = struct.unpack("<H", e[26:28])[0] | (struct.unpack("<H", e[20:22])[0] << 16)
                if attr & 0x10:
                    entries.append(("dir", 0, path + name + "/"))
                    parse(fcl, path + name + "/", depth + 1)
                else:
                    ext = name.rsplit(".", 1)[-1].lower() if "." in name else "?"
                    names[ext] += 1
                    total += size
                    entries.append(("file", size, path + name))
            cl = nxt(cl)
    parse(rootcl, "/", 0)
    return (entries, names, total)

def print_tree(res):
    entries, names, total = res
    files = sum(1 for t, _, _ in entries if t == "file")
    dirs = len(entries) - files
    print("# files: %d  dirs: %d  total size: %.1f GB" % (
        files, dirs, total / 1e9), flush=True)
    print("# top extensions:", flush=True)
    for ext, n in sorted(names.items(), key=lambda x: -x[1])[:15]:
        print("#   .%-8s %d" % (ext, n), flush=True)
    print("# --- listing ---", flush=True)
    for t, s, p in entries:
        print("%s\t%d\t%s" % (t, s, p), flush=True)

# -- 2. FAT-signature geometry reconstruction ---------------------------------
def find_fats(bound=400 * 1024 * 1024):
    # FAT[0] is 0x0ffffff8 (media descriptor) at every FAT start; FAT[1] and
    # beyond vary, so match only the first 4 bytes to stay tolerant.
    m = b"\xf8\xff\xff\x0f"
    pts, off, CH = [], 0, 64 * 1024
    while off < bound:
        data = rd(off, CH) or b""
        if data:
            for p in range(0, len(data) - 4, 512):
                if data[p:p + 4] == m:
                    pts.append(off + p)
        off += CH
    return sorted(set(pts))

def data_start_after(fat_off, bound=350 * 1024 * 1024):
    # first cluster past the FAT whose start looks like a directory cluster
    off = fat_off + 4096
    while off < fat_off + bound:
        data = rd(off, 1024 * 1024) or b""
        for p in range(0, len(data) - 128, 4096):
            d = data[p:p + 4096]
            hits, ok = 0, True
            for q in range(0, 4096, 32):
                e = d[q:q + 32]
                nm = e[0:8] + e[8:11]
                if any(c == 0 or c < 0x20 or c == 0x7f for c in nm):
                    ok = False
                    break
                if e[0] != 0xE5 and e[11] != 0x0F and not (e[11] & 0x08):
                    hits += 1
            if ok and (d[0] == 0x2E or hits >= 3):
                return off + p
        off += 1024 * 1024
    return None

if not geo:
    fats = find_fats()
    print("# FAT markers at (bytes): %s" % fats, flush=True)
    best = None
    # two markers: a=FAT1 start, b=FAT2 start -> fatsz, data area, FAT2 content
    if len(fats) >= 2:
        for a, b in zip(fats, fats[1:]):
            if not (0 < (b - a) < 300 * 1024 * 1024 and (b - a) % 512 == 0):
                continue
            fat2 = rd(b, b - a)
            if not fat2:
                continue
            for csize in (32768, 16384, 8192, 4096):
                res = tree_entries(fat2, csize, b + (b - a), 2)
                if res and res[0]:
                    nf = sum(1 for t, _, _ in res[0] if t == "file")
                    if best is None or nf > best[0]:
                        best = (nf, res, csize)
    # single marker: assume FAT2 start, locate data area by scanning
    if best is None and len(fats) >= 1:
        for fb in fats:
            d = data_start_after(fb)
            if d:
                fat = rd(fb, d - fb)
                if fat:
                    for csize in (32768, 16384, 8192, 4096):
                        res = tree_entries(fat, csize, d, 2)
                        if res and res[0]:
                            nf = sum(1 for t, _, _ in res[0] if t == "file")
                            if best is None or nf > best[0]:
                                best = (nf, res, csize)
    if best:
        print("# geometry reconstructed (cluster=%d) - %d files" % (best[2], best[0]), flush=True)
        print_tree(best[1])
        os.close(fd)
        sys.exit(0)
    print("# FAT reconstruction failed.", flush=True)

# -- 3. type sampling -----------------------------------------------------------
if not geo:
    print("# file-type sampling (reading first 8 GB)...", flush=True)
    sigs = {b"\xff\xd8\xff": ".jpg", b"\x89PNG": ".png", b"GIF8": ".gif",
            b"%PDF": ".pdf", b"PK\x03\x04": ".zip/office", b"ID3": ".mp3",
            b"\xff\xfb": ".mp3", b"\x00\x00\x00\x18ftyp": ".mp4", b"BM": ".bmp"}
    counts = collections.Counter()
    off = 64 * 1024 * 1024
    while off < 8 * 1024 * 1024 * 1024:
        data = rd(off, 1024 * 1024) or b""
        if data:
            k = 0
            while k < len(data) - 4:
                hit = next((ext for sig, ext in sigs.items() if data[k:k+len(sig)] == sig), None)
                if hit:
                    counts[hit] += 1
                    k += max(4, len(hit))
                else:
                    k += 16
        off += 64 * 1024 * 1024
    for ext, n in counts.most_common():
        print("#   %-12s %d" % (ext, n), flush=True)
    os.close(fd)
    sys.exit(0)

# -- normal boot-sector path ---------------------------------------------------
csize = geo["bps"] * geo["spc"]
fat1_off = geo["rsv"] * geo["bps"]
fat = None
for n in range(geo["nfat"]):
    f = rd(fat1_off + n * geo["fatsz"] * geo["bps"], geo["fatsz"] * geo["bps"])
    print("# fat%d: %s" % (n + 1, ("read (%d bytes)" % len(f)) if f else "unreadable"), flush=True)
    if f and fat is None:
        fat = f
if fat is None:
    print("# no readable FAT.", flush=True)
    os.close(fd)
    sys.exit(1)
res = tree_entries(fat, csize,
                   (geo["rsv"] + geo["nfat"] * geo["fatsz"]) * geo["bps"], geo["rootcl"])
print_tree(res)
os.close(fd)
