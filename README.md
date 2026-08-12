# zabbix-netconf

Native **Zabbix ≥ 7.2** NETCONF monitoring (SSH agent + subsystem `netconf`) for **Nokia SR Linux**, plus a small Docker + containerlab demo.

| Doc | Purpose |
|-----|---------|
| **[ZABBIX-NETCONF-ADMIN-GUIDE.md](./ZABBIX-NETCONF-ADMIN-GUIDE.md)** | Customer/admin guide: onboard SR Linux to an **existing** Zabbix estate |
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

To add another metric, create **two items in the Zabbix UI** (not a new item type). Worked example below: **timezone** on `srl1`.

### Add a check (timezone, in the UI)

A check is (1) an **SSH agent** master that returns raw NETCONF XML, plus (2) a **dependent** item that extracts one leaf.

This example is already proven against the lab:

```bash
python3 scripts/netconf_probe.py \
  --host 172.30.50.11 --user admin --password 'NokiaSrl1!' \
  --mode get --xpath '<system><clock><timezone/></clock></system>'
```

Expected reply (pretty-printed). Read it as a path, not as a blob:

```xml
<data xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">
  <system xmlns="urn:nokia.com:srlinux:general:system">
    <clock xmlns="urn:nokia.com:srlinux:linux:ntp">
      <timezone>UTC</timezone>
    </clock>
  </system>
</data>
```

| Piece | What it is | What you do with it |
|-------|------------|---------------------|
| `<data …>` | NETCONF wrapper. Always there on a successful `<get>`. | Ignore. Do not put `<data>` in the filter. |
| `<system xmlns="urn:nokia.com:srlinux:general:system">` | First YANG container + its module URN. | Copy **tag + xmlns** into the executed-script `<filter>`. |
| `<clock xmlns="urn:nokia.com:srlinux:linux:ntp">` | Child container + its module URN. | Same — nest it under `<system>`. |
| `<timezone>UTC</timezone>` | The **leaf**. Tag = name, `UTC` = the metric. | This is what the dependent item extracts. JS/regex match `<timezone>([^<]+)</timezone>` → `UTC`. |
| `rpc-error` / empty `<data/>` | Failed or unmatched filter. | Do not build an item yet. Fix the filter / namespace. |

You are hunting for **one leaf** (`timezone`) and the **xmlns on each ancestor**. Everything else is scaffolding.

Zabbix **Test** on the master is noisier than the probe: you may also see a server `<hello>`, `<rpc-reply>`, and `]]>]]>` markers. That is still a pass if `<timezone>UTC</timezone>` is inside. Fail if you see `<rpc-error>` or `#` chunk headers (that means NETCONF 1.1 framing).

#### 1. Open the host’s item list

1. Browse to http://localhost:8080 and sign in (**Admin** / **zabbix**).
2. Left menu: **Data collection → Hosts**.
3. On the **srl1** row, click **Items** (the Items link, not the hostname).
4. Click **Create item** (upper right).

#### 2. Create the master (raw XML)

Set these fields. Leave anything not listed at the default.

| Field | Exact value |
|-------|-------------|
| **Name** | `NETCONF: Get timezone (raw)` |
| **Type** | `SSH agent` |
| **Key** | `ssh.run[SrlTimezone,{$NETCONF.IP},{$NETCONF.PORT},,,netconf]` |
| **Type of information** | `Text` |
| **Update interval** | `5m` |
| **Username** | `{$NETCONF.USER}` |
| **Authentication method** | `Password` |
| **Password** | `{$NETCONF.PASSWORD}` |
| **Executed script** | paste the block under this table |
| **Timeout** | `30s` |

The sixth key parameter must be the literal word `netconf`. The first parameter (`SrlTimezone`) must be unique on this host.

**Executed script** is three NETCONF messages taped together. It is not a shell script. Each message **must** end with the six characters `]]>]]>` on their own line (end-of-message). Zabbix sends this as-is over the `netconf` SSH subsystem.

```
message 1: <hello> …          we speak NETCONF 1.0 only
]]>]]>
message 2: <rpc><get>…        ask for one YANG subtree
]]>]]>
message 3: <rpc><close-session/>   hang up cleanly
]]>]]>
```

| Block | What it is | What you change |
|-------|------------|-----------------|
| `<hello>…<capability>urn:ietf:params:netconf:base:1.0</capability>` | Client greeting. **Only** `base:1.0` so framing stays `]]>]]>` (1.1 uses `#` chunks and breaks JS). | Leave as-is on every check. |
| `]]>]]>` | End of that message. Required after hello, after get, after close. | Never delete these lines. |
| `<rpc … message-id="1"><get><filter type="subtree">` | “Return operational state matching this tree.” | Keep `<get>` / `<filter>`. Swap only the inner tags. |
| `<system xmlns="…"><clock xmlns="…"><timezone/></clock></system>` | The **ask**. Nested tags = YANG path. Empty `<timezone/>` means “give me this leaf.” `xmlns` comes from the probe reply. | This is the only part that changes per check. |
| `<rpc … message-id="2"><close-session/>` | Close the NETCONF session. | Leave as-is. Bump `message-id` only if you add more RPCs. |

Paste *all* of this, including every `]]>]]>` line:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<hello xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">
  <capabilities>
    <capability>urn:ietf:params:netconf:base:1.0</capability>
  </capabilities>
</hello>
]]>]]>
<rpc xmlns="urn:ietf:params:xml:ns:netconf:base:1.0" message-id="1">
  <get>
    <filter type="subtree">
      <system xmlns="urn:nokia.com:srlinux:general:system">
        <clock xmlns="urn:nokia.com:srlinux:linux:ntp">
          <timezone/>
        </clock>
      </system>
    </filter>
  </get>
</rpc>
]]>]]>
<rpc xmlns="urn:ietf:params:xml:ns:netconf:base:1.0" message-id="2">
  <close-session/>
</rpc>
]]>]]>
```

Then:

1. Click **Test** at the bottom.
2. **Get value and test**. You want XML that contains `<timezone>UTC</timezone>`.
3. Close the test dialog and click **Add**.

If Test fails, do not create the dependent yet. Typical causes: `ZBX_TIMEOUT` below 30s, missing `]]>]]>`, or a typo in the key (especially the trailing `,netconf`).

#### 3. Create the dependent (parsed value)

Still on **srl1 → Items**, click **Create item** again.

| Field | Exact value |
|-------|-------------|
| **Name** | `NETCONF timezone` |
| **Type** | `Dependent item` |
| **Key** | `netconf.timezone` |
| **Type of information** | `Character` |
| **Master item** | click **Select** → choose `NETCONF: Get timezone (raw)` |

Open the **Preprocessing** tab → **Add**:

| Field | Exact value |
|-------|-------------|
| **Name** | `JavaScript` |
| **Script** | the block below |

```javascript
var m = value.match(/<timezone>([^<]+)<\/timezone>/);
if (m) return m[1].trim();
return value.slice(0, 200);
```

Click **Add**.

#### 4. Confirm the value

1. Left menu: **Monitoring → Latest data**.
2. Hosts: **srl1** (or host group **SR Linux Lab**).
3. Name filter: `timezone`.
4. You should see:
   - `NETCONF: Get timezone (raw)` — a blob of XML, status not **Unsupported**
   - `NETCONF timezone` — **`UTC`**

That is the whole pattern. For a different leaf: find it in the
[SR Linux 26.3.1 YANG browser](https://yangbrowser.nokia.com/srlinux/26.3.1)
(not the SR OS tree), probe it, put that subtree (with the namespaces from
the reply) in the master’s `<filter>`, give the `ssh.run[…]` a new first
parameter, and change the JS to match the new tag.

The browser’s **XPath** is the leaf location (`/system/clock/timezone` →
`<system><clock><timezone/></clock></system>`). Its **JS path** is for the
browser UI, not Zabbix preprocessing. Always probe before creating the item.

Production field notes and failure table: [admin guide §7.6](./ZABBIX-NETCONF-ADMIN-GUIDE.md#76-add-a-new-check-recipe).

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
