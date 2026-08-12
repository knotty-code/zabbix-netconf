# zabbix-netconf

Native **Zabbix ≥ 7.2** NETCONF monitoring (SSH agent + subsystem `netconf`) for **Nokia SR Linux** / **7250 IXR-X1b**, plus a Docker lab that demos Magic Kingdom containerlab border leafs.

| Doc | Purpose |
|-----|---------|
| **[ZABBIX-NETCONF-ADMIN-GUIDE.md](./ZABBIX-NETCONF-ADMIN-GUIDE.md)** · [`.docx`](./ZABBIX-NETCONF-ADMIN-GUIDE.docx) | Customer/admin guide: onboard X1b to an **existing** Zabbix estate |
| **This README** | Lab/demo stack quick start |
| [Zabbix-Lab-NETCONF-Overview.pptx](./Zabbix-Lab-NETCONF-Overview.pptx) | Slide overview |

**Primary path:** `ssh.run[...,netconf]` — no external poller required on Zabbix 7.2+.  
**Lab image:** Zabbix **7.4** Alpine (`ZBX_STARTSSH`, `ZBX_TIMEOUT=30`).

---

## Lab targets (Magic Kingdom)

| Host (Zabbix) | Role | Mgmt IP | Platform |
|---------------|------|---------|----------|
| `bleaf1.magic-kingdom.io` | bleaf | **172.30.40.21** | 7250 IXR-X1b · SR Linux 26.3.1 |
| `bleaf2.magic-kingdom.io` | bleaf | **172.30.40.22** | 7250 IXR-X1b · SR Linux 26.3.1 |

Lab topo: Magic Kingdom containerlab (`magic-kingdom.clab.yml` in the magic-kingdom repo).  
Credentials (lab only): **admin** / **NokiaSrl1!**

---

## Quick start

```bash
git clone git@github.com:knotty-code/zabbix-netconf.git
cd zabbix-netconf

# Requires containerlab network magic-kingdom-mgmt (lab already deployed)
docker compose up -d

# Wait until UI answers, then register hosts + native SSH/NETCONF items
python3 scripts/zabbix_register_bleafs.py --url http://localhost:8080
```

| Service | URL / port |
|---------|------------|
| **Zabbix UI** | http://localhost:8080 — **Admin** / **zabbix** |
| Server | TCP **10051** |
| SSH pollers | `ZBX_STARTSSH=5` inside `zabbix-server` |

**Data → Monitoring → Latest data → Host group “Magic Kingdom”**

### Fresh DB after major Zabbix image jump

```bash
docker compose down -v   # wipe volume if schema migration fails
docker compose pull
docker compose up -d
python3 scripts/zabbix_register_bleafs.py --url http://localhost:8080
```

---

## Architecture

```
┌─────────────────────┐   SSH subsystem netconf :22   ┌──────────────┐
│ zabbix-server       │ ────────────────────────────► │ bleaf1 X1b   │
│ SSH pollers         │ ────────────────────────────► │ bleaf2 X1b   │
│ (StartSSH ≥ 1)      │                               └──────────────┘
└─────────┬───────────┘
          │ raw XML → JS/JSONPath preprocessing
          │ dependent items (netconf.*)
          ▼
┌─────────────────────┐     UI :8080                  ┌──────────────┐
│ postgres            │ ◄───────────────────────────► │ zabbix-web   │
└─────────────────────┘                               └──────────────┘
   (server + web joined to docker network magic-kingdom-mgmt)
```

Optional offline probes (not on the data path):

```bash
docker compose --profile tools up -d netconf-tools
docker exec -it zabbix-netconf-tools python3 /scripts/netconf_probe.py \
  --host 172.30.40.21 --user admin --password 'NokiaSrl1!' --mode hostname
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

---

## NETCONF on the X1bs

SR Linux NETCONF is an **SSH subsystem** on **port 22** (not classic 830):

```text
system netconf-server mgmt {
    admin-state enable
    ssh-server mgmt
}
```

If EDA reconciles config, keep this in the source of truth.

---

## Compose notes

- External network **`magic-kingdom-mgmt`** must exist (containerlab).
- `extra_hosts` maps `bleaf*.magic-kingdom.io` → lab mgmt IPs.
- Images: **Zabbix 7.4** Alpine (pgsql) + Postgres 16.
- `ZBX_STARTSSH=5`, `ZBX_TIMEOUT=30` (NETCONF hello needs more than default 3s).

```bash
docker compose logs -f zabbix-server
docker compose down          # keep DB volume
docker compose down -v       # wipe Zabbix DB
```

---

## Repo layout

| Path | Role |
|------|------|
| `ZABBIX-NETCONF-ADMIN-GUIDE.md` / `.docx` | Customer onboarding handbook |
| `docker-compose.yml` | Lab stack |
| `scripts/zabbix_register_bleafs.py` | API: hosts + native SSH items |
| `scripts/netconf_probe.py` | Optional offline probe |
| `scripts/netconf_optics_inventory.py` | Optional optics inventory |
| `scripts/netconf_poller.py` | Legacy trapper poller |
| `build-zabbix-lab-pptx.js` | Regenerates the PowerPoint (`npm run build:pptx`) |
| `externalchecks/` | Optional external-check stubs |

---

## Security

Lab defaults only (`Admin/zabbix`, `admin/NokiaSrl1!`). Do not expose 8080/10051 beyond the lab host without hardening.
