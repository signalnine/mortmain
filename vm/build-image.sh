#!/bin/bash
# build-image.sh -- build vm/images/gen0.qcow2 from the Debian base image.
#
# Usage: vm/build-image.sh [--force]
#
# Output: vm/images/gen0.qcow2, a STANDALONE compressed qcow2 (no backing
# file; the base image can be deleted afterwards). Virtual size 8G.
# Runtime boots never write to gen0: they use an overlay (see vm/run.sh and
# mortmain/vm.py), so gen0 is the pristine generation-zero house.
#
# Steps:
#   1. stage payload: metacog binary, guest/bin, guest/man/man1, seed/rule,
#      guest/setup/provision.sh -> a tar file, attached to the build VM as a
#      raw read-only virtio disk (serial "mmpayload"); the guest reads it
#      with `tar -xf /dev/disk/by-id/virtio-mmpayload`.
#   2. cloud-init NoCloud seed (cloud-localds): installs packages, runs
#      provision.sh, disables cloud-init, powers off.
#   3. boot a throwaway 8G overlay on the base with user-mode networking.
#   4. check the serial log for the success marker, compress to gen0.qcow2.
#
# Idempotent: a stamp (sha256 of every input) is kept next to the image; if
# inputs are unchanged the build is skipped. --force rebuilds anyway.
# Rebuilding replaces gen0.qcow2; overlays made from the old gen0 become
# invalid (qemu refuses or misreads them), so discard old runs' overlays.
#
# Env:
#   METACOG_BIN   path of the static metacog binary
#                 (default metacog/metacog-linux-amd64, built with CGO_ENABLED=0)
#   BUILD_TIMEOUT seconds to wait for the build VM (default 1500)
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
BASE="$ROOT/vm/base/debian-12-genericcloud-amd64.qcow2"
IMAGES="$ROOT/vm/images"
OUT="$IMAGES/gen0.qcow2"
STAMP="$IMAGES/gen0.stamp"
METACOG_BIN=${METACOG_BIN:-$ROOT/metacog/metacog-linux-amd64}
BUILD_TIMEOUT=${BUILD_TIMEOUT:-1500}
FORCE=0
[ "${1:-}" = "--force" ] && FORCE=1

die() { echo "build-image: $*" >&2; exit 1; }

[ -f "$BASE" ] || die "base image missing: $BASE"
[ -x "$METACOG_BIN" ] || die "metacog binary missing or not executable: $METACOG_BIN
  build it first (cd metacog && CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -o metacog-linux-amd64 ./cmd/metacog), or set METACOG_BIN"
file -b "$METACOG_BIN" | grep -q 'ELF 64-bit.*x86-64.*statically linked' || die "$METACOG_BIN is not a statically linked x86-64 ELF binary"
for t in qemu-system-x86_64 qemu-img cloud-localds tar sha256sum; do
    command -v "$t" >/dev/null || die "missing tool: $t"
done
[ -r /dev/kvm ] && [ -w /dev/kvm ] || die "/dev/kvm not accessible"
mkdir -p "$IMAGES"

# --- input stamp -----------------------------------------------------------
inputs_hash() {
    {
        sha256sum "$0" "$METACOG_BIN"
        stat -c '%s %Y' "$BASE"
        (cd "$ROOT" && find guest/bin guest/man guest/setup seed -type f -print0 2>/dev/null \
            | sort -z | xargs -0 -r sha256sum)
    } | sha256sum | cut -d' ' -f1
}
HASH=$(inputs_hash)
if [ $FORCE = 0 ] && [ -f "$OUT" ] && [ -f "$STAMP" ] && [ "$(cat "$STAMP")" = "$HASH" ]; then
    echo "build-image: $OUT is up to date ($HASH)"
    exit 0
fi

WORK=$(mktemp -d "$IMAGES/build.XXXXXX")
QPID=
cleanup() {
    [ -n "$QPID" ] && kill "$QPID" 2>/dev/null || true
    rm -rf "$WORK"
}
trap cleanup EXIT

# --- 1. payload ------------------------------------------------------------
P="$WORK/payload"
mkdir -p "$P/bin" "$P/man1"
cp "$METACOG_BIN" "$P/metacog"
cp "$ROOT/guest/setup/provision.sh" "$P/provision.sh"
find "$ROOT/guest/bin" -maxdepth 1 -type f -exec cp {} "$P/bin/" \; 2>/dev/null || true
find "$ROOT/guest/man/man1" -maxdepth 1 -type f -exec cp {} "$P/man1/" \; 2>/dev/null || true
[ -f "$ROOT/seed/rule" ] && cp "$ROOT/seed/rule" "$P/rule"
tar --owner=0 --group=0 --numeric-owner -C "$P" -cf "$WORK/payload.tar" .
# pad to a whole MiB so the block device size is sane
truncate -s %1M "$WORK/payload.tar"

# --- 2. cloud-init seed ----------------------------------------------------
cat > "$WORK/user-data" <<'EOF'
#cloud-config
users: []
disable_root: true
ssh_pwauth: false
package_update: true
package_upgrade: false
packages: [qemu-guest-agent, man-db, python3, openssh-client, quota, acl]
growpart: {mode: auto, devices: ['/']}
resize_rootfs: true
runcmd:
  - - bash
    - -c
    - |
      set -o pipefail
      mkdir -p /run/mmpayload
      if tar -xf /dev/disk/by-id/virtio-mmpayload -C /run/mmpayload \
         && bash /run/mmpayload/provision.sh /run/mmpayload 2>&1 | tee /var/log/mortmain-provision.log > /dev/ttyS0; then
        touch /etc/cloud/cloud-init.disabled
        fstrim -av > /dev/ttyS0 2>&1 || true
        sync
        echo MORTMAIN_BUILD_OK > /dev/ttyS0
      else
        echo MORTMAIN_BUILD_FAIL > /dev/ttyS0
      fi
power_state:
  mode: poweroff
  condition: true
  timeout: 60
EOF
cat > "$WORK/meta-data" <<'EOF'
instance-id: mortmain-build
local-hostname: localhost
EOF
cloud-localds "$WORK/seed.iso" "$WORK/user-data" "$WORK/meta-data"

# --- 3. build boot -----------------------------------------------------------
qemu-img create -q -f qcow2 -F qcow2 -b "$BASE" "$WORK/disk.qcow2" 8G
echo "build-image: booting build VM (serial log: $WORK/serial.log)"
t0=$(date +%s)
qemu-system-x86_64 \
    -enable-kvm -machine q35 -cpu host -smp 2 -m 2048 \
    -nodefaults -display none -no-reboot \
    -serial "file:$WORK/serial.log" \
    -drive "file=$WORK/disk.qcow2,if=none,id=root,format=qcow2,discard=unmap,cache=unsafe" \
    -device virtio-blk-pci,drive=root,bootindex=0 \
    -drive "file=$WORK/seed.iso,if=virtio,format=raw,readonly=on" \
    -drive "file=$WORK/payload.tar,if=none,id=payload,format=raw,readonly=on" \
    -device virtio-blk-pci,drive=payload,serial=mmpayload \
    -nic user,model=virtio-net-pci \
    -device virtio-rng-pci &
QPID=$!
while kill -0 "$QPID" 2>/dev/null; do
    if (( $(date +%s) - t0 > BUILD_TIMEOUT )); then
        tail -50 "$WORK/serial.log" >&2
        die "build VM timed out after ${BUILD_TIMEOUT}s"
    fi
    sleep 2
done
QRC=0
wait "$QPID" || QRC=$?
QPID=
[ -f "$WORK/serial.log" ] || die "qemu failed to start (exit $QRC)"
echo "build-image: build VM ran $(( $(date +%s) - t0 ))s"
cp "$WORK/serial.log" "$IMAGES/gen0.build.log"
if ! grep -q MORTMAIN_BUILD_OK "$WORK/serial.log"; then
    grep -n -A40 'provision:' "$WORK/serial.log" | tail -60 >&2 || tail -60 "$WORK/serial.log" >&2
    die "provisioning failed; full log: $IMAGES/gen0.build.log"
fi

# --- 4. compress to a standalone image -------------------------------------
echo "build-image: compressing"
qemu-img convert -c -O qcow2 "$WORK/disk.qcow2" "$WORK/gen0.qcow2"
mv -f "$WORK/gen0.qcow2" "$OUT"
echo "$HASH" > "$STAMP"
echo "build-image: wrote $OUT ($(du -h "$OUT" | cut -f1)), total $(( $(date +%s) - t0 ))s"
