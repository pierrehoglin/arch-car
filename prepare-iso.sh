#!/usr/bin/env bash
# install_alarm.sh - Setup Arch Linux ARM for Raspberry Pi 4

set -euo pipefail

# Check if script is run as root
if [ "$EUID" -ne 0 ]; then
  echo "Please run as root (sudo)."
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ARCHIVE="ArchLinuxARM-rpi-armv7-latest.tar.gz"
ARCHIVE="ArchLinuxARM-rpi-aarch64-latest.tar.gz"
DOWNLOAD_URL="http://os.archlinuxarm.org/os/${ARCHIVE}"

FIRMWARE_PKG="firmware-raspberrypi-20260311-1-any.pkg.tar.xz"
FIRMWARE_URL="http://mirror.archlinuxarm.org/aarch64/alarm/${FIRMWARE_PKG}"

ROOT_MNT="/tmp/arch-iso"
BOOT_MNT="/tmp/arch-iso/boot"

declare -A CONDITIONS=( [format]=0 [extract]=0 [unmount]=0 [aur]=0 [packages]=0 )

ANY_SET=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --*)
            key="${1#--}"
            if [[ -v CONDITIONS[$key] ]]; then
                CONDITIONS[$key]=1
                ANY_SET=1
            else
                echo "Unknown option: $1" >&2; exit 1
            fi
            shift ;;
        -d) DEVICE="$2"; shift 2 ;;
        *)  echo "Unknown option: $1" >&2; exit 1 ;;
    esac
done

if [[ $ANY_SET -eq 0 ]]; then
  for k in "${!CONDITIONS[@]}"; do CONDITIONS[$k]=1; done
fi

FORMAT=${CONDITIONS[format]}
EXTRACT=${CONDITIONS[extract]}
PACKAGES=${CONDITIONS[packages]}
AUR=${CONDITIONS[aur]}
UNMOUNT=${CONDITIONS[unmount]}

echo "Steps to run:"
for k in "${!CONDITIONS[@]}"; do
    [[ ${CONDITIONS[$k]} -eq 1 ]] && echo "  - $k"
done
read -rp "Continue? [y/N] " ok
[[ "$ok" == "y" ]] || exit 0

# Progress-bar function for sync to track /proc/meminfo Dirty KB
sync_with_progress() {
  # Flush buffers in the background
  sync &
  local SYNC_PID=$!

  # Grab initial dirty memory size in KB
  local INITIAL_DIRTY=$(awk '/Dirty:/ {print $2}' /proc/meminfo)
  
  # Avoid division by zero if dirty memory is already negligible
  if [ "$INITIAL_DIRTY" -lt 1024 ]; then
    wait $SYNC_PID
    return 0
  fi

  echo -n "Flushing cache to SD card: "

  while kill -0 $SYNC_PID 2>/dev/null; do
    local CURRENT_DIRTY=$(awk '/Dirty:/ {print $2}' /proc/meminfo)
    
    # Calculate progress percentage
    local WRITTEN=$((INITIAL_DIRTY - CURRENT_DIRTY))
    local PCT=$((WRITTEN * 100 / INITIAL_DIRTY))
    [ $PCT -gt 100 ] && PCT=100
    [ $PCT -lt 0 ] && PCT=0

    # Build a 30-character visual progress bar
    local FILLED=$((PCT * 30 / 100))
    local EMPTY=$((30 - FILLED))
    local BAR=$(printf "%${FILLED}s" '' | tr ' ' '#')
    local PAD=$(printf "%${EMPTY}s" '' | tr ' ' '-')

    # Print updating line overwriting previous output (\r)
    printf "\rFlushing cache to SD card: [%s%s] %3d%% (%d MB remaining)\033[K" \
      "$BAR" "$PAD" "$PCT" "$((CURRENT_DIRTY / 1024))"

    sleep 0.5
  done

  # Ensure bar completes at 100% on exit
  printf "\rFlushing cache to SD card: [##############################] 100%% (0 MB remaining)\033[K\n"
}


format() {
  echo ""
  echo "!!! WARNING: ALL DATA ON $DEVICE WILL BE PERMANENTLY ERASED !!!"
  read -p "Are you absolutely sure you want to continue? (y/N): " confirm
  if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
      echo "Installation cancelled."
      exit 0
  fi

  echo "--- Clearing existing filesystem signatures and partition table..."
  wipefs -a --force "$DEVICE"
  dd if=/dev/zero of="$DEVICE" bs=1M count=10 status=none
  sync_with_progress 

  echo "--- Partitioning drive..."
  sfdisk "$DEVICE" <<EOF
label: dos
1 : size=256M, type=c, bootable
2 : type=83
EOF

  echo "--- Formatting partitions..."
  mkfs.vfat -F 32 "$PART_BOOT"
  mkfs.ext4 -F "$PART_ROOT"
}

extract() {
  # Check for tarball or download automatically via wget
  if [ ! -f "$ARCHIVE" ]; then
    echo "--------------------------------------------------------"
    echo " $ARCHIVE not found locally."
    echo " Downloading official image from Arch Linux ARM..."
    echo "--------------------------------------------------------"
    wget -O "$ARCHIVE" "$DOWNLOAD_URL"
    echo "Download complete!"
    echo ""
  fi

  echo "--- Extracting Root Filesystem (This will take a few minutes)..."
  bsdtar -xpf "$ARCHIVE" -C "$ROOT_MNT"
  sync_with_progress 
}

swap_firmware() {
  arch-chroot "$ROOT_MNT" /bin/bash <<EOF
set -ex

# Initialize pacman keys
pacman-key --init
pacman-key --populate archlinuxarm

pacman -Rdd --noconfirm uboot-raspberrypi linux-aarch64

sed -i 's/^#DisableSandboxFilesystem/DisableSandboxFilesystem/' /etc/pacman.conf
sed -i 's/^#DisableSandboxSyscalls/DisableSandboxSyscalls/' /etc/pacman.conf

pacman -Syu --noconfirm
pacman -S --noconfirm --overwrite "/boot/*" linux-rpi linux-firmware

sed -i 's/^DisableSandboxFilesystem/#DisableSandboxFilesystem/' /etc/pacman.conf
sed -i 's/^DisableSandboxSyscalls/#DisableSandboxSyscalls/' /etc/pacman.conf
EOF
}

install_packages() {
  mapfile -t aur_packages < <(grep -v '^#' "$SCRIPT_DIR/aur.packages" | grep -v '^$')
  mapfile -t packages < <(grep -v '^#' "$SCRIPT_DIR/base.packages" | grep -v '^$')

  arch-chroot "$ROOT_MNT" /bin/bash <<EOF
set -ex

sed -i 's/^#DisableSandboxFilesystem/DisableSandboxFilesystem/' /etc/pacman.conf
sed -i 's/^#DisableSandboxSyscalls/DisableSandboxSyscalls/' /etc/pacman.conf

pacman -Syu --noconfirm
pacman -Sy --noconfirm ${packages[*]}

sed -i 's/^DisableSandboxFilesystem/#DisableSandboxFilesystem/' /etc/pacman.conf
sed -i 's/^DisableSandboxSyscalls/#DisableSandboxSyscalls/' /etc/pacman.conf

mkdir -p /etc/sudoers.d
echo 'alarm ALL=(ALL) NOPASSWD: ALL' > /etc/sudoers.d/nopass
chmod 440 /etc/sudoers.d/nopass

pacman -Sy --noconfirm --disable-sandbox base-devel git cargo

EOF

  arch-chroot "$ROOT_MNT" su - alarm -c ' 
set -ex

git clone https://github.com/J-Lentz/iwgtk.git ~/iwgtk
cd ~/iwgtk
meson setup build
cd build
meson compile


git clone https://github.com/vinceliuice/Tela-icon-theme ~/tela-icon-theme
cd ~/tela-icon-theme
./install.sh

for f in "$@"; do
  rm -rf ~/$f
  git clone https://aur.archlinux.org/$f.git ~/$f
  cd ~/$f
  makepkg -s --noconfirm
done
' sh "${aur_packages[@]}"

  arch-chroot "$ROOT_MNT" /bin/bash <<EOF
set -ex

meson install -C /home/alarm/iwgtk/build

for f in ${aur_packages[@]}; do
  pacman -U --noconfirm /home/alarm/\$f/*.pkg.tar.xz
done

rm /etc/sudoers.d/nopass
EOF

  

  cp -r "$SCRIPT_DIR/root/." "$ROOT_MNT"

  arch-chroot "$ROOT_MNT" /bin/bash <<EOF
set -ex

chown -R alarm:alarm /home/alarm
chmod +x -R /home/alarm/.local/bin

usermod -aG wheel alarm
chmod 440 -R /etc/sudoers.d
chmod 600 /etc/hostapd/hostapd.conf
chmod 600 /etc/NetworkManager/system-connections/lte.nmconnection

chmod +x /usr/local/bin/wayfire-run

fc-cache -fv
locale-gen

ln -sf /usr/share/zoneinfo/Europe/Stockholm /etc/localtime
hwclock --systohc 2>/dev/null || true

systemctl enable sshd
systemctl disable bluetooth
systemctl enable NetworkManager
systemctl enable ModemManager
systemctl enable greetd
systemctl disable ofono
systemctl enable regen-initramfs
systemctl enable systemd-timesyncd
systemctl disable systemd-networkd
systemctl disable getty@tty1

su - alarm -c '
set -ex

mkdir -p ~/.config/systemd/user/default.target.wants
ln -s /usr/lib/systemd/user/spotifyd.service \
      ~/.config/systemd/user/default.target.wants/spotifyd.service

ln -s /usr/lib/systemd/user/obex.service \
      ~/.config/systemd/user/dbus-org.bluez.obex.service

git clone https://github.com/pierrehoglin/arch-car.git
car-unit-sync
'
EOF
}

echo "========================================================"
echo " AVAILABLE STORAGE DRIVES:"
echo "========================================================"
lsblk -d -o NAME,SIZE,MODEL,TYPE | grep -E "disk|TYPE"
echo "========================================================"

# Prompt user for selection
read -p "Enter the disk name to flash (e.g., sdb, mmcblk0): " DISK_CHOICE
DISK_CHOICE=$(basename "$DISK_CHOICE")
DEVICE="/dev/$DISK_CHOICE"

# Validate that the selected block device exists
if [ -z "$DISK_CHOICE" ] || [ ! -b "$DEVICE" ]; then
  echo "Error: Invalid disk choice or device does not exist."
  exit 1
fi

# Handle naming convention discrepancies between /dev/sdb and /dev/mmcblk0
if [[ "$DEVICE" == *"mmcblk"* ]] || [[ "$DEVICE" == *"nvme"* ]]; then
    echo "Only /dev/sdX disks allowed"
    exit 1
else
    PART_BOOT="${DEVICE}1"
    PART_ROOT="${DEVICE}2"
fi


echo "--- Unmounting device if previously mounted..."
umount ${DEVICE}* 2>/dev/null || true

if [[ $FORMAT -eq 1 ]]; then
  format
fi

echo "--- Creating mount points and mounting..."
mkdir -p "$ROOT_MNT"
mount "$PART_ROOT" "$ROOT_MNT"
mkdir -p "$BOOT_MNT"
mount "$PART_BOOT" "$BOOT_MNT"

if [[ $EXTRACT -eq 1 ]]; then
  extract
  swap_firmware
fi


if [[ $PACKAGES -eq 1 ]]; then
  install_packages
fi

if [[ $UNMOUNT -eq 1 ]]; then
  echo "--- Cleaning up..."
  umount "$BOOT_MNT"
  umount "$ROOT_MNT"
  rmdir "$ROOT_MNT"
fi

sync_with_progress 


echo "========================================================"
echo " SUCCESS! Arch Linux ARM is successfully flashed to $DEVICE"
echo " Default Login credentials:"
echo "   User: alarm  | Password: alarm"
echo "   User: root   | Password: root"
echo "========================================================"
