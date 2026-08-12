#!/usr/bin/env python3
"""NETCONF probe for Zabbix / lab — tuned for Nokia SR Linux (X1b) and generic NETCONF.

SR Linux containerlab notes
---------------------------
* NETCONF rides SSH subsystem on **port 22** (not 830) when
  `system netconf-server <name> { admin-state enable; ssh-server <ssh>; }` is set.
* Lab credentials: admin / NokiaSrl1!
* Prefer small subtree filters — unfiltered <get> can be 10+ MB.

Examples
--------
  # Connectivity / capability count
  python3 netconf_probe.py --host 172.30.50.11 --user admin --password 'NokiaSrl1!' \\
      --port 22 --mode caps

  # Hostname via SR Linux native YANG subtree
  python3 netconf_probe.py --host srl1 --user admin --password 'NokiaSrl1!' \\
      --port 22 --mode hostname

  # Interface oper-state summary (count up/down)
  python3 netconf_probe.py --host 172.30.50.11 --user admin --password 'NokiaSrl1!' \\
      --port 22 --mode if-summary
"""
from __future__ import annotations

import argparse
import re
import sys
import traceback
import xml.etree.ElementTree as ET


def _connect(args):
    from ncclient import manager

    return manager.connect(
        host=args.host,
        port=args.port,
        username=args.user,
        password=args.password,
        hostkey_verify=args.hostkey_verify,
        device_params={"name": "default"},
        timeout=args.timeout,
        allow_agent=False,
        look_for_keys=False,
    )


def _local(tag: str) -> str:
    """Strip XML namespace from tag."""
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag


def mode_caps(m) -> str:
    caps = list(m.server_capabilities)
    return f"ok capabilities={len(caps)}"


def mode_hostname(m) -> str:
    """Fetch SR Linux system name (host-name)."""
    # Subtree filter — namespace varies by SRL release; try native srl_nokia
    filters = [
        """<system xmlns="urn:srl_nokia/system"><name/></system>""",
        """<system xmlns="urn:srl_nokia/system:system"><name/></system>""",
        """<system><name/></system>""",
    ]
    last_err = None
    for f in filters:
        try:
            reply = m.get(filter=("subtree", f))
            xml = reply.data_xml
            # Find host-name or name text
            root = ET.fromstring(xml)
            for el in root.iter():
                if _local(el.tag) in ("host-name", "hostname", "name") and el.text:
                    # Prefer host-name
                    if _local(el.tag) == "host-name":
                        return el.text.strip()
            # second pass any name under system
            for el in root.iter():
                if _local(el.tag) == "host-name" and el.text:
                    return el.text.strip()
            # fallback: first non-empty host-name-like
            mobj = re.search(r"<host-name>([^<]+)</host-name>", xml)
            if mobj:
                return mobj.group(1).strip()
            last_err = f"no host-name in reply ({len(xml)} bytes)"
        except Exception as e:
            last_err = f"{type(e).__name__}: {e}"
            continue
    raise RuntimeError(last_err or "hostname fetch failed")


def mode_if_summary(m) -> str:
    """Count ethernet interfaces by oper-state from a limited subtree."""
    filt = """<interface xmlns="urn:srl_nokia/interfaces"/>"""
    try:
        reply = m.get(filter=("subtree", filt))
    except Exception:
        # broader fallback
        reply = m.get(filter=("subtree", "<interface/>"))
    xml = reply.data_xml
    # oper-state values
    states = re.findall(r"<oper-state>([^<]+)</oper-state>", xml)
    # also match names to count interfaces
    names = re.findall(r"<name>([^<]+)</name>", xml)
    # Heuristic: ethernet interfaces often named ethernet-* or e*-*
    eth_names = [n for n in names if n.startswith("ethernet-") or re.match(r"e\d+-\d+", n)]
    up = sum(1 for s in states if s.lower() in ("up", "enable", "enabled"))
    down = sum(1 for s in states if s.lower() in ("down", "disable", "disabled", "lower-layer-down"))
    total = len(states) if states else len(eth_names)
    return f"interfaces={total} oper_up={up} oper_down={down}"


def mode_version(m) -> str:
    """Best-effort software version from platform/control or app banner."""
    # Try without forcing a specific YANG URN (SRL is picky about namespaces)
    candidates = [
        """<platform><control><software-version/></control></platform>""",
        """<platform><control/></platform>""",
        """<system><app-management><application><name>sr_linux</name></application></app-management></system>""",
    ]
    xml = ""
    for filt in candidates:
        try:
            reply = m.get(filter=("subtree", filt))
            xml = reply.data_xml or ""
            ver = re.search(r"<software-version>([^<]+)</software-version>", xml)
            if ver:
                return ver.group(1).strip()
            ver = re.search(r"<version>([^<]+)</version>", xml)
            if ver:
                return ver.group(1).strip()
        except Exception:
            continue
    # Capabilities often include software build strings; fall back to fixed lab known version
    for c in m.server_capabilities:
        s = str(c)
        if "srl_nokia" in s and "revision=" in s:
            # not version, skip
            pass
    if xml:
        one = " ".join(xml.split())
        return one[:200] if one else "unknown"
    return "SR Linux (version leaf unavailable via NETCONF filter)"


def mode_get(m, xpath: str) -> str:
    try:
        reply = m.get(filter=("xpath", xpath))
    except Exception:
        reply = m.get(filter=("subtree", xpath if xpath.startswith("<") else f"<{xpath.strip('/')}>"))
    text = reply.data_xml if hasattr(reply, "data_xml") else str(reply)
    one_line = " ".join(text.split())
    if len(one_line) > 8000:
        one_line = one_line[:8000] + "…"
    return one_line or "empty"


def mode_get_config(m) -> str:
    reply = m.get_config(source="running")
    text = reply.data_xml if hasattr(reply, "data_xml") else str(reply)
    # size only for safety
    return f"running_config_bytes={len(text)}"


def main() -> int:
    p = argparse.ArgumentParser(description="NETCONF probe for Zabbix lab (SR Linux aware)")
    p.add_argument("--host", required=True)
    p.add_argument("--port", type=int, default=22, help="SSH/NETCONF port (SRL lab uses 22)")
    p.add_argument("--user", required=True)
    p.add_argument("--password", required=True)
    p.add_argument(
        "--mode",
        choices=("caps", "hostname", "if-summary", "version", "get", "get-config"),
        default="caps",
    )
    p.add_argument("--xpath", default="/")
    p.add_argument("--timeout", type=int, default=30)
    p.add_argument("--hostkey-verify", action="store_true")
    args = p.parse_args()

    try:
        from ncclient import manager  # noqa: F401
    except ImportError:
        print("ZBX_NOTSUPPORTED: ncclient not installed (pip install ncclient)")
        return 1

    try:
        with _connect(args) as m:
            if args.mode == "caps":
                print(mode_caps(m))
            elif args.mode == "hostname":
                print(mode_hostname(m))
            elif args.mode == "if-summary":
                print(mode_if_summary(m))
            elif args.mode == "version":
                print(mode_version(m))
            elif args.mode == "get":
                print(mode_get(m, args.xpath))
            elif args.mode == "get-config":
                print(mode_get_config(m))
        return 0
    except Exception as e:
        print(f"ZBX_NOTSUPPORTED: {type(e).__name__}: {e}".replace("\n", " "))
        return 1


if __name__ == "__main__":
    sys.exit(main())
