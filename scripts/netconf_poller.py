#!/usr/bin/env python3
"""LEGACY: Poll Magic Kingdom bleaf X1bs via NETCONF and push metrics to Zabbix.

The lab compose stack now uses **native Zabbix SSH + NETCONF subsystem items**
(Zabbix ≥ 7.2). Prefer `zabbix_register_bleafs.py` and the admin guide.

This trapper poller remains for offline demos or Zabbix &lt; 7.2 only.

Designed to run in a netconf-tools container on the magic-kingdom-mgmt network.

Env:
  ZABBIX_SERVER   default zabbix-server
  ZABBIX_PORT     default 10051
  NETCONF_USER    default admin
  NETCONF_PASSWORD default NokiaSrl1!
  NETCONF_PORT    default 22
  POLL_INTERVAL   seconds, default 60
  ONCE            if "1", run one cycle and exit
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

# Hosts: Zabbix technical host name → NETCONF target
TARGETS = [
    ("bleaf1.magic-kingdom.io", os.environ.get("BLEAF1_IP", "172.30.40.21")),
    ("bleaf2.magic-kingdom.io", os.environ.get("BLEAF2_IP", "172.30.40.22")),
]

PROBE = Path(__file__).resolve().parent / "netconf_probe.py"


def zbx_send(server: str, port: int, lines: list[str]) -> None:
    """Send trapper values via Zabbix sender protocol (JSON + clock)."""
    if not lines:
        return
    import json
    import struct
    import time

    now = int(time.time())
    data = []
    for line in lines:
        # "host key value" — value may contain spaces
        parts = line.split(" ", 2)
        if len(parts) < 3:
            continue
        host, key, value = parts
        data.append({"host": host, "key": key, "value": value, "clock": now})

    sender = _which("zabbix_sender")
    if sender:
        # file format: hostname key timestamp value  (or without timestamp)
        payload = "\n".join(
            f'{d["host"]} {d["key"]} {d["clock"]} {d["value"]}' for d in data
        ) + "\n"
        proc = subprocess.run(
            [sender, "-z", server, "-p", str(port), "-T", "-i", "-"],
            input=payload,
            text=True,
            capture_output=True,
            timeout=30,
        )
        if proc.returncode != 0:
            print(f"zabbix_sender rc={proc.returncode}: {proc.stderr or proc.stdout}", flush=True)
        else:
            print(f"zabbix_sender ok: {proc.stdout.strip()}", flush=True)
        return

    body = json.dumps({"request": "sender data", "data": data}).encode()
    header = b"ZBXD\x01" + struct.pack("<Q", len(body))
    with socket.create_connection((server, port), timeout=15) as s:
        s.sendall(header + body)
        resp = s.recv(4096)
        print(f"trapper resp: {resp[13:].decode(errors='replace')}", flush=True)


def _which(cmd: str) -> str | None:
    from shutil import which

    return which(cmd)


def probe(ip: str, mode: str, user: str, password: str, port: int) -> tuple[bool, str]:
    cmd = [
        sys.executable,
        str(PROBE),
        "--host",
        ip,
        "--port",
        str(port),
        "--user",
        user,
        "--password",
        password,
        "--mode",
        mode,
        "--timeout",
        "25",
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=40)
        out = (r.stdout or "").strip() or (r.stderr or "").strip()
        ok = r.returncode == 0 and not out.startswith("ZBX_NOTSUPPORTED")
        return ok, out
    except Exception as e:
        return False, f"ZBX_NOTSUPPORTED: {e}"


def cycle(server: str, zbx_port: int, user: str, password: str, nport: int) -> None:
    lines: list[str] = []
    for zbx_host, ip in TARGETS:
        print(f"--- probing {zbx_host} ({ip}) ---", flush=True)
        ok_any = False
        for mode, key in [
            ("caps", "netconf.caps"),
            ("hostname", "netconf.hostname"),
            ("if-summary", "netconf.if.summary"),
            ("version", "netconf.version"),
        ]:
            ok, val = probe(ip, mode, user, password, nport)
            # sanitize single-line
            val = " ".join(val.split())
            if ok:
                ok_any = True
                lines.append(f"{zbx_host} {key} {val}")
                print(f"  {key}={val[:120]}", flush=True)
            else:
                lines.append(f"{zbx_host} {key} {val}")
                print(f"  {key} FAIL {val[:120]}", flush=True)

        # Optics inventory (presence-focused; DOM when optics present)
        try:
            from netconf_optics_inventory import inventory as optics_inventory

            inv = optics_inventory(ip, nport, user, password, 40)
            cages = inv.get("port_count", 0)
            present = inv.get("optics_present", 0)
            missing = inv.get("optics_not_present", 0)
            summary = (
                f"cages={cages} present={present} not_present={missing} "
                f"states={inv.get('oper_state')} reasons={inv.get('oper_down_reason')}"
            )
            lines.append(f"{zbx_host} netconf.optics.cages {cages}")
            lines.append(f"{zbx_host} netconf.optics.present {present}")
            lines.append(f"{zbx_host} netconf.optics.not_present {missing}")
            lines.append(f"{zbx_host} netconf.optics.summary {summary}")
            print(f"  optics {summary}", flush=True)
            ok_any = True
        except Exception as e:
            lines.append(f"{zbx_host} netconf.optics.summary ZBX_NOTSUPPORTED: {e}")
            print(f"  optics FAIL {e}", flush=True)

        lines.append(f"{zbx_host} netconf.availability {1 if ok_any else 0}")
    zbx_send(server, zbx_port, lines)


def main() -> int:
    server = os.environ.get("ZABBIX_SERVER", "zabbix-server")
    zbx_port = int(os.environ.get("ZABBIX_PORT", "10051"))
    user = os.environ.get("NETCONF_USER", "admin")
    password = os.environ.get("NETCONF_PASSWORD", "NokiaSrl1!")
    nport = int(os.environ.get("NETCONF_PORT", "22"))
    interval = int(os.environ.get("POLL_INTERVAL", "60"))
    once = os.environ.get("ONCE", "0") == "1"

    # wait for probe script + ncclient
    for _ in range(30):
        try:
            import ncclient  # noqa: F401

            break
        except ImportError:
            time.sleep(2)
    else:
        print("ncclient never became available", flush=True)
        return 1

    print(
        f"NETCONF poller → Zabbix {server}:{zbx_port}; targets={[t[0] for t in TARGETS]}; interval={interval}s",
        flush=True,
    )
    while True:
        try:
            cycle(server, zbx_port, user, password, nport)
        except Exception as e:
            print(f"cycle error: {e}", flush=True)
        if once:
            break
        time.sleep(interval)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
