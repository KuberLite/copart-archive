# Windows access to the archive

The archive is shared over SMB **on the WireGuard interface only**. SMB must never
face the internet — it is scanned and attacked constantly. The server already runs
PiVPN, so the share lives behind it.

```
share      \\10.30.71.1\copart      read only
user       copart                   password in /root/copart-smb-password.txt (root only)
listens    10.30.71.1:445, 127.0.0.1:445 — nothing on the public address
firewall   ufw allow in on wg0 proto tcp to any port 445
```

Checked after setup: the public address refuses the connection, an anonymous
listing shows no share, and `mkdir` over the share fails with ACCESS_DENIED.

## On the Windows machine

1. Connect the WireGuard client (a PiVPN profile — `pivpn add -n <name>` on the
   server writes `/root/<name>.conf`).
2. Explorer → Map network drive → `\\10.30.71.1\copart`, user `copart`.
   Or: `net use Z: \\10.30.71.1\copart /user:copart`

## Server side

Config in `/etc/samba/smb.conf` (the distribution original is kept as
`smb.conf.original`), service `smbd`; `nmbd` is disabled — NetBIOS is not needed
for SMB2. To change the password: `smbpasswd copart`.
