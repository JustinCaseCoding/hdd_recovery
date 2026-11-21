#!/bin/bash
# resume_ddrescue.sh - resumable ddrescue loop for a flaky usb drive.
# usage (root): sudo bash resume_ddrescue.sh [skip_offset]
#
# waits for the source disk (matched by model string in lsblk), runs
# ddrescue (resumes via mapfile), and when the drive drops off the usb
# bus it waits for it to come back and resumes automatically.
# exits cleanly when ddrescue reports done.
# the target folder is resolved by disk label on every round, so remounts
# with a renamed mountpoint cannot strand the run.
#
# optional first argument: byte offset to skip (e.g. "200M") - useful to
# copy the healthy bulk of a damaged disk first and leave a bad start
# region for a later final pass (run again without the offset).

# --- configuration: edit these -------------------------------------------
SRC_MODEL="SAMSUNG HM320II"     # source disk model string (lsblk -dno MODEL)
DST_LABEL="FREECOM HDD"         # target disk label (ntfs/exfat label)
DST_DIR="Backup_HDD_CnMemory"   # subfolder on the target
IMG_NAME="samsung_sda1.img"     # image file name
MAP_NAME="samsung.mapfile"      # ddrescue mapfile name
# --------------------------------------------------------------------------

OFF="${1:-0}"
[ "$OFF" != "0" ] && echo "skip beginning up to $OFF"

# the by-label symlink encodes spaces as \x20
BYLABEL="/dev/disk/by-label/${DST_LABEL// /\\x20}"

while :; do
  D=""
  while [ -z "$D" ]; do
    D=$(lsblk -dno NAME,MODEL 2>/dev/null | awk -v m="$SRC_MODEL" 'index($0,m){print $1; exit}')
    [ -z "$D" ] && sleep 10
  done
  MP=$(findmnt -n -o TARGET "$BYLABEL" 2>/dev/null)
  if [ -z "$MP" ]; then
    echo "[$(date +%T)] target '$DST_LABEL' not mounted - waiting"
    sleep 20
    continue
  fi
  IMG="$MP/$DST_DIR/$IMG_NAME"
  MAP="$MP/$DST_DIR/$MAP_NAME"
  echo "[$(date +%T)] target: $MP/$DST_DIR  (reading /dev/${D}1${OFF:+ skip=$OFF})"
  if [ "$OFF" != "0" ]; then
    ddrescue -i "$OFF" "/dev/${D}1" "$IMG" "$MAP"
  else
    ddrescue "/dev/${D}1" "$IMG" "$MAP"
  fi
  rc=$?
  if [ "$rc" -eq 0 ]; then
    echo "[$(date +%T)] ddrescue reports done - stopping"
    break
  fi
  echo "[$(date +%T)] ddrescue aborted (exit $rc) - waiting for drive to return"
  sleep 10
done
echo "done: $IMG"
