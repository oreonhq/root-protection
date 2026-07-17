#!/bin/bash
# shared soft-guard helpers for root-protection

_rp_guard_conf=/etc/root-protection/config.toml

_rp_guard_enabled() {
  local conf="${_rp_guard_conf}"
  [[ -f "$conf" ]] || return 1
  [[ "${ROOT_PROTECTION_GUARD:-1}" != "0" ]] || return 1
  awk '
    BEGIN { gen=0; guard=1; in_g=0; in_guard=0 }
    /^\[general\]/ { in_g=1; in_guard=0; next }
    /^\[guard\]/ { in_guard=1; in_g=0; next }
    /^\[/ { in_g=0; in_guard=0; next }
    in_g && /^[[:space:]]*enabled[[:space:]]*=[[:space:]]*true/ { gen=1 }
    in_g && /^[[:space:]]*enabled[[:space:]]*=[[:space:]]*false/ { gen=0 }
    in_guard && /^[[:space:]]*enabled[[:space:]]*=[[:space:]]*true/ { guard=1 }
    in_guard && /^[[:space:]]*enabled[[:space:]]*=[[:space:]]*false/ { guard=0 }
    END { exit !(gen && guard) }
  ' "$conf"
}

_rp_log_guard() {
  local msg="$1"
  local log=/var/log/root-protection/guard.log
  mkdir -p /var/log/root-protection 2>/dev/null || true
  printf '%s %s\n' "$(date -Is 2>/dev/null || date)" "$msg" >>"$log" 2>/dev/null || true
  logger -t root-protection-guard "$msg" 2>/dev/null || true
}

_rp_allowlisted_cmd() {
  local first="$1"
  first=${first##*/}
  case "$first" in
    dnf|dnf5|yum|rpm|pkcon|packagekitd|snapper|boom|root-protection|lvcreate|lvremove|lvconvert|lvchange|vgchange|systemctl|journalctl)
      return 0
      ;;
  esac
  return 1
}

# argv as separate words: check catastrophic sudo/root ops
_rp_argv_dangerous() {
  local low joined cmd
  joined=$(printf '%s ' "$@" | tr '[:upper:]' '[:lower:]')
  joined=${joined%% }
  cmd=${1##*/}
  cmd=$(tr '[:upper:]' '[:lower:]' <<<"$cmd")

  case "$cmd" in
    rm)
      # rm -rf /usr  |  rm -rf --no-preserve-root /
      if [[ "$joined" == *"--no-preserve-root"* ]]; then
        return 0
      fi
      if [[ "$joined" != *" -r"* && "$joined" != *"-r "* && "$joined" != *"-rf"* && "$joined" != *"-fr"* && "$joined" != *" --recursive"* ]]; then
        return 1
      fi
      case "$joined" in
        *" / "*|*" /"|*" /usr"*|*" /etc"*|*" /boot"*|*" /var"*|*" /lib"*|*" /bin"*|*" /sbin"*|*" /opt"*|*" /*"*)
          return 0
          ;;
      esac
      ;;
    mkfs|mkfs.ext4|mkfs.xfs|mkfs.btrfs)
      return 0
      ;;
    dd)
      [[ "$joined" == *"of=/dev/"* ]] && return 0
      ;;
    wipefs|sgdisk|shred)
      return 0
      ;;
  esac
  return 1
}

_rp_confirm() {
  local line="$1"
  if [[ "${FORCE:-0}" == "1" ]]; then
    _rp_log_guard "FORCE allow: $line"
    return 0
  fi
  if [[ ! -t 0 || ! -t 2 ]]; then
    _rp_log_guard "blocked non-tty: $line"
    echo "root-protection: blocked catastrophic command (no TTY for CONFIRM): $line" >&2
    echo "re-run in a real terminal, or FORCE=1 if you mean it" >&2
    return 1
  fi
  echo "root-protection: this looks catastrophic:" >&2
  echo "  $line" >&2
  echo "type CONFIRM to continue, or anything else to abort." >&2
  echo "set FORCE=1 to skip this check once." >&2
  local ans
  read -r ans || return 1
  if [[ "$ans" == "CONFIRM" ]]; then
    _rp_log_guard "confirmed: $line"
    return 0
  fi
  _rp_log_guard "blocked: $line"
  echo "root-protection: aborted" >&2
  return 1
}

_rp_guard_check_argv() {
  local line
  _rp_guard_enabled || return 0
  _rp_allowlisted_cmd "${1:-}" && return 0
  if _rp_argv_dangerous "$@"; then
    line=$(printf '%s ' "$@")
    line=${line%% }
    _rp_confirm "$line" || return 1
  fi
  return 0
}
