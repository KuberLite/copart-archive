# Access to the archive over SFTP

SFTP comes with SSH, so nothing extra runs on the server and it works from any OS.
The account is read-only, has no shell and is caged in a directory that holds
nothing but the archive.

```
host     grahovskiy.com   port 22
user     copart           key /root/copart-sftp-key (private, root only)
path     /archive         (the real path is /opt/copart-archive/archive)
```

`/archive` is also the account's home, so a client lands right in it.

Checked after setup: `mkdir` is denied, `cd /etc` leads nowhere, an interactive
login answers "This service allows sftp connections only", port forwarding is off,
and a file downloads fine.

## Clients

- **Windows** — WinSCP or FileZilla; for a drive letter see below.
- **Linux** — the file manager opens `sftp://copart@grahovskiy.com/archive`, or `sshfs`.
- **macOS** — Finder has no SFTP; Cyberduck or `sshfs`.
- **CLI** — `sftp -i key copart@grahovskiy.com`, `rsync -e ssh`, `scp`.

## A network drive on Windows

Windows cannot mount SFTP by itself; WinFsp + SSHFS-Win (both free) add that.

1. Install [WinFsp](https://winfsp.dev), then [SSHFS-Win](https://github.com/winfsp/sshfs-win).
2. The easy way — [SSHFS-Win Manager](https://github.com/evsar3/sshfs-win-manager):
   host `grahovskiy.com`, port 22, user `copart`, authentication by private key
   (pick the key file), remote path `/archive`, a drive letter, mount.
3. Without the manager: put the key at `%USERPROFILE%\.ssh\id_rsa` and in
   Explorer → Map network drive enter `\\sshfs.k\copart@grahovskiy.com`.
   SSHFS-Win looks only at that file name; OpenSSH reads the key type from the
   content, so an ed25519 key works under that name.

The drive is read-only: copying from it works, writing to it is refused.

Alternatives: `rclone mount` with WinFsp (a command that has to keep running),
or paid tools — Mountain Duck (also gives a drive in macOS Finder), SFTP Drive.

Better than passing the private key around: put the person's own public key into
`/etc/ssh/authorized_keys/copart` (one key per line).

## How it is built

- `/srv/copart-sftp/archive` is a read-only bind mount of the archive (in `/etc/fstab`),
  and `/srv/copart-sftp` is the chroot — so the account cannot see the rest of the disk.
- The user `copart` is in the group `sftponly`; the `Match Group sftponly` block in
  `/etc/ssh/sshd_config` sets `ChrootDirectory`, `ForceCommand internal-sftp -R`
  (`-R` is read-only), keys only, no forwarding. `Subsystem sftp internal-sftp`
  is required for the chroot.
- `AuthorizedKeysFile /etc/ssh/authorized_keys/%u`: the directory must be `755`
  and the file `644` — sshd reads it as the user, not as root.
- The distribution config is kept as `/etc/ssh/sshd_config.before-copart`.
