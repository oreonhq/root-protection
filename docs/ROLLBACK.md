# Rollback with root-protection

Snapshots are LVM thin CoW volumes named like `vg/root-snapshotN` (snapper naming). Boom adds BLS entries under `/boot/loader/entries` that GRUB can boot.

## Bricked after a bad root command

1. Reboot
2. At GRUB, pick a `root-protection snap ...` entry from before the damage
3. Log in and confirm the system is good
4. Make it permanent:

```bash
sudo root-protection list
sudo root-protection rollback <id> --merge
sudo reboot
```

5. After merge:

```bash
sudo root-protection cleanup
sudo root-protection sync-boot
```

Note: `sudo rm -rf /usr` does not use an interactive root shell. v1.0.5+ wraps `/usr/local/bin/sudo` so that path also gets the CONFIRM prompt.

## GRUB boots a snapshot by default / everything is read-only

Snapshot boots are often read-only. That is expected when you are *in* a snap.

If GRUB keeps landing on a snap instead of the live OS:

```bash
sudo root-protection fix-boot
sudo reboot
```

v1.0.7+ also restores the live OS as GRUB default after every boom entry create.


## Temporary boot (inspect / try)

```bash
root-protection list
root-protection rollback 12
reboot
```

In GRUB pick the entry titled like `root-protection #12: ...`.

You are running on the snapshot LV as root. The original root LV is still there. Changes you make on the snapshot stay on the snapshot until you merge or discard.

When done testing, reboot back into the normal default entry.

## Permanent restore (merge)

You want the live system to become that snapshot forever:

```bash
root-protection rollback 12 --merge
reboot
```

That runs `lvconvert --merge` on the snapshot LV. After reboot LVM finishes the merge into the origin. The snapshot LV goes away.

Then:

```bash
root-protection cleanup
root-protection sync-boot
root-protection status
```

## Notes

- Keep `/boot` off the thin root LV so kernels/initrds for boom `--backup` entries survive pool pressure
- Watch thin pool fill: `root-protection health`
- Critically full pools refuse new snaps when `refuse_create_on_crit = true`
- Merge is disruptive. take a fresh snapshot of current state before merging if you might want to undo again

## Manual boom (debug)

```bash
boom profile create --from-host
boom create --backup --title "root-protection #12" --root-lv oreon/root-snapshot12
boom list
```
