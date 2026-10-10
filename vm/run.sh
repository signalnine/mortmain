#!/bin/bash
# run.sh -- boot an image headless, no network, in the foreground.
#
# Usage: vm/run.sh [IMAGE] [RUN_DIR] [--cpus N] [--memory-mb M]
#   IMAGE    default vm/images/gen0.qcow2 (never written)
#   RUN_DIR  default runs/dev-vm; holds disk.qcow2 (overlay on IMAGE, created
#            if absent, keeps internal snapshots), qmp.sock, qga.sock,
#            serial.log
#
# The qemu command line comes from mortmain/vm.py (QemuBackend.qemu_argv) so
# the shell and the harness boot the same machine:
#   -enable-kvm -machine q35 -cpu host -smp 2 -m 4096 -nodefaults -nic none
#   -display none -serial file:RUN_DIR/serial.log
#   -qmp unix:RUN_DIR/qmp.sock  + virtio-serial org.qemu.guest_agent.0 on
#   unix:RUN_DIR/qga.sock
#
# Talk to it:  socat - UNIX-CONNECT:RUN_DIR/qga.sock   {"execute":"guest-ping"}
# Stop it:     echo '{"execute":"qmp_capabilities"}{"execute":"system_powerdown"}' | socat - UNIX-CONNECT:RUN_DIR/qmp.sock
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
IMAGE=${1:-$ROOT/vm/images/gen0.qcow2}
RUN_DIR=${2:-$ROOT/runs/dev-vm}
shift $(( $# >= 2 ? 2 : $# ))
PY=$ROOT/.venv/bin/python
[ -x "$PY" ] || PY=python3
cd "$ROOT"
exec "$PY" -m mortmain.vm run "$IMAGE" "$RUN_DIR" "$@"
