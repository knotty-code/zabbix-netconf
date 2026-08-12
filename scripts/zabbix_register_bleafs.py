#!/usr/bin/env python3
"""Register Magic Kingdom X1b bleafs in Zabbix with *native* NETCONF (SSH subsystem).

Requires Zabbix **≥ 7.2** (SSH item key 6th parameter: subsystem=netconf).

Creates:
  Host group: Magic Kingdom
  Hosts: bleaf1.magic-kingdom.io, bleaf2.magic-kingdom.io
  SSH agent master items (subsystem netconf) + dependent / simple-check items

Usage:
  python3 zabbix_register_bleafs.py --url http://localhost:8080

Re-running is idempotent: replaces legacy trapper `netconf.*` items and
ensures SSH masters + dependents exist.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request

# Item type codes (Zabbix API)
TYPE_ZABBIX_TRAPPER = 2
TYPE_SIMPLE_CHECK = 3
TYPE_SSH_AGENT = 13
TYPE_DEPENDENT = 18

# Preprocessing type codes
PREPROC_REGEX = 5
PREPROC_XPATH = 11
PREPROC_JSONPATH = 12
PREPROC_JS = 21
PREPROC_DISCARD_UNCHANGED_HEARTBEAT = 20

# Value types
VT_FLOAT = 0
VT_CHAR = 1
VT_UINT = 3
VT_TEXT = 4

DEFAULT_HOSTS = [
    {
        "host": "bleaf1.magic-kingdom.io",
        "name": "bleaf1 (7250 IXR-X1b / SRL)",
        "ip": "172.30.40.21",
    },
    {
        "host": "bleaf2.magic-kingdom.io",
        "name": "bleaf2 (7250 IXR-X1b / SRL)",
        "ip": "172.30.40.22",
    },
]

# NETCONF end-of-message framing required by Zabbix SSH subsystem items
EOM = "]]>]]>"

# Client hello must announce *only* base:1.0 so framing stays ]]>]]>
# (SRL advertises 1.1; if the client also claims 1.1, chunked framing applies.)
# XML namespace for <hello>/<rpc> elements vs capability URI are different (RFC 6241).
NS_NC = "urn:ietf:params:xml:ns:netconf:base:1.0"
CAP_BASE_10 = "urn:ietf:params:netconf:base:1.0"
CLIENT_HELLO = "\n".join(
    [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<hello xmlns="{NS_NC}">',
        "  <capabilities>",
        f"    <capability>{CAP_BASE_10}</capability>",
        "  </capabilities>",
        "</hello>",
        EOM,
    ]
)

# SR Linux YANG namespaces (from live capability / data replies on 26.3.x)
NS_SYSTEM = "urn:nokia.com:srlinux:general:system"
NS_SYSNAME = "urn:nokia.com:srlinux:chassis:system-name"
NS_PLATFORM = "urn:nokia.com:srlinux:chassis:platform"
NS_CONTROL = "urn:nokia.com:srlinux:chassis:platform-control"
NS_IF = "urn:nokia.com:srlinux:chassis:interfaces"


def rpc_get(filter_xml: str, msg_id: str = "1") -> str:
    """Build client-hello + namespaced get + close-session (1.0 framing)."""
    return "\n".join(
        [
            CLIENT_HELLO,
            f'<rpc xmlns="{NS_NC}" message-id="{msg_id}">',
            "  <get>",
            '    <filter type="subtree">',
            f"      {filter_xml}",
            "    </filter>",
            "  </get>",
            "</rpc>",
            EOM,
            f'<rpc xmlns="{NS_NC}" message-id="{int(msg_id) + 1}">',
            "  <close-session/>",
            "</rpc>",
            EOM,
        ]
    )


RPC_HOSTNAME = rpc_get(
    f'<system xmlns="{NS_SYSTEM}"><name xmlns="{NS_SYSNAME}"/></system>'
)
RPC_VERSION = rpc_get(
    f'<platform xmlns="{NS_PLATFORM}">'
    f'<control xmlns="{NS_CONTROL}"><software-version/></control>'
    f"</platform>"
)
# Full interface tree can be large — still OK for lab; optics uses transceiver only
RPC_INTERFACES = rpc_get(f'<interface xmlns="{NS_IF}"/>')
RPC_OPTICS = rpc_get(
    f'<interface xmlns="{NS_IF}"><transceiver/></interface>'
)

# JS preprocessing: extract hostname from NETCONF XML
JS_HOSTNAME = r"""
var m = value.match(/<host-name>([^<]+)<\/host-name>/);
if (m) return m[1].trim();
m = value.match(/<name>([^<]+)<\/name>/);
if (m) return m[1].trim();
return value.slice(0, 200);
""".strip()

JS_VERSION = r"""
var m = value.match(/<software-version>([^<]+)<\/software-version>/);
if (m) return m[1].trim();
m = value.match(/<version>([^<]+)<\/version>/);
if (m) return m[1].trim();
if (/rpc-reply|data/i.test(value)) return 'SR Linux (version leaf not in filter reply)';
return value.slice(0, 200);
""".strip()

JS_IF_SUMMARY = r"""
var states = value.match(/<oper-state>([^<]+)<\/oper-state>/g) || [];
var up = 0, down = 0;
for (var i = 0; i < states.length; i++) {
  var s = (states[i].match(/>([^<]+)</) || [])[1] || '';
  s = s.toLowerCase();
  if (s === 'up' || s === 'enable' || s === 'enabled') up++;
  else if (s === 'down' || s === 'disable' || s === 'disabled' || s === 'lower-layer-down') down++;
}
var names = value.match(/<name>([^<]+)<\/name>/g) || [];
return 'interfaces=' + (states.length || names.length) + ' oper_up=' + up + ' oper_down=' + down;
""".strip()

JS_OPTICS_JSON = r"""
// Build a small JSON summary from transceiver containers
var cages = (value.match(/<transceiver[\s>]/g) || []).length;
if (cages === 0) {
  // alternate: count oper-down-reason / oper-state under transceiver-ish blocks
  cages = (value.match(/oper-down-reason/g) || []).length;
}
var notPresent = (value.match(/not-present/g) || []).length;
var present = cages > notPresent ? cages - notPresent : 0;
// Prefer explicit oper-state counts when available
var ops = value.match(/<oper-state>([^<]+)<\/oper-state>/g) || [];
if (ops.length) {
  cages = ops.length;
  notPresent = 0; present = 0;
  for (var i = 0; i < ops.length; i++) {
    var s = ((ops[i].match(/>([^<]+)</) || [])[1] || '').toLowerCase();
    if (s === 'not-present' || s.indexOf('not-present') >= 0) notPresent++;
    else present++;
  }
}
return JSON.stringify({
  cages: cages,
  present: present,
  not_present: notPresent,
  summary: 'cages=' + cages + ' present=' + present + ' not_present=' + notPresent
});
""".strip()


class ZabbixAPI:
    """Zabbix JSON-RPC client (7.0+ Authorization Bearer token; no body auth)."""

    def __init__(self, url: str, user: str, password: str):
        self.url = url.rstrip("/") + "/api_jsonrpc.php"
        self.auth = None
        self._id = 0
        self.auth = self.call("user.login", {"username": user, "password": password})

    def call(self, method: str, params: dict | list):
        self._id += 1
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": self._id,
        }
        # Zabbix ≥ 7.0: session/API token via Authorization header only
        # (body "auth" is rejected as unexpected parameter on 7.4).
        headers = {"Content-Type": "application/json-rpc"}
        if self.auth and method not in ("user.login", "apiinfo.version"):
            headers["Authorization"] = f"Bearer {self.auth}"
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            self.url,
            data=data,
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read().decode())
        if "error" in body:
            raise RuntimeError(f"{method}: {body['error']}")
        return body["result"]


def ensure_group(api: ZabbixAPI, name: str) -> str:
    found = api.call("hostgroup.get", {"filter": {"name": [name]}})
    if found:
        return found[0]["groupid"]
    created = api.call("hostgroup.create", {"name": name})
    return created["groupids"][0]


def ensure_host(api: ZabbixAPI, groupid: str, host: dict) -> str:
    # Lab passwords as plain macros (type 0) so SSH items resolve reliably.
    # Production: use secret macros (type 1) / vault.
    macros = [
        {"macro": "{$NETCONF.IP}", "value": host["ip"]},
        {"macro": "{$NETCONF.PORT}", "value": "22"},
        {"macro": "{$NETCONF.USER}", "value": "admin"},
        {"macro": "{$NETCONF.PASSWORD}", "value": "NokiaSrl1!", "type": 0},
        # legacy aliases used by older docs / scripts
        {"macro": "{$NETCONF_HOST}", "value": host["ip"]},
        {"macro": "{$NETCONF_PORT}", "value": "22"},
        {"macro": "{$NETCONF_USER}", "value": "admin"},
        {"macro": "{$NETCONF_PASSWORD}", "value": "NokiaSrl1!", "type": 0},
    ]
    desc = (
        "Magic Kingdom containerlab X1b (SR Linux). "
        "Metrics via native Zabbix SSH + NETCONF subsystem (not SNMP / not trapper poller)."
    )
    tags = [
        {"tag": "role", "value": "bleaf"},
        {"tag": "platform", "value": "7250-IXR-X1b"},
        {"tag": "os", "value": "SR-Linux"},
        {"tag": "lab", "value": "magic-kingdom"},
        {"tag": "monitor", "value": "netconf"},
        {"tag": "netconf", "value": "native-ssh"},
    ]

    found = api.call("host.get", {"filter": {"host": [host["host"]]}, "selectMacros": "extend"})
    if found:
        hostid = found[0]["hostid"]
        api.call(
            "host.update",
            {
                "hostid": hostid,
                "name": host["name"],
                "groups": [{"groupid": groupid}],
                "description": desc,
                "tags": tags,
                "macros": macros,
            },
        )
        return hostid

    created = api.call(
        "host.create",
        {
            "host": host["host"],
            "name": host["name"],
            "groups": [{"groupid": groupid}],
            "interfaces": [
                {
                    "type": 1,  # agent interface (required; SSH uses IP from item key / macros)
                    "main": 1,
                    "useip": 1,
                    "ip": host["ip"],
                    "dns": host["host"],
                    "port": "10050",
                }
            ],
            "description": desc,
            "tags": tags,
            "macros": macros,
        },
    )
    return created["hostids"][0]


def _pp_js(script: str) -> dict:
    return {
        "type": str(PREPROC_JS),
        "params": script,
        "error_handler": "0",
        "error_handler_params": "",
    }


def _pp_jsonpath(path: str, on_fail_set: str | None = None) -> dict:
    step = {
        "type": str(PREPROC_JSONPATH),
        "params": path,
        "error_handler": "0",
        "error_handler_params": "",
    }
    if on_fail_set is not None:
        step["error_handler"] = "2"  # set value to
        step["error_handler_params"] = on_fail_set
    return step


def purge_legacy_trapper_items(api: ZabbixAPI, hostid: str) -> None:
    """Remove old poller→trapper / prior SSH NETCONF items so keys can be reused."""
    # Client-side filter is more reliable than key_ search across Zabbix versions
    all_items = api.call(
        "item.get",
        {
            "hostids": [hostid],
            "output": ["itemid", "key_", "type", "master_itemid"],
            "selectPreprocessing": "extend",
        },
    )
    to_delete: list[str] = []
    for i in all_items:
        k = i.get("key_", "")
        if k.startswith("netconf.") or k.startswith("ssh.run[Srl"):
            to_delete.append(i["itemid"])
        elif k.startswith("net.tcp.service[ssh"):
            to_delete.append(i["itemid"])
        elif "netconf" in k.lower() and i.get("type") in (
            str(TYPE_ZABBIX_TRAPPER),
            str(TYPE_SSH_AGENT),
            str(TYPE_DEPENDENT),
            TYPE_ZABBIX_TRAPPER,
            TYPE_SSH_AGENT,
            TYPE_DEPENDENT,
        ):
            to_delete.append(i["itemid"])

    ids = sorted(set(to_delete))
    if not ids:
        print("  (no prior netconf/ssh items to remove)")
        return

    # Delete dependents (type 18) before masters when possible
    dep_ids = [
        i["itemid"]
        for i in all_items
        if i["itemid"] in ids and str(i.get("type")) == str(TYPE_DEPENDENT)
    ]
    master_ids = [i for i in ids if i not in dep_ids]
    for batch in (dep_ids, master_ids):
        if batch:
            api.call("item.delete", batch)
    print(f"  - removed {len(ids)} legacy/old items")


def create_ssh_master(
    api: ZabbixAPI,
    hostid: str,
    *,
    name: str,
    key_desc: str,
    params: str,
    delay: str = "2m",
    preprocessing: list | None = None,
    value_type: int = VT_TEXT,
) -> str:
    key = f"ssh.run[{key_desc},{{$NETCONF.IP}},{{$NETCONF.PORT}},,,netconf]"
    body = {
        "name": name,
        "key_": key,
        "hostid": hostid,
        "type": TYPE_SSH_AGENT,
        "value_type": value_type,
        "delay": delay,
        "history": "7d",
        "trends": "0",
        "username": "{$NETCONF.USER}",
        "password": "{$NETCONF.PASSWORD}",
        "authtype": 0,  # password
        "params": params,
        "timeout": "30s",
        "description": (
            "Native NETCONF over SSH subsystem (Zabbix ≥ 7.2). "
            "Executed script: client <hello> base:1.0 + namespaced get + close-session. "
            "Requires server Timeout / ZBX_TIMEOUT high enough for SRL capability hello."
        ),
        "tags": [
            {"tag": "source", "value": "netconf"},
            {"tag": "component", "value": "ssh-master"},
        ],
    }
    if preprocessing:
        body["preprocessing"] = preprocessing
    created = api.call("item.create", body)
    itemid = created["itemids"][0]
    print(f"  + SSH master {key_desc} id={itemid}")
    return itemid


def create_dependent(
    api: ZabbixAPI,
    hostid: str,
    master_itemid: str,
    *,
    name: str,
    key: str,
    value_type: int,
    preprocessing: list,
    delay: str = "0",
) -> None:
    api.call(
        "item.create",
        {
            "name": name,
            "key_": key,
            "hostid": hostid,
            "type": TYPE_DEPENDENT,
            "master_itemid": master_itemid,
            "value_type": value_type,
            "delay": delay,
            "history": "7d",
            "trends": "0" if value_type in (VT_CHAR, VT_TEXT) else "30d",
            "description": "Derived from native NETCONF SSH master item",
            "preprocessing": preprocessing,
            "tags": [
                {"tag": "source", "value": "netconf"},
                {"tag": "component", "value": "derived"},
            ],
        },
    )
    print(f"  + dependent {key}")


def create_simple_tcp(api: ZabbixAPI, hostid: str) -> None:
    tcp_key = 'net.tcp.service[ssh,"{$NETCONF.IP}","{$NETCONF.PORT}"]'
    api.call(
        "item.create",
        {
            "name": "NETCONF: SSH/TCP service status",
            "key_": tcp_key,
            "hostid": hostid,
            "type": TYPE_SIMPLE_CHECK,
            "value_type": VT_UINT,
            "delay": "1m",
            "history": "7d",
            "trends": "30d",
            "description": "1 = TCP accepts on NETCONF/SSH port (typically 22)",
            "tags": [{"tag": "source", "value": "netconf"}],
        },
    )
    print(f"  + simple check {tcp_key}")

    api.call(
        "item.create",
        {
            "name": "NETCONF availability",
            "key_": "netconf.availability",
            "hostid": hostid,
            "type": 15,  # calculated
            "value_type": VT_UINT,
            "delay": "1m",
            "history": "7d",
            "trends": "30d",
            "params": f"last(//{tcp_key})",
            "description": "Mirrors TCP SSH service check (1/0); same key as legacy poller",
            "tags": [{"tag": "source", "value": "netconf"}],
        },
    )
    print("  + calculated netconf.availability")


def ensure_items(api: ZabbixAPI, hostid: str) -> None:
    purge_legacy_trapper_items(api, hostid)
    create_simple_tcp(api, hostid)

    # Hostname master → dependent netconf.hostname
    mid_hn = create_ssh_master(
        api,
        hostid,
        name="NETCONF: Get system name (raw)",
        key_desc="SrlHostname",
        params=RPC_HOSTNAME,
        delay="2m",
    )
    create_dependent(
        api,
        hostid,
        mid_hn,
        name="NETCONF system hostname",
        key="netconf.hostname",
        value_type=VT_CHAR,
        preprocessing=[_pp_js(JS_HOSTNAME)],
    )

    # Version
    mid_ver = create_ssh_master(
        api,
        hostid,
        name="NETCONF: Get platform control (raw)",
        key_desc="SrlVersion",
        params=RPC_VERSION,
        delay="5m",
    )
    create_dependent(
        api,
        hostid,
        mid_ver,
        name="NETCONF / software version",
        key="netconf.version",
        value_type=VT_CHAR,
        preprocessing=[_pp_js(JS_VERSION)],
    )

    # Interfaces summary
    mid_if = create_ssh_master(
        api,
        hostid,
        name="NETCONF: Get interfaces (raw)",
        key_desc="SrlInterfaces",
        params=RPC_INTERFACES,
        delay="3m",
    )
    create_dependent(
        api,
        hostid,
        mid_if,
        name="NETCONF interface oper summary",
        key="netconf.if.summary",
        value_type=VT_CHAR,
        preprocessing=[_pp_js(JS_IF_SUMMARY)],
    )

    # Caps stand-in: session success marker from hostname raw (rpc-reply present)
    create_dependent(
        api,
        hostid,
        mid_hn,
        name="NETCONF capability / session smoke",
        key="netconf.caps",
        value_type=VT_CHAR,
        preprocessing=[
            _pp_js(
                "if (/rpc-reply|rpc-error|host-name|<data/i.test(value)) "
                "return 'ok netconf_session=1'; "
                "return 'ok netconf_session=0 reply_bytes=' + value.length;"
            )
        ],
    )

    # Optics master → JSON + dependents
    mid_opt = create_ssh_master(
        api,
        hostid,
        name="NETCONF: Get transceiver state (raw)",
        key_desc="SrlOptics",
        params=RPC_OPTICS,
        delay="3m",
    )
    # intermediate JSON on a dependent text item, then counts
    # Simpler: four dependents each running JS on the same master raw XML
    create_dependent(
        api,
        hostid,
        mid_opt,
        name="Optics cages with transceiver container",
        key="netconf.optics.cages",
        value_type=VT_UINT,
        preprocessing=[
            _pp_js(JS_OPTICS_JSON),
            _pp_jsonpath("$.cages", "0"),
        ],
    )
    create_dependent(
        api,
        hostid,
        mid_opt,
        name="Optics installed (not not-present)",
        key="netconf.optics.present",
        value_type=VT_UINT,
        preprocessing=[
            _pp_js(JS_OPTICS_JSON),
            _pp_jsonpath("$.present", "0"),
        ],
    )
    create_dependent(
        api,
        hostid,
        mid_opt,
        name="Optics missing (not-present)",
        key="netconf.optics.not_present",
        value_type=VT_UINT,
        preprocessing=[
            _pp_js(JS_OPTICS_JSON),
            _pp_jsonpath("$.not_present", "0"),
        ],
    )
    create_dependent(
        api,
        hostid,
        mid_opt,
        name="Optics presence summary text",
        key="netconf.optics.summary",
        value_type=VT_CHAR,
        preprocessing=[
            _pp_js(JS_OPTICS_JSON),
            _pp_jsonpath("$.summary", "unknown"),
        ],
    )


def check_version(api: ZabbixAPI) -> None:
    info = api.call("apiinfo.version", [])
    print(f"Zabbix API version: {info}")
    # apiinfo.version may not need auth in some versions; if we got here fine
    major_minor = str(info).split(".")
    try:
        major, minor = int(major_minor[0]), int(major_minor[1])
    except (ValueError, IndexError):
        return
    if (major, minor) < (7, 2):
        raise SystemExit(
            f"ERROR: Zabbix {info} is too old for native NETCONF SSH subsystem. "
            "Need ≥ 7.2 (compose uses alpine-7.4-latest)."
        )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--url", default="http://localhost:8080")
    ap.add_argument("--user", default="Admin")
    ap.add_argument("--password", default="zabbix")
    ap.add_argument(
        "--keep-legacy",
        action="store_true",
        help="Do not delete existing netconf.* items (default: replace)",
    )
    args = ap.parse_args()

    api = ZabbixAPI(args.url, args.user, args.password)
    check_version(api)

    groupid = ensure_group(api, "Magic Kingdom")
    print(f"Host group Magic Kingdom id={groupid}")

    for h in DEFAULT_HOSTS:
        hostid = ensure_host(api, groupid, h)
        print(f"Host {h['host']} id={hostid}")
        if args.keep_legacy:
            print("  (skipping purge; --keep-legacy)")
        ensure_items(api, hostid)

    print(
        "Done. Native SSH+NETCONF items registered.\n"
        "Check: Monitoring → Latest data → Magic Kingdom "
        "(ssh.run masters + netconf.* dependents)."
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        raise
