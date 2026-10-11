#!/bin/bash
# provision.sh -- run once, as root, inside the guest at image build time.
#
# Usage: provision.sh PAYLOAD_DIR
#
# PAYLOAD_DIR layout (made by vm/build-image.sh):
#   metacog            the metacog binary            -> /usr/local/bin/metacog
#   bin/*              in-VM clients                 -> /usr/local/bin/ (0755)
#                      bin/house also gets command symlinks (profess, admit, ...)
#   man1/*             man pages                     -> /usr/share/man/man1/
#   (no rites: /usr/share/metacog/rites/ stays empty; the harness admits the
#    generation-zero rites into /library/outer at lineage init)
#   rule               the Rule (optional)           -> /rule
#   inbox-mask         inbox mask service            -> /usr/local/lib/mortmain/ (0700)
#
# Idempotent: safe to run again on an already provisioned guest.
# Owners and modes follow docs/plan.md "Filesystem".
set -euo pipefail

PAYLOAD=${1:?usage: provision.sh PAYLOAD_DIR}
export DEBIAN_FRONTEND=noninteractive

log() { echo "provision: $*"; }

# --- packages ------------------------------------------------------------
# cloud-init installs these on the build boot; repeated here so the script
# stands alone on a guest with network.
need=()
for p in qemu-guest-agent man-db python3 openssh-client quota acl; do
    dpkg-query -W -f='${Status}' "$p" 2>/dev/null | grep -q "install ok installed" || need+=("$p")
done
if ((${#need[@]})); then
    log "installing ${need[*]}"
    apt-get update -q
    apt-get install -y -q --no-install-recommends "${need[@]}"
fi

# Remove what monks have no use for and what widens the surface.
purge=()
for p in sudo openssh-server unattended-upgrades; do
    dpkg-query -W -f='${Status}' "$p" 2>/dev/null | grep -q "install ok installed" && purge+=("$p")
done
if ((${#purge[@]})); then
    log "purging ${purge[*]}"
    SUDO_FORCE_REMOVE=yes apt-get purge -y -q "${purge[@]}"
    apt-get autoremove -y -q --purge
fi

# --- groups --------------------------------------------------------------
for g in monks postulant novice adept chronicler elder; do
    getent group "$g" >/dev/null || groupadd --system "$g"
done

# --- accounts: lock down -------------------------------------------------
# Cloud default user: remove (cloud-init is told not to create it, belt and braces).
if getent passwd debian >/dev/null; then
    log "removing default cloud user"
    pkill -KILL -u debian 2>/dev/null || true
    userdel -r debian 2>/dev/null || userdel debian
fi
getent group debian >/dev/null && groupdel debian 2>/dev/null || true
rm -f /etc/sudoers.d/90-cloud-init-users
# Root: no password login anywhere. Console/getty still exists but root has no password.
passwd -l root >/dev/null
usermod -s /usr/sbin/nologin root 2>/dev/null || true
# Note: root's shell set to nologin does not affect qemu-ga guest-exec (it execs
# argv directly) or runuser/systemd-run.
: > /etc/securetty 2>/dev/null || true

# useradd defaults for monk accounts created later by the harness.
sed -i -E 's/^#?\s*HOME_MODE\s.*/HOME_MODE\t0711/' /etc/login.defs
grep -q '^HOME_MODE' /etc/login.defs || printf 'HOME_MODE\t0711\n' >> /etc/login.defs
sed -i -E 's/^#?\s*UMASK\s.*/UMASK\t\t077/' /etc/login.defs
cat > /etc/default/useradd <<'EOF'
SHELL=/bin/bash
HOME=/cloister
CREATE_MAIL_SPOOL=no
EOF

# --- filesystem layout ---------------------------------------------------
# mk PATH OWNER:GROUP MODE  (directory)
mk() { mkdir -p "$1"; chown "$2" "$1"; chmod "$3" "$1"; }
# mf PATH OWNER:GROUP MODE  (file, created empty if absent)
mf() { [ -e "$1" ] || : > "$1"; chown "$2" "$1"; chmod "$3" "$1"; }

if [ -f "$PAYLOAD/rule" ]; then
    install -o root -g root -m 0644 "$PAYLOAD/rule" /rule
else
    mf /rule root:root 0644
fi

mk /cloister            root:root    0755
mk /library             root:root    0755
mk /library/outer       root:novice  0750
mk /library/inner       root:adept   0750
mk /scriptorium         root:adept   1770
mk /ossuary             root:adept   0750
mk /chapter             root:novice  0750
mf /chapter/necrology   root:novice  0640
mf /chapter/chronicle   root:chronicler 0664
setfacl -m g:novice:r /chapter/chronicle
mf /chapter/burnlog     root:novice  0640
mf /chapter/vessel      root:novice  0640
mf /chapter/parameters  root:novice  0640
mk /chapter/proposals   root:novice  0750
mf /library/catalog     root:novice  0640
mk /var/bell            root:root    0755
mk /var/lib/mortmain    root:root    0755
[ -s /var/lib/mortmain/ancestors.json ] || echo '[]' > /var/lib/mortmain/ancestors.json
mf /var/lib/mortmain/ancestors.json root:novice 0640
mk /var/spool/mortmain        root:root 0755
mk /var/spool/mortmain/req    root:root 1733
mk /var/spool/mortmain/resp   root:root 0711
mk /var/spool/mortmain/events root:root 1733
mk /usr/share/metacog         root:root 0755
mk /usr/share/metacog/rites   root:root 0755
mk /etc/metacog               root:root 0755
mf /etc/metacog/monastery     root:root 0644

# --- payload -------------------------------------------------------------
install -o root -g root -m 0755 "$PAYLOAD/metacog" /usr/local/bin/metacog
if [ -d "$PAYLOAD/bin" ]; then
    for f in "$PAYLOAD"/bin/*; do
        [ -f "$f" ] || continue
        install -o root -g root -m 0755 "$f" /usr/local/bin/
    done
fi
if [ -d "$PAYLOAD/man1" ]; then
    for f in "$PAYLOAD"/man1/*; do
        [ -f "$f" ] || continue
        install -o root -g root -m 0644 "$f" /usr/share/man/man1/
    done
fi
if [ -f /usr/local/bin/house ]; then
    for c in profess ordeal admit burn prove offer consult testify propose ratify yarrow; do
        ln -sfn house "/usr/local/bin/$c"
    done
fi
mandb -q 2>/dev/null || true

# --- mounts: nosuid/nodev on every place a monk can write -----------------
# A dead monk's setuid binary must not let the living act under its uid.
# Bind mounts of the root fs onto themselves with nosuid,nodev,(noexec not set:
# monks run code from the library).
for d in /cloister /library /scriptorium /ossuary /var/spool/mortmain /tmp /var/tmp; do
    if ! grep -qE "^$d\s+$d\s+none\s+bind" /etc/fstab; then
        printf '%s %s none bind,nosuid,nodev 0 0\n' "$d" "$d" >> /etc/fstab
    fi
done
# /dev/shm is tmpfs nosuid,nodev by default under systemd.

# --- quotas (per-user block/inode limits on the root fs, which holds /cloister)
# Root fs is ext4; legacy (non-journaled-feature) vfsv1 quota files via the
# usrquota mount option. Limits are set later by the harness with setquota.
QUOTA_OK=0
if modprobe quota_v2 2>/dev/null || grep -q quota_v2 /proc/modules || [ -d /sys/module/quota_v2 ]; then
    if ! awk '$2=="/"{print $4}' /etc/fstab | grep -q usrquota; then
        awk 'BEGIN{OFS="\t"} $2=="/" && $1 !~ /^#/ { $4 = $4 ",usrquota" } {print}' /etc/fstab > /etc/fstab.new
        mv /etc/fstab.new /etc/fstab
    fi
    mount -o remount,usrquota / || true
    if quotacheck -cum / 2>&1 && quotaon -u / 2>&1; then
        QUOTA_OK=1
    else
        quotaon -u / 2>/dev/null && QUOTA_OK=1 || true
    fi
fi
log "quota enabled: $QUOTA_OK"
echo "$QUOTA_OK" > /var/lib/mortmain/quota-enabled
chmod 0644 /var/lib/mortmain/quota-enabled

# --- cgroups: per-monk slices ---------------------------------------------
# A monk runs in monk-<user>.slice (user name systemd-escaped: '-' -> '\x2d'),
# child of monk.slice. Prefix drop-in monk-.slice.d applies to every monk-*.slice.
cat > /etc/systemd/system/monk.slice <<'EOF'
[Unit]
Description=monks
Before=slices.target

[Slice]
CPUAccounting=yes
MemoryAccounting=yes
TasksAccounting=yes
EOF
mkdir -p /etc/systemd/system/monk-.slice.d
cat > /etc/systemd/system/monk-.slice.d/50-limits.conf <<'EOF'
[Slice]
CPUQuota=100%
MemoryMax=1G
MemorySwapMax=0
TasksMax=128
EOF

# --- quiet house: no motd, no network, no timers that reach out ----------
: > /etc/motd
chmod -x /etc/update-motd.d/* 2>/dev/null || true
echo localhost > /etc/hostname
cat > /etc/hosts <<'EOF'
127.0.0.1	localhost
::1		localhost ip6-localhost ip6-loopback
EOF
rm -f /etc/network/interfaces.d/50-cloud-init /etc/network/interfaces.d/*cloud* \
      /etc/netplan/*.yaml /etc/systemd/network/*cloud-init* 2>/dev/null || true
if [ -f /etc/network/interfaces ]; then
    cat > /etc/network/interfaces <<'EOF'
auto lo
iface lo inet loopback
EOF
fi
for u in apt-daily.timer apt-daily-upgrade.timer systemd-timesyncd.service \
         systemd-networkd-wait-online.service; do
    systemctl disable "$u" 2>/dev/null || true
    systemctl mask "$u" 2>/dev/null || true
done
# kernel: hide other users' processes is NOT set (hidepid breaks systemd-run),
# but restrict kernel log and ptrace.
cat > /etc/sysctl.d/90-mortmain.conf <<'EOF'
kernel.dmesg_restrict = 1
kernel.kptr_restrict = 2
kernel.yama.ptrace_scope = 2
fs.protected_hardlinks = 1
fs.protected_symlinks = 1
fs.protected_fifos = 2
fs.protected_regular = 2
fs.suid_dumpable = 0
EOF

# --- inbox mask -----------------------------------------------------------
# Keeps notes dropped in an inbox readable by its owner (see the script).
if [ -f "$PAYLOAD/inbox-mask" ]; then
    install -d -o root -g root -m 0755 /usr/local/lib/mortmain
    install -o root -g root -m 0700 "$PAYLOAD/inbox-mask" /usr/local/lib/mortmain/inbox-mask
    cat > /etc/systemd/system/mortmain-inbox-mask.service <<'EOF'
[Unit]
Description=Keep inbox notes readable by their owners

[Service]
ExecStart=/usr/local/lib/mortmain/inbox-mask
Restart=always

[Install]
WantedBy=multi-user.target
EOF
    systemctl enable mortmain-inbox-mask.service 2>/dev/null || true
fi

# --- guest agent ----------------------------------------------------------
# qemu-guest-agent.service is static (started by udev when the virtio port
# appears). Verify nothing blocks guest-exec / guest-file-*.
systemctl enable qemu-guest-agent 2>/dev/null || true
for f in /etc/qemu/qemu-ga.conf /etc/default/qemu-guest-agent; do
    if [ -f "$f" ] && grep -Eq 'block-rpcs|blacklist|-b |--block-rpcs|allow-rpcs' "$f"; then
        echo "provision: WARNING $f restricts guest agent RPCs:" >&2
        cat "$f" >&2
        exit 1
    fi
done
if systemctl cat qemu-guest-agent 2>/dev/null | grep -Eq -- '(-b|--block-rpcs|--allow-rpcs)'; then
    echo "provision: WARNING qemu-guest-agent unit restricts RPCs" >&2
    exit 1
fi

# --- tidy -----------------------------------------------------------------
apt-get clean
rm -rf /var/lib/apt/lists/*
log "done"
