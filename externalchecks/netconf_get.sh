#!/bin/bash
# Zabbix external check: netconf_get.sh[host,user,password,xpath_or_filter]
#
# Returns a single string (or number) from a NETCONF <get> reply.
# Requires ncclient on the Zabbix server host — this script is a stub that
# delegates to the Python helper when available in /scripts or PATH.
#
# In this lab compose, prefer running probes from zabbix-netconf-tools,
# or install ncclient into a custom zabbix-server image for true external checks.
#
# Args:
#   $1 host
#   $2 username
#   $3 password
#   $4 xpath (optional; default: system name style filter)

set -euo pipefail

HOST="${1:?host required}"
USER="${2:?user required}"
PASS="${3:?password required}"
XPATH="${4:-/}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
HELPER="${SCRIPT_DIR}/../scripts/netconf_probe.py"

if [[ -x /usr/bin/python3 ]] || command -v python3 >/dev/null 2>&1; then
  PY=python3
else
  echo "ZBX_NOTSUPPORTED: python3 not available for NETCONF probe"
  exit 1
fi

if [[ ! -f "$HELPER" ]]; then
  # When mounted only at /usr/lib/zabbix/externalscripts, helper may be missing
  HELPER="/scripts/netconf_probe.py"
fi

if [[ ! -f "$HELPER" ]]; then
  echo "ZBX_NOTSUPPORTED: netconf_probe.py not found"
  exit 1
fi

export NETCONF_HOST="$HOST"
export NETCONF_USER="$USER"
export NETCONF_PASSWORD="$PASS"
export NETCONF_XPATH="$XPATH"

exec "$PY" "$HELPER" --host "$HOST" --user "$USER" --password "$PASS" --xpath "$XPATH"
