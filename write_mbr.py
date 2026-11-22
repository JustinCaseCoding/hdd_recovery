#!/usr/bin/env python3
# write_mbr.py - write a minimal dos mbr with one partition straight to a
# block device, bypassing sfdisk/parted probing that fails on bad sectors.
# usage: sudo /usr/bin/python3 write_mbr.py /dev/sdX [start_mb]
# warning: destroys the existing partition table. refuses non HM320II disks.
import os, struct, sys

DEV = sys.argv[1]
START_MB = int(sys.argv[2]) if len(sys.argv) > 2 else 512

name = os.path.basename(DEV)
model_path = "/sys/block/%s/device/model" % name
try:
    model = open(model_path).read().strip()
except OSError:
    model = "?"
print("device : %s (%s)" % (DEV, model))
if "HM320II" not in model:
    sys.exit("refusing: model is not HM320II")

fd = os.open(DEV, os.O_RDWR | os.O_SYNC)
try:
    size = os.lseek(fd, 0, os.SEEK_END)
    total = size // 512
finally:
    os.close(fd)
print("size   : %d sectors (%d bytes)" % (total, size))

start = START_MB * 2048
count = total - start
if start <= 2048 or count <= 0:
    sys.exit("refusing: bad geometry")

entry = bytes([0x00, 0xFE, 0xFF, 0xFF, 0x07, 0xFE, 0xFF, 0xFF])
entry += struct.pack("<II", start, min(count, 0xFFFFFFFF))
mbr = b"\x00" * 446 + entry + b"\x00" * 48 + b"\x55\xaa"
assert len(mbr) == 512

fd = os.open(DEV, os.O_RDWR | os.O_SYNC)
try:
    os.pwrite(fd, mbr, 0)
finally:
    os.close(fd)
print("wrote mbr: partition 1 at sector %d (%d MB), %d sectors, type 0x07" % (
    start, start // 2048, min(count, 0xFFFFFFFF)))
