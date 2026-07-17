# Installing root-protection

## Disk layout

root-protection only supports **ext4 on LVM thin** for `/`.

Required:

1. Volume group with a thin pool
2. Thin LV for root, ext4, mounted at `/`
3. Separate `/boot` (partition or thick LV) and ESP if UEFI
4. Separate `/home` recommended so user data is not in every root snap

Example (adjust sizes/names):

```bash
vgcreate oreon /dev/sda2
lvcreate -L 100G -T oreon/pool
lvcreate -V 40G -T oreon/pool -n root
lvcreate -L 1G oreon -n boot
mkfs.ext4 /dev/oreon/root
mkfs.ext4 /dev/oreon/boot
```

Wire fstab, install the OS onto that layout (Centrio / whatever Oreon installer path you use).

## Packages

```bash
dnf install root-protection
# pulls snapper, boom-boot, lvm2, etc
```

From source:

```bash
sudo make install
```

## Enable

```bash
root-protection doctor
root-protection enable
systemctl status root-protection-snapshot.timer
systemctl status root-protection-health.timer
```

`enable` will:

- refuse if doctor fails
- create snapper config `root` with `lvm(ext4)`
- apply retention from `/etc/root-protection/config.toml`
- ensure a boom OS profile exists
- take an initial snapshot and sync boom boot entries
- start daily snapshot + hourly health timers

## Config

`/etc/root-protection/config.toml`

Important knobs:

- `general.enabled`
- `retention.*` snapshot keep counts
- `health.crit_data_percent` / `refuse_create_on_crit`
- `guard.enabled`
- `dnf.pre_post_snapshots`

## Package manager hooks

- dnf5: `/etc/dnf/libdnf5-plugins/actions.d/root-protection.actions` (needs `libdnf5-plugin-actions`)
- dnf4: python plugin `root_protection` under `dnf-plugins`

Hooks never abort the transaction if a snapshot fails.

## Soft guard

`/etc/profile.d/root-protection-guard.sh` loads in interactive root shells.

- matches catastrophic patterns
- asks you to type `CONFIRM`
- `FORCE=1 command...` skips once
- dnf/rpm/yum and friends are allowlisted

Disable guard only: set `[guard] enabled = false` or `ROOT_PROTECTION_GUARD=0`.
