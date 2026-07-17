#!/bin/bash
# root-protection soft guard for interactive root shells
# sourced from /etc/profile.d/root-protection-guard.sh

# shellcheck disable=SC1091
[[ -f /usr/libexec/root-protection/guard-lib.sh ]] && . /usr/libexec/root-protection/guard-lib.sh

_rp_is_interactive_root() {
  [[ "${EUID:-$(id -u)}" -eq 0 ]] || return 1
  [[ -t 0 && -t 1 ]] || return 1
  case "$-" in
    *i*) return 0 ;;
    *) return 1 ;;
  esac
}

_rp_line_dangerous() {
  local line low
  line="$1"
  low=$(tr '[:upper:]' '[:lower:]' <<<"$line")
  low=${low#sudo }
  # turn the line into fake argv for shared checker when possible
  # fallback to substring match
  case "$low" in
    *"rm -rf /"*|*"rm -fr /"*|*"rm --no-preserve-root"*) return 0 ;;
    *"rm -rf /usr"*|*"rm -rf /etc"*|*"rm -rf /boot"*|*"rm -rf /var"*) return 0 ;;
    *"rm -rf /lib"*|*"rm -rf /bin"*|*"rm -rf /sbin"*|*"rm -rf /opt"*) return 0 ;;
    *"mkfs /"*|*"mkfs.ext4 /dev/"*|*"mkfs.xfs /dev/"*|*"mkfs.btrfs /dev/"*) return 0 ;;
    *"dd if="*"of=/dev/"*) return 0 ;;
    *"wipefs"*|*"sgdisk --zap"*|*"shred /dev/"*) return 0 ;;
  esac
  return 1
}

root_protection_preexec() {
  local line="${1:-}"
  [[ -n "$line" ]] || return 0
  type _rp_guard_enabled &>/dev/null || return 0
  _rp_guard_enabled || return 0
  _rp_is_interactive_root || return 0
  # shellcheck disable=SC2086
  if _rp_allowlisted_cmd $(awk '{print $1}' <<<"$line"); then
    return 0
  fi
  if _rp_line_dangerous "$line"; then
    _rp_confirm "$line" || return 1
  fi
  return 0
}

if _rp_is_interactive_root 2>/dev/null; then
  if [[ -n "${BASH_VERSION:-}" ]]; then
    _rp_debug_trap() {
      root_protection_preexec "$BASH_COMMAND" || return 1
    }
    shopt -s extdebug 2>/dev/null || true
    trap '_rp_debug_trap' DEBUG
  fi
fi
