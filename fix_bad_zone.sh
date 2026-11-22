#!/bin/bash
# fix_bad_zone.sh - repartition a usb disk so that the damaged head zone
# (boot area, bad sectors at the start) is left outside any partition.
# usage: sudo bash fix_bad_zone.sh /dev/sdX [label]
# WARNING: this destroys the partition table and all data on the disk.
set -euo pipefail

DEV=${1:?usage: sudo bash fix_bad_zone.sh /dev/sdX [label]}
LABEL=${2:-DATA}
EXPECTED=${3:-HM320II}

model=$(lsblk -dno MODEL "$DEV")
echo "device : $DEV ($model)"
if [ "$(lsblk -dno TRAN "$DEV")" != "usb" ]; then
    echo "refusing: $DEV is not a usb disk"
    exit 1
fi
case "$model" in
    *"$EXPECTED"*) ;;
    *) echo "refusing: model '$model' does not match '$EXPECTED'"; exit 1 ;;
esac
echo "size   : $(lsblk -bdno SIZE "$DEV")"
echo "plan   : partition starts at 512 MB, bad head zone stays unused"
read -r -p "type yes to wipe and repartition: " ans
[ "$ans" = yes ] || { echo aborted; exit 1; }

wipefs -a "$DEV"
printf 'label: dos\nstart=1048576, size=+, type=7\n' | sfdisk -q "$DEV"
partprobe "$DEV" 2>/dev/null || true
sleep 1
mkfs.exfat -n "$LABEL" "${DEV}1"
lsblk -o NAME,FSTYPE,LABEL,SIZE "$DEV"
echo "done"
