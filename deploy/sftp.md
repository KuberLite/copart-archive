# Access to the archive over SFTP

SFTP comes with SSH, so nothing extra runs on the server and it works from any OS.
The account is read-only, has no shell and is caged in a directory that holds
nothing but the archive.

```
host     grahovskiy.com   port 22
user     copart           key /root/copart-sftp-key (private, root only)
path     /archive         (the real path is /opt/copart-archive/archive)
```

Checked after setup: `mkdir` is denied, `cd /etc` leads nowhere, an interactive
login answers "This service allows sftp connections only", port forwarding is off,
and a file downloads fine.

## Clients

- **Windows** — WinSCP or FileZilla; for a drive letter, rclone with WinFsp.
- **Linux** — the file manager opens `sftp://copart@grahovskiy.com/archive`, or `sshfs`.
- **macOS** — Finder has no SFTP; Cyberduck or `sshfs`.
- **CLI** — `sftp -i key copart@grahovskiy.com`, `rsync -e ssh`, `scp`.

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
