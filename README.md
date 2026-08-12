# zabbix-netconf

Native **Zabbix ≥ 7.2** NETCONF monitoring (SSH agent + subsystem `netconf`) for **Nokia SR Linux**, plus a small Docker + containerlab demo.

| Doc | Purpose |
|-----|---------|
| **[ZABBIX-NETCONF-ADMIN-GUIDE.md](./ZABBIX-NETCONF-ADMIN-GUIDE.md)** | Customer/admin guide: onboard SR Linux (including 7250 IXR-X1b) to an **existing** Zabbix estate |
| **This README** | Lab/demo stack quick start |

**Primary path:** `ssh.run[...,netconf]` — no external poller required on Zabbix 7.2+.  
**Lab image:** Zabbix **7.4** Alpine (`ZBX_STARTSSH`, `ZBX_TIMEOUT=30`).

---

## Lab targets

Two standalone SR Linux nodes (`lab/srl.clab.yml`). One interconnect, no spines or fabric.

| Host (Zabbix) | Role | Mgmt IP | Platform |
|---------------|------|---------|----------|
| `srl1` | leaf | **172.30.50.11** | SR Linux 26.3.1 (`ixrd2l`) |
| `srl2` | leaf | **172.30.50.12** | SR Linux 26.3.1 (`ixrd2l`) |

Credentials (lab only): **admin** / **NokiaSrl1!**

---

## Quick start

```bash
git clone git@github.com:knotty-code/zabbix-netconf.git
cd zabbix-netconf

# 1. Two SR Linux nodes + Docker network srl-lab
sudo containerlab deploy -t lab/srl.clab.yml

# 2. Zabbix (joins srl-lab so it can reach the nodes)
docker compose up -d

# 3. Wait until UI answers, then register hosts + native SSH/NETCONF items
python3 scripts/zabbix_register_hosts.py --url http://localhost:8080
```

| Service | URL / port |
|---------|------------|
| **Zabbix UI** | http://localhost:8080 — **Admin** / **zabbix** |
| Server | TCP **10051** |
| SSH pollers | `ZBX_STARTSSH=5` inside `zabbix-server` |

**Data → Monitoring → Latest data → Host group “SR Linux Lab”**

### Fresh DB after major Zabbix image jump

```bash
docker compose down -v   # wipe volume if schema migration fails
docker compose pull
docker compose up -d
python3 scripts/zabbix_register_hosts.py --url http://localhost:8080
```

### Tear down

```bash
docker compose down          # keep DB volume
docker compose down -v       # wipe Zabbix DB
sudo containerlab destroy -t lab/srl.clab.yml --cleanup
```

---

## Architecture

```
┌─────────────────────┐   SSH subsystem netconf :22   ┌──────────────┐
│ zabbix-server       │ ────────────────────────────► │ srl1         │
│ SSH pollers         │ ────────────────────────────► │ srl2         │
│ (StartSSH ≥ 1)      │                               └──────────────┘
└─────────┬───────────┘
          │ raw XML → JS/JSONPath preprocessing
          │ dependent items (netconf.*)
          ▼
┌─────────────────────┐     UI :8080                  ┌──────────────┐
│ postgres            │ ◄───────────────────────────► │ zabbix-web   │
└─────────────────────┘                               └──────────────┘
   (server joined to docker network srl-lab)
```

Optional offline probes (not on the data path):

```bash
docker compose --profile tools up -d netconf-tools
docker exec -it zabbix-netconf-tools python3 /scripts/netconf_probe.py \
  --host 172.30.50.11 --user admin --password 'NokiaSrl1!' --mode hostname
```

Legacy `scripts/netconf_poller.py` (trapper push) remains for Zabbix &lt; 7.2 only.

### Items (per host)

| Key | Type | Meaning |
|-----|------|---------|
| `net.tcp.service[ssh,"{$NETCONF.IP}","{$NETCONF.PORT}"]` | Simple check | Port open |
| `netconf.availability` | Calculated | Mirrors TCP check (1/0) |
| `ssh.run[SrlHostname,...,netconf]` | SSH master | Raw hostname RPC XML |
| `netconf.hostname` | Dependent | Parsed host-name |
| `ssh.run[SrlVersion,...,netconf]` | SSH master | Platform control XML |
| `netconf.version` | Dependent | software-version |
| `ssh.run[SrlInterfaces,...,netconf]` | SSH master | Interface tree |
| `netconf.if.summary` | Dependent | `interfaces=N oper_up=…` |
| `netconf.caps` | Dependent | Session smoke |
| `ssh.run[SrlOptics,...,netconf]` | SSH master | Transceiver subtree |
| `netconf.optics.*` | Dependent | cages / present / not_present / summary |

Macros: `{$NETCONF.IP}`, `{$NETCONF.PORT}`, `{$NETCONF.USER}`, `{$NETCONF.PASSWORD}`.

Register extra devices (or skip the lab defaults):

```bash
python3 scripts/zabbix_register_hosts.py \
  --url http://localhost:8080 \
  --group 'Nokia SR Linux' \
  --host leaf1:10.0.0.11 \
  --host leaf2:10.0.0.12
```

---

## NETCONF on SR Linux

SR Linux NETCONF is an **SSH subsystem** on **port 22** (not classic 830). The lab startup configs already set this:

```text
system netconf-server mgmt {
    admin-state enable
    ssh-server mgmt
}
```

If a controller reconciles config, keep this in the source of truth.

---

## Compose notes

- External network **`srl-lab`** must exist (created by containerlab).
- `extra_hosts` maps `srl1` / `srl2` → lab mgmt IPs.
- Images: **Zabbix 7.4** Alpine (pgsql) + Postgres 16.
- `ZBX_STARTSSH=5`, `ZBX_TIMEOUT=30` (NETCONF hello needs more than default 3s).

```bash
docker compose logs -f zabbix-server
```

---

## Repo layout

| Path | Role |
|------|------|
| `ZABBIX-NETCONF-ADMIN-GUIDE.md` | Customer onboarding handbook |
| `lab/srl.clab.yml` | Two-node SR Linux topology |
| `lab/startup/` | Enable NETCONF on each node |
| `docker-compose.yml` | Lab Zabbix stack |
| `scripts/zabbix_register_hosts.py` | API: hosts + native SSH items |
| `scripts/netconf_probe.py` | Optional offline probe |
| `scripts/netconf_optics_inventory.py` | Optional optics inventory |
| `scripts/netconf_poller.py` | Legacy trapper poller |
| `externalchecks/` | Optional external-check stubs |

---

## Security

Lab defaults only (`Admin/zabbix`, `admin/NokiaSrl1!`). Do not expose 8080/10051 beyond the lab host without hardening.
