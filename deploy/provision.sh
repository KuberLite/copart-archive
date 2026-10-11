#!/bin/bash
# Prepares a fresh Ubuntu 22.04/24.04 box for the archive. Safe to run again.
#   scp deploy/provision.sh root@HOST: && ssh root@HOST bash provision.sh
# What it does and why is in deploy/README.md; every step here was learned on a
# real server, see the comments.
set -euo pipefail
BASE=/opt/copart-archive
MEMORY=${MEMORY:-700m}  # container limit; the boxes so far had 1 GB of RAM
export DEBIAN_FRONTEND=noninteractive
say() { printf '\n== %s\n' "$*"; }

say "packages"
apt-get update -qq
apt-get -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold upgrade -y -qq >/dev/null
apt-get install -y -qq ufw fail2ban rsync docker.io docker-buildx >/dev/null
echo "ok"

say "swap 2G"  # without it a big xlsx can push a 1 GB box into the OOM killer
if ! swapon --show | grep -q /swapfile; then
  [ -f /swapfile ] || fallocate -l 2G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile >/dev/null   # no -q: not every mkswap has it
  swapon /swapfile
fi
grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
echo 'vm.swappiness=10' > /etc/sysctl.d/99-swappiness.conf && sysctl -q --system
swapon --show --noheadings

say "firewall: only ssh in"
ufw allow OpenSSH >/dev/null
ufw default deny incoming >/dev/null
ufw default allow outgoing >/dev/null
ufw --force enable >/dev/null
ufw status | sed -n 1p   # sed reads it all: head would SIGPIPE ufw under pipefail

say "fail2ban"
printf '[sshd]\nenabled = true\nmaxretry = 5\nfindtime = 10m\nbantime = 1h\n' > /etc/fail2ban/jail.d/sshd.local
systemctl enable fail2ban >/dev/null 2>&1
systemctl restart fail2ban
sleep 2
systemctl is-active fail2ban

say "ssh: keys only"  # files in sshd_config.d are read first, the first value wins
cat > /etc/ssh/sshd_config.d/01-key-only.conf <<'CONF'
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin prohibit-password
CONF

say "docker"
mkdir -p /etc/docker
echo '{ "log-driver": "json-file", "log-opts": { "max-size": "10m", "max-file": "3" } }' > /etc/docker/daemon.json
systemctl enable docker >/dev/null 2>&1
systemctl restart docker
docker --version

say "archive directories"
mkdir -p "$BASE/app" "$BASE/archive" "$BASE/input"
echo "MEMORY=$MEMORY" > "$BASE/host.conf"
ls "$BASE"

say "sftp: read-only, caged, keys only"
mkdir -p /srv/copart-sftp/archive
chown root:root /srv/copart-sftp /srv/copart-sftp/archive
chmod 755 /srv/copart-sftp /srv/copart-sftp/archive
grep -q '/srv/copart-sftp/archive' /etc/fstab || \
  echo "$BASE/archive /srv/copart-sftp/archive none bind,ro 0 0" >> /etc/fstab
mountpoint -q /srv/copart-sftp/archive || mount /srv/copart-sftp/archive
groupadd -f sftponly
groupadd -f copart
id copart >/dev/null 2>&1 || useradd -r -g copart -s /usr/sbin/nologin -M -d /archive copart
usermod -aG sftponly -d /archive -p '*' copart   # '*': no password, yet not "locked" for PAM
# Keys are served by a command, NOT AuthorizedKeysFile: cloud-init reads that
# setting on every boot, ignores the Match block, writes root's keys there and
# closes the directory to 700 — copart then cannot read its own key.
mkdir -p /etc/copart-sftp/keys
chmod 755 /etc/copart-sftp /etc/copart-sftp/keys
touch /etc/copart-sftp/keys/copart && chmod 644 /etc/copart-sftp/keys/copart
cat > /usr/local/sbin/copart-sftp-keys <<'KEYS'
#!/bin/sh
# Prints a user's SFTP keys for sshd (AuthorizedKeysCommand in the sftponly block).
case "${1:-}" in
  ""|*[!a-z0-9_-]*) exit 1 ;;
esac
f="/etc/copart-sftp/keys/$1"
[ -f "$f" ] && cat "$f"
exit 0
KEYS
chown root:root /usr/local/sbin/copart-sftp-keys && chmod 755 /usr/local/sbin/copart-sftp-keys
[ -f /etc/ssh/sshd_config.before-copart ] || cp /etc/ssh/sshd_config /etc/ssh/sshd_config.before-copart
sed -i 's|^Subsystem\s*sftp\s*/usr/lib/openssh/sftp-server|Subsystem sftp internal-sftp|' /etc/ssh/sshd_config
grep -q 'Match Group sftponly' /etc/ssh/sshd_config || cat >> /etc/ssh/sshd_config <<'CONF'

# Copart archive: read-only sftp, no shell, caged in /srv/copart-sftp
Match Group sftponly
    ChrootDirectory /srv/copart-sftp
    ForceCommand internal-sftp -R
    AuthorizedKeysCommand /usr/local/sbin/copart-sftp-keys %u
    AuthorizedKeysCommandUser nobody
    PasswordAuthentication no
    AllowTcpForwarding no
    AllowAgentForwarding no
    X11Forwarding no
    PermitTunnel no
CONF

say "sshd: check, then apply"
if sshd -t; then
  systemctl restart ssh   # 24.04 starts sshd from a socket; restart covers both
  sshd -T | grep -E '^(passwordauthentication|permitrootlogin) '
else
  echo "sshd_config is broken, restoring" >&2
  cp /etc/ssh/sshd_config.before-copart /etc/ssh/sshd_config
  rm -f /etc/ssh/sshd_config.d/01-key-only.conf
  exit 1
fi

say "done — reboot is needed only if /var/run/reboot-required exists"
ls /var/run/reboot-required 2>/dev/null || echo "no reboot needed"
