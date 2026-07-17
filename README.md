# root-protection

Space-efficient system snapshots and GRUB rollback for Oreon on ext4 root with LVM thin.

This is meant to be an alternative to immutable roots in most cases. Package managers and apps keep working. You get a recoverable timeline and a soft guard against dumb interactive root mistakes.

## What it does

- CoW snapshots of `/` via snapper on LVM thin (`lvm(ext4)`)
- Daily snapshots (systemd timer) plus dnf/dnf5 pre/post transaction snapshots
- Boom boot entries so you can pick an older root from GRUB
- Thin pool health checks that refuse new snaps when the pool is critically full
- Soft intercept on interactive root shells for catastrophic commands (warn + type `CONFIRM`), never blocks dnf/rpm

## Requirements

- `/` is ext4 on an LVM thin LV
- `/boot` (and ESP) outside that thin root LV
- Packages: `snapper`, `lvm2`, `boom-boot`, `grub2-tools`, `python3`

Check first:

```bash
root-protection doctor
```

## Quick start

```bash
dnf install root-protection
root-protection doctor
root-protection enable
root-protection status
root-protection list
```

Rollback:

```bash
root-protection rollback 42          # ensure GRUB/boom entry, reboot and pick it
root-protection rollback 42 --merge  # schedule permanent merge, then reboot
```

See [docs/INSTALL.md](docs/INSTALL.md) and [docs/ROLLBACK.md](docs/ROLLBACK.md).

## License

Copyright (C) 2026 Oreon HQ. GPL-3.0. See [LICENSE](LICENSE).
