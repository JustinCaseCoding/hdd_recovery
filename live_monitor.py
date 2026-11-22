#!/usr/bin/env python3
# live_monitor.py - colorful live console dashboard for an ongoing ddrescue
# image copy.
# usage: python3 live_monitor.py <image> <mapfile> [census_interval_s]
# refreshes every 5 s: image size, percent bar, rate, ddrescue mapfile
# status (rescued/bad/pending), a file-type census and the last files found
# (type + approx size + position). census recomputed in a background
# thread every 120 s (or given interval). ctrl-c to exit.
import os, sys, time, threading, collections

if len(sys.argv) < 3:
    print("usage: %s <image> <mapfile> [census_interval_s]" % sys.argv[0], flush=True)
    sys.exit(1)

IMG, MAP = sys.argv[1], sys.argv[2]
CENSUS_EVERY = float(sys.argv[3]) if len(sys.argv) > 3 else 120.0

SIGS = [
    (b"\xff\xd8\xff", "jpg"), (b"\x89PNG\r\n\x1a\n", "png"), (b"GIF8", "gif"),
    (b"%PDF", "pdf"), (b"PK\x03\x04", "zip/office"), (b"ID3", "mp3"),
    (b"\xff\xfb", "mp3"), (b"\x00\x00\x00\x18ftyp", "mp4"), (b"BM", "bmp"),
    (b"\x1aE\xdf\xa3", "mkv"), (b"RIFF", "wav/avi"),
]
FG = dict(jpg=32, bmp=32, png=32, gif=32, mp3=36, wav=36, zip=33, pdf=33,
          mp4=35, mkv=35, tiff=32, office=33)

def col(code, s):
    return "\x1b[%dm%s\x1b[0m" % (code, s)

def img_size():
    try:
        return os.path.getsize(IMG)
    except OSError:
        return None

def parse_map():
    total = done = bad = pend = 0
    try:
        with open(MAP) as f:
            for ln in f:
                ln = ln.strip()
                if not ln or ln.startswith("#"):
                    continue
                p = ln.split()
                if len(p) < 3:
                    continue
                try:
                    size = int(p[1], 16)
                except ValueError:
                    continue
                total += size
                st = p[2]
                if st == "+":
                    done += size
                elif st == "-":
                    bad += size
                else:
                    pend += size
    except OSError:
        return None
    return total, done, bad, pend

census = {}
last_files = collections.deque(maxlen=14)

def census_worker():
    global census, last_files
    while True:
        sz = img_size()
        if sz:
            counts = collections.Counter()
            hits = []  # (pos, type)
            off, CH = 0, 4 * 1024 * 1024
            while off < sz:
                try:
                    f = os.open(IMG, os.O_RDONLY)
                    try:
                        data = os.pread(f, CH, off)
                    finally:
                        os.close(f)
                except OSError:
                    break
                if not data:
                    break
                k = 0
                while k < len(data) - 8:
                    hit = next((e for s, e in SIGS if data.startswith(s, k)), None)
                    if hit:
                        counts[hit] += 1
                        hits.append((off + k, hit))
                        k += 4096
                    else:
                        k += 64
                off += CH
            census = dict(counts)
            new = []
            for i, (pos, typ) in enumerate(hits):
                nxt = hits[i + 1][0] if i + 1 < len(hits) else None
                size = (nxt - pos) if nxt else None
                new.append((typ, size, pos))
            last_files = collections.deque(new[-14:], maxlen=14)
        time.sleep(CENSUS_EVERY)

threading.Thread(target=census_worker, daemon=True).start()

def gb(n):
    return n / 1e9

def fmt_size(b):
    if b is None:
        return "?"
    if b >= 1e9:
        return "%.1f GB" % (b / 1e9)
    if b >= 1e6:
        return "%.1f MB" % (b / 1e6)
    return "%.0f kB" % (b / 1e3)

prev, prev_t = None, time.time()
H = lambda s: col("1;36", s)
print("\x1b[?25l", end="", flush=True)  # hide cursor
try:
    while True:
        t0 = time.time()
        cur = img_size()
        mp = parse_map()
        lines = []
        lines.append(H("=" * 66))
        lines.append(H(" USB HDD ddrescue monitor".ljust(34) + time.strftime("%H:%M:%S").rjust(32)))
        lines.append(H("=" * 66))
        if cur is None:
            lines.append(col(33, "  image file not found yet - waiting for ddrescue..."))
        else:
            if mp:
                total, done, bad, pend = mp
                pct = 100.0 * done / total if total else 0.0
                n = int(pct / 2)
                bar = col(32, "\u2588" * n) + col(90, "\u2591" * (50 - n))
                lines.append("  rescued    %s / %s    %s" % (
                    col("1;32", "%9.2f GB" % gb(done)),
                    "%6.2f GB" % gb(total), col("1;33", "%5.1f%%" % pct)))
                lines.append("  [" + bar + "]")
                lines.append("  bad %s    pending %s" % (
                    col(31, "%6.2f GB" % gb(bad)), col(33, "%9.2f GB" % gb(pend))))
            rate = (cur - prev) / (t0 - prev_t) / 1e6 if prev is not None and t0 > prev_t else 0.0
            lines.append("  image %s    %s current rate" % (
                col("1;34", "%9.2f GB" % gb(cur)), col(36, "%5.2f MB/s" % rate)))
        if census:
            total_hits = sum(census.values())
            parts = ["%s %d" % (col(FG.get(t, 90), t), n) for t, n in
                     sorted(census.items(), key=lambda x: -x[1])[:6]]
            lines.append(H("-" * 66))
            lines.append("  %s (%d): %s" % (col("1;37", "file census"),
                                             total_hits, " | ".join(parts)))
            lines.append(H("  last files found (type, approx size, position):"))
            for typ, size, pos in last_files:
                fg = FG.get(typ, 90)
                lines.append("    %s  %s  @  %s" % (
                    col(fg, typ.ljust(11)), col("1;37", fmt_size(size).rjust(9)),
                    "%5.2f GB" % gb(pos)))
        lines.append(H("=" * 66))
        lines.append(col(90, "  ctrl-c to exit  (dashboard only - ddrescue keeps running)"))
        print("\x1b[2J\x1b[H" + "\n".join(lines), end="", flush=True)
        prev, prev_t = cur, t0
        time.sleep(5)
except KeyboardInterrupt:
    pass
finally:
    print("\x1b[?25h")  # show cursor again
