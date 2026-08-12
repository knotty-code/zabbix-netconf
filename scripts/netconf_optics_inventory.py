#!/usr/bin/env python3
"""Inventory optics via NETCONF on SR Linux (X1b) devices.

Live lab note
-------------
Containerlab X1b sims typically report *all* cages as:
  oper-state=down, oper-down-reason=not-present
so DDM/DOM leaves (power, temp, vendor, …) are absent until a real optic is present
(or a higher-fidelity sim). The YANG model still exposes the full leaf set — this
script prints both **live values** and the **modeled** monitoring surface.

Usage
-----
  python3 netconf_optics_inventory.py --host 172.30.50.11
  python3 netconf_optics_inventory.py --host srl1 --port 22
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def connect(host, port, user, password, timeout):
    from ncclient import manager

    return manager.connect(
        host=host,
        port=port,
        username=user,
        password=password,
        hostkey_verify=False,
        device_params={"name": "default"},
        allow_agent=False,
        look_for_keys=False,
        timeout=timeout,
    )


def walk_leaves(el, prefix=""):
    out = {}
    tag = local(el.tag)
    path = f"{prefix}/{tag}" if prefix else tag
    children = list(el)
    if el.text and el.text.strip() and not children:
        out[path] = el.text.strip()
    for c in children:
        out.update(walk_leaves(c, path))
    return out


def inventory(host, port, user, password, timeout) -> dict:
    with connect(host, port, user, password, timeout) as m:
        reply = m.get(filter=("subtree", "<interface><transceiver/></interface>"))
        xml = reply.data_xml or ""
        root = ET.fromstring(xml)
        ports = []
        for iface in root.iter():
            if local(iface.tag) != "interface":
                continue
            name = None
            xcv = None
            for ch in list(iface):
                if local(ch.tag) == "name" and ch.text:
                    name = ch.text
                if local(ch.tag) == "transceiver":
                    xcv = ch
            if not name or xcv is None:
                continue
            leaves = walk_leaves(xcv)
            # flatten keys without leading transceiver/
            flat = {
                k[len("transceiver/") :] if k.startswith("transceiver/") else k: v
                for k, v in leaves.items()
            }
            ports.append({"interface": name, **flat})

        states = Counter(p.get("oper-state", "?") for p in ports)
        reasons = Counter(p.get("oper-down-reason", "") for p in ports if p.get("oper-down-reason"))
        present = [p for p in ports if p.get("oper-down-reason") != "not-present"]
        return {
            "host": host,
            "port_count": len(ports),
            "oper_state": dict(states),
            "oper_down_reason": dict(reasons),
            "optics_present": len(present),
            "optics_not_present": reasons.get("not-present", 0),
            "ports": ports,
            "xml_bytes": len(xml),
        }


# Modeled monitoring surface (from srl_nokia-interfaces + interfaces-dco YANG)
MODELED = {
    "presence_health": [
        "oper-state",
        "oper-down-reason",  # not-present | read-failure | unknown-transceiver | tx-laser-disabled | …
        "tx-laser",
        "fault-condition",
        "healthz/status",
        "ddm-events",
    ],
    "identity_inventory": [
        "form-factor",  # QSFP28, QSFPDD, SFP56, …
        "ethernet-pmd",
        "connector-type",
        "vendor",
        "vendor-part-number",
        "vendor-revision",
        "serial-number",
        "date-code",
        "wavelength",
        "firmware-version",  # DCO / CMIS
        "functional-type",  # standard | digital-coherent-optics | …
    ],
    "dom_module": [
        "temperature/latest-value (+ max, thresholds, alarm/warn conditions)",
        "voltage/latest-value (+ thresholds, alarm/warn conditions)",
        "input-power/instant (+ thresholds, alarm/warn)  [dBm]",
        "output-power/instant (+ thresholds, alarm/warn) [dBm]",
        "laser-bias-current (via channel / power-levels where applicable)",
    ],
    "dom_per_lane": [
        "channel[index]/wavelength",
        "channel[index]/input-power/*",
        "channel[index]/output-power/*",
    ],
    "dco_coherent": [
        "optical-channel list: frequency, oper-frequency, operational-mode",
        "target-power, chromatic-dispersion / dispersion-control-mode",
        "rx-los-thresh, module-state",
        "statistics: BER, OSNR, ESNR, CD, DGD, freq-offset, quality, power, PDL",
    ],
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", action="append", dest="hosts", help="Repeatable; default both lab nodes")
    ap.add_argument("--port", type=int, default=22)
    ap.add_argument("--user", default="admin")
    ap.add_argument("--password", default="NokiaSrl1!")
    ap.add_argument("--timeout", type=int, default=60)
    ap.add_argument("--json", action="store_true", help="Machine-readable full dump")
    ap.add_argument("--show-ports", action="store_true", help="Print every port row")
    args = ap.parse_args()
    hosts = args.hosts or ["172.30.50.11", "172.30.50.12"]

    results = []
    for h in hosts:
        try:
            results.append(inventory(h, args.port, args.user, args.password, args.timeout))
        except Exception as e:
            results.append({"host": h, "error": f"{type(e).__name__}: {e}"})

    if args.json:
        print(json.dumps({"modeled": MODELED, "live": results}, indent=2))
        return 0

    print("=" * 72)
    print("NETCONF optics exploration — SR Linux")
    print("=" * 72)
    print("\n## Modeled surface (YANG — available when optic present)")
    for section, leaves in MODELED.items():
        print(f"\n### {section}")
        for leaf in leaves:
            print(f"  - {leaf}")

    print("\n## Live inventory")
    for r in results:
        if "error" in r:
            print(f"\n### {r['host']} ERROR {r['error']}")
            continue
        print(f"\n### {r['host']}")
        print(f"  cages with transceiver container : {r['port_count']}")
        print(f"  optics present                   : {r['optics_present']}")
        print(f"  optics not-present               : {r['optics_not_present']}")
        print(f"  oper-state histogram             : {r['oper_state']}")
        print(f"  oper-down-reason histogram       : {r['oper_down_reason']}")
        print(f"  NETCONF payload bytes            : {r['xml_bytes']}")
        # leaf keys currently returned
        keys = sorted({k for p in r["ports"] for k in p if k != "interface"})
        print(f"  leaves currently populated       : {keys}")
        if args.show_ports:
            for p in r["ports"]:
                print(f"    {p['interface']}: { {k:v for k,v in p.items() if k!='interface'} }")

    print("\n## Takeaways for Zabbix")
    print(
        """
  1. Filter: <interface><transceiver/></interface>  (no YANG URN — SRL rejects unknown NS)
  2. NETCONF over SSH port 22 (netconf-server bound to ssh-server mgmt)
  3. Presence / fault: oper-state, oper-down-reason, fault-condition, tx-laser
  4. Inventory (when present): vendor, serial, form-factor, PMD, wavelength
  5. DOM: temperature, voltage, input/output power + alarm/warn thresholds & conditions
  6. Per-lane DOM: channel[1..n] power + wavelength
  7. DCO extras (srl_nokia-interfaces-dco): frequency, OSNR, BER, CD, DGD, PDL, quality
  8. This containerlab sim has 0 installed optics — only presence/down-reason is live today
  9. gNMI already streams transceiver paths for EDA on :57410 (TLS) — parallel option
"""
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        raise
