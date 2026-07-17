#!/bin/bash
# wrap /usr/bin/sudo so `sudo rm -rf /usr` gets the CONFIRM prompt
set -euo pipefail

REAL_SUDO=/usr/bin/sudo
LIB=/usr/libexec/root-protection/guard-lib.sh

# avoid recursion if somehow PATH points at us again
if [[ "$(readlink -f "$0" 2>/dev/null || echo "$0")" == "$(readlink -f "$REAL_SUDO" 2>/dev/null || true)" ]]; then
  echo "root-protection: sudo wrapper misinstalled" >&2
  exit 125
fi

if [[ -f "$LIB" ]]; then
  # shellcheck disable=SC1090
  . "$LIB"
  # only inspect when next token looks like a real command (skip sudo flags)
  args=("$@")
  idx=0
  while [[ $idx -lt ${#args[@]} ]]; do
    a="${args[$idx]}"
    case "$a" in
      --)
        idx=$((idx + 1))
        break
        ;;
      -*)
        # sudo options that take an argument
        case "$a" in
          -u|--user|-g|--group|-h|--host|-p|--prompt|-r|--role|-t|--type|-C|--close-from|-D|--chdir|-R|--chroot)
            idx=$((idx + 2))
            continue
            ;;
        esac
        idx=$((idx + 1))
        continue
        ;;
      *)
        break
        ;;
    esac
  done
  if [[ $idx -lt ${#args[@]} ]]; then
    cmd_args=("${args[@]:$idx}")
    if ! _rp_guard_check_argv "${cmd_args[@]}"; then
      exit 1
    fi
  fi
fi

exec "$REAL_SUDO" "$@"
