# usb-hdd-recovery-tools

Small, read-only toolset for recovering data from a damaged external USB HDD
whose enclosure keeps dropping off the bus. Developed during a real recovery
of a Samsung HM320II (320 GB) with a failing boot sector.

## Tools

### `resume_ddrescue.sh`
Resumable `ddrescue` loop for a flaky USB drive.

* waits for the source disk (matched by its model string in `lsblk`),
* runs `ddrescue`, which resumes from the mapfile,
* when the drive drops off the USB bus it waits for it to come back and
  resumes automatically,
* exits cleanly when `ddrescue` reports done.

The target folder is resolved by disk **label** on every round, so a renamed
mountpoint after a remount cannot strand the run.

```
# copy the healthy bulk first, skipping a damaged start region (recommended):
sudo bash resume_ddrescue.sh 200M
# afterwards, retry the skipped start region:
sudo bash resume_ddrescue.sh
```

Edit the configuration block at the top (`SRC_MODEL`, `DST_LABEL`, ...) to
match your drives.

### `fat32_name_lister.py`
Read-only FAT32 file/dir name lister that works when the boot sector is
unreadable (e.g. a damaged partition start).

Strategy, in order:
1. locate a boot sector copy (primary / backup / injected) and walk the
   directory tree via the FAT (verified),
2. reconstruct geometry from the FAT32 FAT-start signature
   (`f8 ff ff 0f`) and walk the tree (best effort),
3. otherwise do a quick file-**type** sampling scan (no names).

Works on block devices and image files alike. Longer names are reconstructed
from LFN entries.

```
python3 fat32_name_lister.py /dev/sdb1 > listing.txt
python3 fat32_name_lister.py samsung_sda1.img > listing.txt
```

Output is prefixed with `#` for status lines; the listing itself is
`type<TAB>size<TAB>path`.

### `type_scanner.py`
Quick file-type census of a (partial) raw image, without mounting it.
Finds signatures (JPEG, PNG, GIF, PDF, zip/OOXML, MP3, MP4, BMP, TIFF, MKV,
RIFF) and reports counts per type.

```
python3 type_scanner.py samsung_sda1.img 4
```

### `verify_image.py`
Verifies a ddrescue image against its mapfile: reports how much was
rescued, how much is bad (unrecoverable), and whether the copy is complete.

```
python3 verify_image.py samsung_sda1.img samsung.mapfile
```

Exit code: 0 = complete, 1 = incomplete (XX GB still pending), 2 = nothing copied.

## Dependencies
* `ddrescue` (GNU ddrescue) for the shell loop
* `lsblk`, `findmnt` (util-linux) for device/target detection
* Python 3 (stdlib only) for the Python tools

## Compatibility

* **Python tools** (`fat32_name_lister.py`, `type_scanner.py`, `verify_image.py`):
  cross-platform (Linux, macOS, Windows) - pure Python stdlib, and they work
  on image files and block devices alike (on Windows, point them at image
  files).
* **`resume_ddrescue.sh`**: Linux only - it relies on `lsblk`/`findmnt`
  (util-linux) and GNU `ddrescue`. There is no Windows/macOS equivalent
  without a VM/WSL.
* **Selecting drives**: the Python tools take the device or image as an
  argument. The ddrescue loop is configured with the `SRC_MODEL` and
  `DST_LABEL` variables at the top of the script.
* **Many bad sectors**: ddrescue handles any number of bad sectors - it logs
  them in the mapfile, skips and retries them, and resumes after drops.
  Data physically located on bad sectors cannot be recovered; run
  `verify_image.py` afterwards to see the real loss in percent.

## Attribution

These tools were written by **Hermes**, the AI assistant by Nous Research, during a live data-recovery session on a failing external hard drive. The repository owner set the requirements, provided the hardware and ran the recoveries; all code and troubleshooting logic are by the AI assistant.

## Notes & limitations
* Everything here is read-only with respect to the source disk; the Python
  tools never write to the input.
* The FAT-signature reconstruction path is best-effort; the boot-sector and
  type-sampling paths are verified against test media.
* A drive that clicks/beeps while reading is approaching hardware failure.
  Copy what you can, accept skipped bad regions, and back up the result.
