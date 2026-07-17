#!/bin/bash
# one-shot emergency fix if package install is lagging
set -euo pipefail
LIB=/usr/libexec/root-protection
if [[ -x "$LIB/fix-grub-layout" ]]; then
  exec "$LIB/fix-grub-layout" all
fi
# inline fallback
ENTRIES=/boot/loader/entries
RP_BLS=/boot/root-protection/bls
mkdir -p "$RP_BLS"
shopt -s nullglob
for f in "$ENTRIES"/*.conf; do
  if grep -qiE 'root-protection|root-snapshot' "$f"; then
    mv -f "$f" "$RP_BLS/"
    echo "moved $(basename "$f")"
  fi
done
MID=$(tr -d '[:space:]' </etc/machine-id)
KVER=$(uname -r)
ID="${MID}-${KVER}"
if [[ ! -f "${ENTRIES}/${ID}.conf" ]]; then
  echo "missing live entry ${ENTRIES}/${ID}.conf" >&2
  ls -la "$ENTRIES" >&2
  exit 1
fi
grub2-editenv - set save_default=false
grub2-editenv - unset next_entry
grub2-editenv - set "saved_entry=${ID}"
if [[ -f /etc/default/grub ]]; then
  sed -i 's/^GRUB_DEFAULT=.*/GRUB_DEFAULT=saved/' /etc/default/grub || echo 'GRUB_DEFAULT=saved' >>/etc/default/grub
  sed -i 's/^GRUB_SAVEDEFAULT=.*/GRUB_SAVEDEFAULT=false/' /etc/default/grub || echo 'GRUB_SAVEDEFAULT=false' >>/etc/default/grub
fi
grub2-mkconfig -o /boot/grub2/grub.cfg
echo "FIXED. live=$ID"
ls -la "$ENTRIES"
ls -la "$RP_BLS"
grub2-editenv list
