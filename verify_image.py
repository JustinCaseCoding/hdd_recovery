#!/usr/bin/env python3
# verify_image.py - verify a ddrescue image against its mapfile.
# usage: python3 verify_image.py <image> <mapfile>
#
# parses the ddrescue mapfile and reports how much of the source was
# rescued, how much is bad/unreadable, and whether the copy is complete.
# statuses (ddrescue):
#   + finished (rescued)    - bad sector (lost)      / non-tried (pending)
#   * non-trimmed           ? non-scraped
import sys, os

if len(sys.argv) < 3:
    print("usage: %s <image> <mapfile>" % sys.argv[0], flush=True)
    sys.exit(1)

img, mapf = sys.argv[1], sys.argv[2]
img_size = os.path.getsize(img)

total = done = bad = untried = trimmed = scraped = 0
nblocks = 0
with open(mapf) as f:
    for line in f:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 3:
            continue
        try:
            pos = int(parts[0], 16)
            size = int(parts[1], 16)
        except ValueError:
            continue
        status = parts[2]
        total += size
        nblocks += 1
        if status == "+":
            done += size
        elif status == "-":
            bad += size
        elif status == "*":
            trimmed += size
        elif status == "?":
            scraped += size
        else:
            untried += size

def gb(n):
    return n / 1e9

print("image size : %.2f GB" % gb(img_size), flush=True)
print("mapfile sum: %.2f GB (%d blocks)" % (gb(total), nblocks), flush=True)
print("", flush=True)
print("rescued (finished)   : %8.2f GB  %5.1f%%" % (gb(done), 100.0 * done / total if total else 0), flush=True)
print("bad sectors (lost)   : %8.2f GB  %5.1f%%" % (gb(bad), 100.0 * bad / total if total else 0), flush=True)
print("in progress (trim)   : %8.2f GB  %5.1f%%" % (gb(trimmed), 100.0 * trimmed / total if total else 0), flush=True)
print("in progress (scrape) : %8.2f GB  %5.1f%%" % (gb(scraped), 100.0 * scraped / total if total else 0), flush=True)
print("not attempted        : %8.2f GB  %5.1f%%" % (gb(untried), 100.0 * untried / total if total else 0), flush=True)
print("", flush=True)

# "?" (non-scraped) and "/" (non-tried) mean the region is not copied yet in
# this ddrescue version's mapfile - treat them as pending, not as recovered.
pending = trimmed + scraped + untried
print("rescued so far : %.2f GB (%.1f%%)" % (gb(done), 100.0 * done / total if total else 0), flush=True)
print("pending        : %.2f GB (%.1f%%)" % (gb(pending), 100.0 * pending / total if total else 0), flush=True)
print("unrecoverable  : %.2f GB (%.1f%%)" % (gb(bad), 100.0 * bad / total if total else 0), flush=True)

if total == 0:
    print("verdict: mapfile empty - nothing copied yet", flush=True)
    sys.exit(2)
if pending == 0:
    print("verdict: COMPLETE - all regions rescued, %s bad" % gb(bad), flush=True)
    sys.exit(0)
print("verdict: INCOMPLETE - run still in progress (%s pending)" % gb(pending), flush=True)
sys.exit(1)
