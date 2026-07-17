#!/usr/bin/awk -f
# usage: rp-conf-get section key /path/to/config.toml
BEGIN {
  section = ARGV[1]; key = ARGV[2]; delete ARGV[1]; delete ARGV[2]
  insec = 0
}
$0 ~ "^\\[" section "\\]" { insec = 1; next }
/^\[/ { insec = 0; next }
insec && $0 ~ "^[[:space:]]*" key "[[:space:]]*=" {
  sub(/^[^=]*=[[:space:]]*/, "")
  gsub(/^"/, ""); gsub(/"$/, "")
  print
  exit
}
