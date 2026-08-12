# Zabbix administrator guide: Onboarding Nokia 7250 IXR-X1b with NETCONF

**Audience:** Zabbix administrators operating an **existing** Zabbix deployment who need to monitor **Nokia 7250 IXR-X1b** (SR Linux) using **NETCONF**, without relying on SNMP.  
**Goal:** Enable the device, validate NETCONF, and collect metrics using **Zabbix’s native SSH + NETCONF subsystem** (7.2+), with a clear fallback path for older servers or bulk collectors.

| | |
|--|--|
| **Platform** | Nokia 7250 IXR-X1b |
| **NOS** | SR Linux |
| **Primary protocol** | NETCONF over SSH (subsystem `netconf`) |
| **Primary Zabbix path** | **Native** (Zabbix ≥ 7.2): SSH agent + `ssh.run[...,netconf]` |
| **Fallback** | External poller → trapper only if Zabbix &lt; 7.2 (lab stack does **not** use this) |
| **Secondary (optional)** | gNMI (often already used by Nokia EDA / other collectors) |
| **Out of scope** | Replacing your Zabbix install; full DC fabric design |

---

## 1. Purpose and scope

This guide helps you:

1. Use **native NETCONF monitoring** in **Zabbix 7.2 and later** (SSH item subsystem support).  
2. Prepare an **X1b** for model-driven monitoring.  
3. **Onboard one X1b** (or a small set) into an existing Zabbix server/proxy estate.  
4. Start with a **practical metric set** (reachability, identity, interfaces, optics presence) and extend later (DOM / DCO).  
5. Know when to fall back to an **external poller** (Zabbix &lt; 7.2, heavy bulk inventory, or air-gapped jump hosts).

It is written for **customer production or lab Zabbix**, not as a requirement to install a particular container stack.

---

## 2. Why NETCONF for X1b (and not SNMP)

| Topic | SNMP | NETCONF |
|-------|------|---------|
| **Native Zabbix collection (7.2+)** | SNMP agent items | **SSH agent + subsystem `netconf`** |
| **Data contract** | MIB / OID | YANG modules → hierarchical XML |
| **Transport** | Typically UDP/161 | **SSH subsystem** (SR Linux often **TCP 22**, not classic 830) |
| **X1b / SR Linux fit** | Often incomplete or operationally brittle | First-class model-driven read of **config + operational state** |
| **Config vs state** | Mixed OIDs | Explicit datastores / state leaves via `<get>` / filters |

**Fair operational statement:**  
With NETCONF you can retrieve **any operational or configuration node the NOS exposes in YANG** for that session (subject to capabilities, features, and AAA)—not an arbitrary internal structure, and **not a MIB**.

---

## 3. How Zabbix does NETCONF (native, 7.2+)

### 3.1 What changed in Zabbix 7.2

Zabbix **7.2** extended **SSH agent** items with a sixth key parameter: **subsystem**.

```text
ssh.run[<unique short description>,<ip>,<port>,<encoding>,<ssh options>,<subsystem>]
```

Setting subsystem to **`netconf`** opens the remote **NETCONF SSH subsystem** instead of a normal shell. The item’s **Executed script** field then carries **NETCONF RPC XML**, framed with the standard NETCONF end-of-message marker `]]>]]>`.

Official documentation examples:

| Example | Meaning |
|---------|---------|
| `ssh.run[Cisco1234,192.0.2.18,,,,netconf]` | SSH/NETCONF to 192.0.2.18 (default port **22**) |
| `ssh.run[SFTPBackup,192.0.2.18,,,,sftp]` | Same pattern for SFTP subsystem |

Reference: [Zabbix SSH checks](https://www.zabbix.com/documentation/current/en/manual/config/items/itemtypes/ssh_checks) · [What’s new in 7.2](https://www.zabbix.com/whats_new_7_2)

**Native support (important):** Starting with **Zabbix 7.2**, NETCONF is a **first-class, built-in monitoring path**—not a third-party plugin and not dependent on an external poller. Zabbix did not add a new menu item named “NETCONF”; instead it extended the existing **SSH agent** item with a **subsystem** parameter. Operationally that *is* native NETCONF: the server/proxy opens the device’s `netconf` SSH subsystem and runs your RPCs from the *Executed script* field.

| If you read… | What it means |
|--------------|----------------|
| “Native NETCONF in Zabbix 7.2+” | Use **SSH agent** + key `ssh.run[...,netconf]` (this guide’s primary path) |
| “No separate NETCONF item type” | UI type is still **SSH agent**; capability is the 6th key parameter `netconf` |
| “External poller” | Optional **fallback** only for Zabbix &lt; 7.2 or special topologies (§9)—**not** required on 7.2+ |

### 3.2 Recommended architecture (production, Zabbix ≥ 7.2)

```
┌────────────────────┐   SSH subsystem netconf    ┌──────────────────┐
│ Zabbix server or   │ ─────────────────────────► │ 7250 IXR-X1b     │
│ active proxy       │   (typically TCP 22)       │ SR Linux         │
│ SSH pollers        │                            └──────────────────┘
│ (StartSSH ≥ 1)     │
└─────────┬──────────┘
          │ raw XML reply → preprocessing
          │ (regex / JS → fields / JSON)
          ▼
┌────────────────────┐
│ Dependent items,   │
│ LLD, triggers, UI  │
└────────────────────┘
```

| Pros | Cons |
|------|------|
| No external poller process | Requires **Zabbix ≥ 7.2** |
| Credentials and items live in Zabbix (macros / vault) | Large YANG trees need careful filters + JS preprocessing |
| Matches official pattern (e.g. **Juniper MX by NETCONF** templates) | Server/proxy must be built with **libssh** (preferred) or libssh2 |
| Works with proxies (poll near the devices) | Each master SSH item opens a session; plan intervals |

### 3.3 Fallback: external poller + trapper (any version)

Use when:

- Zabbix is still **&lt; 7.2**, or  
- You need heavy multi-RPC bulk collection with custom Python, or  
- NETCONF must run from a **jump host** that is not a Zabbix proxy.

```
NETCONF poller (ncclient) ──► X1b
        │
        └── zabbix_sender / trapper ──► Zabbix server or proxy
```

This repository’s **lab** stack (repo root: `docker-compose.yml`, `lab/srl.clab.yml`, `scripts/`) uses the **same native SSH+NETCONF path** (Compose: Zabbix **7.4**, `ZBX_STARTSSH`, `zabbix_register_hosts.py`). The legacy poller script remains only as a reference for Zabbix &lt; 7.2.

### 3.4 Pattern summary

| Pattern | Min Zabbix | When to use |
|---------|------------|-------------|
| **A. SSH agent + `netconf` subsystem** | **7.2** | **Default for production X1b onboarding** |
| B. Poller → trapper | Any | Legacy Zabbix, jump hosts, complex bulk scripts |
| C. External check / Script item | Any | Few metrics; Python on server/proxy |
| D. SSH to CLI only | Any | Not model-driven; avoid for optics/state trees |

---

## 4. Prerequisites

### 4.1 Zabbix version and packages

| Requirement | Detail |
|-------------|--------|
| **Version** | **7.2 or later** for native NETCONF (this guide’s primary path) |
| **SSH support** | Server/proxy built/packaged with **libssh** (recommended) or libssh2 |
| **Pollers** | `StartSSH` ≥ 1 on the **server or proxy** that will dial the X1b (increase for many hosts) |
| **Permissions** | Create hosts, templates, items, macros, triggers |

Confirm version in the UI (**Reports → System information** or Administration) or `zabbix_server -V`.

### 4.2 Network

- [ ] Path from **Zabbix server or proxy** (the SSH poller) to the X1b **management address**.  
- [ ] **TCP 22** open for SSH/NETCONF (see §5—do not assume port **830**).  
- [ ] If using proxies, assign the host to the **regional proxy** so SSH originates in-region.  
- [ ] DNS or static mapping for the Zabbix technical host name.

### 4.3 Device (X1b / SR Linux)

- [ ] Management IP and hostname known.  
- [ ] SSH works with a monitoring identity.  
- [ ] NETCONF server enabled and operational (§5).  
- [ ] AAA allows that identity to perform NETCONF **get** (read-only preferred).  
- [ ] Change control agreed if EDA/NMS owns the config.

### 4.4 Authentication secrets

| Method | Zabbix item fields |
|--------|-------------------|
| Password | Authentication method **Password**; username + password (prefer **secret macros**) |
| Public key | Authentication method **Public key**; configure Zabbix `SSHKeyLocation` and key files on the server/proxy |

---

## 5. Prepare the X1b: enable NETCONF (SR Linux)

### 5.1 Confirm platform

```text
show version
# Expect SR Linux and chassis type consistent with 7250 IXR-X1b
```

### 5.2 Enable NETCONF

On SR Linux, NETCONF is commonly an **SSH subsystem** attached to an existing management `ssh-server` instance (often named `mgmt`), not a separate listener on port 830.

**MD-CLI / candidate example:**

```text
enter candidate
system netconf-server mgmt {
    admin-state enable
    ssh-server mgmt
}
commit now
```

**Verify:**

```text
info system netconf-server *
info from state system netconf-server *
```

Expect `admin-state enable` and `oper-state up` for the instance you configured.

### 5.3 Port and connectivity

| Expectation | Detail |
|-------------|--------|
| **Port** | **22** when bound to `ssh-server` (lab and many SRL deployments) |
| **Classic 830** | May be unused; do not assume 830 is open |
| **Subsystem name** | `netconf` (what Zabbix puts in the 6th key parameter) |

### 5.4 Production account (recommended)

| Practice | Guidance |
|----------|----------|
| User | Dedicated monitoring user (e.g. `zabbix-ro`) |
| Rights | Read-only / get operations; no `edit-config` if monitoring-only |
| Auth | Password or key per security policy; store secrets outside git |
| Source restriction | Limit SSH sources to Zabbix proxy/server IPs where possible |

### 5.5 Config ownership / EDA

If Nokia **EDA** or another controller reconciles configuration, NETCONF enablement must live in the **source of truth**. Otherwise monitoring may break after a reconcile.

---

## 6. Validate NETCONF before creating Zabbix objects

Run these from the **same host/network path** that will poll (Zabbix server or proxy).

### 6.1 Optional client probe (this repo)

```bash
python3 netconf_probe.py \
  --host <MGMT_IP_OR_FQDN> \
  --port 22 \
  --user <USER> \
  --password '<SECRET>' \
  --mode caps
```

**Success:** `ok capabilities=<N>` (N often hundreds of YANG modules on SRL).

```bash
python3 netconf_probe.py \
  --host <MGMT_IP_OR_FQDN> --port 22 \
  --user <USER> --password '<SECRET>' \
  --mode hostname
```

### 6.2 Optics inventory (optional)

```bash
python3 netconf_optics_inventory.py \
  --host <MGMT_IP_OR_FQDN> --port 22 \
  --user <USER> --password '<SECRET>'
```

On simulators, all cages may show `not-present` until real optics exist.

### 6.3 Filter tip (SR Linux)

Prefer **bare** subtree filters:

```xml
<interface><transceiver/></interface>
```

Avoid inventing YANG namespace URIs unless you know the exact URN—incorrect namespaces often return `Unknown namespace`.

---

## 7. Configure Zabbix — native SSH + NETCONF (primary)

### 7.1 Host design

| Field | Recommendation |
|-------|----------------|
| **Host name** (technical) | Stable ID, e.g. `site-a-srl-01.example.com` |
| **Visible name** | Human label, e.g. `Site A · Leaf-01 · SR Linux` |
| **Groups** | e.g. `Nokia SR Linux`, `Leaf`, site/region |
| **Interface** | Agent (or other) interface with **management IP**—required by Zabbix even for SSH items |
| **Proxy** | Regional proxy if used |
| **Tags** | `platform=srlinux`, `os=SR-Linux`, `monitor=netconf`, `role=leaf` |
| **Macros** | See §7.2 |

Do **not** attach SNMP interfaces for this path unless you intentionally dual-stack later.

### 7.2 Host / template macros (suggested)

| Macro | Example | Purpose |
|-------|---------|---------|
| `{$NETCONF.IP}` | `10.10.10.21` | Address used in the SSH item key (may equal interface IP) |
| `{$NETCONF.PORT}` | `22` | SSH/NETCONF port (**22** for typical SRL) |
| `{$NETCONF.USER}` | `zabbix-ro` | Device username (item **Username** field) |
| `{$NETCONF.PASSWORD}` | *(secret)* | Item password; use secret macros / vault |
| `{$NETCONF.TIMEOUT}` | `30s` | Item timeout (UI timeout field) |

Prefer **secret macros** where supported.

### 7.3 Master item: SSH agent + subsystem `netconf`

Create an item of type **SSH agent**:

| Field | Value |
|-------|--------|
| **Name** | e.g. `NETCONF: Get system hostname` |
| **Type** | SSH agent |
| **Key** | `ssh.run[SrlHostname,{$NETCONF.IP},{$NETCONF.PORT},,,netconf]` |
| **Username** | `{$NETCONF.USER}` |
| **Authentication method** | Password (or Public key) |
| **Password** | `{$NETCONF.PASSWORD}` |
| **Executed script** | See sample RPC below |
| **Type of information** | Text (or Log for very large replies) |
| **Update interval** | e.g. 1–5 minutes for identity; longer for heavy trees |
| **Timeout** | Sufficient for the device (e.g. 15–60s) |

**Key rules (official):**

- First parameter (**unique short description**) must be **unique per host** for each SSH item.  
- Default port in the key is **22** if you leave port empty—set `{$NETCONF.PORT}` explicitly.  
- Sixth parameter **`netconf`** selects the NETCONF subsystem.

### 7.4 Executed script: NETCONF RPC framing

For subsystem `netconf`, the **Executed script** is **not** a shell command. It is one or more **RPC documents**, each terminated by **`]]>]]>`**.

**Official multi-RPC shape (from Zabbix docs, Juniper-style RPC names shown as example):**

```xml
<rpc>
  <get-software-information/>
</rpc>
]]>]]>
<rpc>
  <close-session/>
</rpc>
]]>]]>
```

**SR Linux note:** devices often advertise NETCONF **1.0 and 1.1**. Prefer a **client hello that announces only base:1.0** so message framing stays `]]>]]>` (1.1 uses chunked framing). Always end with `<close-session/>`.

**SR Linux-oriented baseline — hostname (operational state):**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<hello xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">
  <capabilities>
    <!-- capability URI (not the XML namespace URI) -->
    <capability>urn:ietf:params:netconf:base:1.0</capability>
  </capabilities>
</hello>
]]>]]>
<rpc xmlns="urn:ietf:params:xml:ns:netconf:base:1.0" message-id="1">
  <get>
    <filter type="subtree">
      <system xmlns="urn:nokia.com:srlinux:general:system">
        <name xmlns="urn:nokia.com:srlinux:chassis:system-name"/>
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

**Version / platform (adapt filter to the leaves you need):**

```xml
<rpc message-id="1">
  <get>
    <filter type="subtree">
      <system>
        <information/>
      </system>
    </filter>
  </get>
</rpc>
]]>]]>
<rpc message-id="2">
  <close-session/>
</rpc>
]]>]]>
```

**Transceiver / optics presence (all interfaces with a transceiver container):**

```xml
<rpc message-id="1">
  <get>
    <filter type="subtree">
      <interface>
        <transceiver/>
      </interface>
    </filter>
  </get>
</rpc>
]]>]]>
<rpc message-id="2">
  <close-session/>
</rpc>
]]>]]>
```

**Notes:**

- Always end sessions with **`<close-session/>`** when the NOS expects a clean close (mirrors official examples).  
- Keep filters **narrow**—unfiltered full-device `<get>` can be multi‑megabyte.  
- Reply size is limited (Zabbix documents up to **16MB** for the SSH item return; DB limits also apply).  
- Exact YANG paths can vary by SR Linux release; validate filters with a client probe first (§6).

### 7.5 Preprocessing pattern (master + dependent items)

Zabbix returns the **raw NETCONF XML** (or multi-reply stream) as the master item value. Extract metrics with **preprocessing**, then **dependent items** / **LLD**.

**Recommended pattern** (same idea as official **Juniper MX by NETCONF** templates):

1. **Master SSH item** — one RPC (or a small bulk set); Type = Text.  
2. **Preprocessing on master** (optional):  
   - JavaScript to normalize XML → JSON, strip framing, or count tags.  
   - Or leave raw XML and parse per dependent item.  
3. **Dependent items** — JSONPath / regex / JS to pull single values (hostname, oper-state counts, etc.).  
4. **LLD rule** (later) — JS that emits discovery JSON for per-port optics.

**Example: extract hostname with regex preprocessing** (adjust to actual XML):

| Step | Type | Parameters |
|------|------|------------|
| 1 | Regular expression | Pattern: `<name>([^<]+)</name>` · Output: `\1` |
| 2 | Trim | (optional) |

**Example: count `not-present` optics with JavaScript** (illustrative):

```javascript
// value = raw XML string from master item
var n = (value.match(/not-present/g) || []).length;
return n;
```

**Example: availability** — use a simple check or treat successful master item history as up:

| Item | Type | Idea |
|------|------|------|
| `net.tcp.service[ssh,{$NETCONF.IP},{$NETCONF.PORT}]` | Simple check | Port open |
| Master SSH item not unsupported | Built-in | Session + RPC succeeded |

### 7.6 Add a new check (recipe)

Do this in the **Zabbix UI**. You will create two items on one host: an SSH master that returns XML, and a dependent that stores one parsed leaf. There is no menu item named “NETCONF”.

Worked example: **system timezone**. Live lab reply (SR Linux 26.3) is:

```xml
<data xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">
  <system xmlns="urn:nokia.com:srlinux:general:system">
    <clock xmlns="urn:nokia.com:srlinux:linux:ntp">
      <timezone>UTC</timezone>
    </clock>
  </system>
</data>
```

Copy those **xmlns** values into the RPC filter. Do not invent URNs.

#### 1. Confirm the leaf (probe)

From the poller host (or the lab repo root):

```bash
python3 scripts/netconf_probe.py \
  --host <MGMT_IP> --port 22 \
  --user <USER> --password '<SECRET>' \
  --mode get --xpath '<system><clock><timezone/></clock></system>'
```

Stop here if you do not see `<timezone>…</timezone>`.

#### 2. Open the host’s item list

1. Zabbix UI → **Data collection → Hosts**.
2. On the target host row, click **Items** (not the hostname).
3. **Create item**.

#### 3. Create the SSH master — set every field below

Selecting **Type = SSH agent** reveals Username, Password, and Executed script.

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
| **Timeout** | `30s` (server `Timeout` / `ZBX_TIMEOUT` must be ≥ 30) |

Key rules: first parameter (`SrlTimezone`) is unique **per host**; sixth parameter is the literal `netconf`; do not omit the empty encoding/options commas.

**Executed script** — paste the entire block, including every `]]>]]>` line. This is not a shell command.

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

Hello must announce **only** `base:1.0`. If you also advertise 1.1, the device uses chunked framing and Test/preprocessing will fail.

Then:

1. **Test → Get value and test**.
2. Pass = XML containing `<timezone>UTC</timezone>` (or another zone name).
3. Close Test → **Add**.

Do not create the dependent until Test succeeds.

#### 4. Create the dependent — set every field below

**Create item** again on the same host.

| Field | Exact value |
|-------|-------------|
| **Name** | `NETCONF timezone` |
| **Type** | `Dependent item` |
| **Key** | `netconf.timezone` |
| **Type of information** | `Character` |
| **Master item** | **Select** → `NETCONF: Get timezone (raw)` |

**Preprocessing** tab → **Add**:

| Field | Exact value |
|-------|-------------|
| **Name** | `JavaScript` |
| **Script** | see below |

```javascript
var m = value.match(/<timezone>([^<]+)<\/timezone>/);
if (m) return m[1].trim();
return value.slice(0, 200);
```

Regex alternative: type **Regular expression**, pattern `<timezone>([^<]+)</timezone>`, output `\1`.

**Add**.

#### 5. Confirm in Latest data

1. **Monitoring → Latest data**.
2. Filter to the host.
3. Name contains `timezone`.
4. Master shows XML and is **not Unsupported**.
5. `netconf.timezone` shows `UTC` (or the device zone), not the raw XML.

#### Repeat for a different leaf

1. Probe the new subtree until you have a reply with the leaf you want.  
2. Put that subtree, including the `xmlns` values from the reply, inside the master’s `<filter>`.  
3. Change the first `ssh.run[…]` parameter (must stay unique).  
4. Point a new dependent at that master and match the new tag in JS/regex.

#### Common failures

| Symptom | Likely cause |
|---------|----------------|
| Master **Unsupported** / timeout | `ZBX_TIMEOUT` too low; filter too wide; NETCONF not enabled |
| Empty `<data/>` or `Unknown namespace` | Wrong YANG URN — use the xmlns from the probe reply |
| Regex/JS returns garbage or chunk headers | Hello advertised **1.1**; announce **only** `base:1.0` |
| Reply is truncated / item error | Missing `]]>]]>` after each RPC, or no `<close-session/>` |
| “Item already exists” | First `ssh.run[…]` parameter not unique on the host |
| Test works, Latest data empty | Interval not elapsed — use **Execute now** on the master |

Per-interface or per-optic checks are the same pattern plus **LLD** later (§13). Do not start there.

#### Persist it in the lab

UI items disappear if you wipe the Zabbix DB. To recreate them with `zabbix_register_hosts.py`, add the filter (with the live namespaces) next to the existing `RPC_*` / `JS_*` constants, then call the same helpers used for hostname:

```python
NS_SYSTEM = "urn:nokia.com:srlinux:general:system"
NS_NTP = "urn:nokia.com:srlinux:linux:ntp"
RPC_TIMEZONE = rpc_get(
    f'<system xmlns="{NS_SYSTEM}">'
    f'<clock xmlns="{NS_NTP}"><timezone/></clock>'
    f"</system>"
)
JS_TIMEZONE = r"""
var m = value.match(/<timezone>([^<]+)<\/timezone>/);
if (m) return m[1].trim();
return value.slice(0, 200);
""".strip()
```

In `ensure_items()`:

```python
mid_tz = create_ssh_master(
    api, hostid,
    name="NETCONF: Get timezone (raw)",
    key_desc="SrlTimezone",
    params=RPC_TIMEZONE,
    delay="5m",
)
create_dependent(
    api, hostid, mid_tz,
    name="NETCONF timezone",
    key="netconf.timezone",
    value_type=VT_CHAR,
    preprocessing=[_pp_js(JS_TIMEZONE)],
)
```

Re-run `python3 scripts/zabbix_register_hosts.py --url http://localhost:8080`. That script **replaces** existing `netconf.*` / `ssh.run[Srl…]` items on the host unless you pass `--keep-legacy`.

### 7.7 Suggested starter item set

| Purpose | Approach | Notes |
|---------|----------|-------|
| NETCONF TCP up | Simple check `net.tcp.service[ssh,...]` | Fast fail for ACL/routing |
| Hostname | SSH master + regex/JS | Identity / inventory drift |
| Software version | SSH master + preprocess | Change detection |
| Interface summary | SSH master + JS | Keep filter bounded |
| Optics cages / present / missing | SSH master (transceiver filter) + JS counts | Tier A presence |
| Per-port DOM / DCO | Master + LLD + dependent prototypes | After real optics |

Template name suggestion: **Template Nokia SR Linux NETCONF (SSH)**.

### 7.8 Triggers (initial)

| Name | Idea | Severity |
|------|------|----------|
| NETCONF TCP down | `net.tcp.service[...] = 0` for N minutes | High |
| NETCONF item unsupported | Item becomes unsupported (auth, RPC error, timeout) | High / Average |
| Hostname mismatch | last hostname ≠ expected inventory | Warning |
| Optics present drop | drop in present count (real hardware only) | Average / High |

Suppress noisy “all cages empty” alerts on simulators.

### 7.9 Templates and scale

1. Create the template with macros and SSH master items.  
2. Add dependent items and triggers on the template.  
3. Link to each X1b host; override macros per host.  
4. Export YAML/XML into GitOps / backup.  
5. Study official **Juniper MX by NETCONF** as a structural reference (SSH masters + JS preprocess + dependent items + LLD)—vendor RPCs differ, pattern does not.

### 7.10 UI verification

1. Open **Monitoring → Latest data** for the host.  
2. Confirm master SSH items update and are not **Unsupported**.  
3. Confirm dependent fields (hostname, counts) populate.  
4. Use **Test** on the item (where available) while developing RPCs.

---

## 8. End-to-end checklist: onboard one X1b (native path)

### Phase A — Plan

1. Confirm **Zabbix ≥ 7.2** on the server/proxy that will poll.  
2. Record **mgmt IP**, **hostname**, **site**, **proxy**.  
3. Confirm `StartSSH` and libssh packaging.  
4. Agree monitoring user and secret handling.

### Phase B — Device

5. SSH to the X1b; confirm SR Linux / X1b.  
6. Enable `netconf-server` bound to mgmt SSH (§5).  
7. Verify `oper-state up`.  
8. Persist config in automation source of truth if applicable.

### Phase C — Path validation

9. From Zabbix server/proxy: `ssh <user>@<mgmt_ip>`.  
10. Optional: capability + hostname probes (§6).  
11. Confirm TCP **22** from that host.

### Phase D — Zabbix objects

12. Create host group(s), host, tags, interface IP, proxy.  
13. Set `{$NETCONF.*}` macros.  
14. Link **Template Nokia SR Linux NETCONF (SSH)** or create SSH items (§7).  
15. Add simple-check reachability + triggers.

### Phase E — Accept

16. Latest data shows XML/extracted values; items supported.  
17. Enable agreed triggers.  
18. Document host in CMDB; note NETCONF owner.  
19. Hand off to NOC with dashboard link.

### Phase F — Next X1b

20. Enable NETCONF → macros → template link → verify Latest data.

---

## 9. Fallback: external poller + trapper (Zabbix &lt; 7.2 or bulk)

### 9.1 When to use

- Server still on **7.0 LTS** (or earlier) without subsystem support.  
- Need multi-host Python orchestration, complex parsing, or offline inventory dumps.  
- NETCONF can only be initiated from a non-proxy jump host.

### 9.2 Item keys (trapper)

| Key | Value type | Description |
|-----|------------|-------------|
| `netconf.availability` | Numeric (unsigned) | 1 = probe succeeded |
| `netconf.caps` | Text | Capability summary |
| `netconf.hostname` | Text | System host-name |
| `netconf.if.summary` | Text | Interface oper summary |
| `netconf.version` | Text | Software version |
| `netconf.optics.cages` | Numeric | Transceiver containers |
| `netconf.optics.present` | Numeric | Installed optics |
| `netconf.optics.not_present` | Numeric | Empty cages |
| `netconf.optics.summary` | Text | Histogram / debug |

Trapper items require **exact technical host name** and **key**. Include **clock** timestamps when using JSON sender protocol.

### 9.3 Poller behaviour (reference)

`scripts/netconf_poller.py` connects with `ncclient`, collects metrics, and sends via trapper. Production needs process supervision, backoff, and secret injection.

### 9.4 External check alternative

Script on server/proxy: item type **External check**, key e.g. `netconf_get.sh[{$NETCONF.IP},{$NETCONF.USER},{$NETCONF.PASSWORD},hostname]`. Heavier per-item load than bulk SSH masters with dependents.

---

## 10. Optics monitoring guidance

### 10.1 What NETCONF can provide (YANG)

| Tier | Content | When available |
|------|---------|----------------|
| **A – Presence** | `oper-state`, `oper-down-reason`, `tx-laser`, fault flags | Empty cages included |
| **B – Inventory** | vendor, PN, SN, form-factor, PMD, wavelength | Optic installed |
| **C – DOM** | temperature, voltage, Rx/Tx power, thresholds | Optic + DDM |
| **D – DCO** | frequency, OSNR, BER, CD, DGD (`srl_nokia-interfaces-dco`) | Coherent / ZR-class |

### 10.2 Practical rollout

1. **Tier A** via native SSH master + JS counts (or poller).  
2. **Tier B** inventory strings as dependent items.  
3. **Tier C/D** numeric items + thresholds when fiber/coherent is live.  
4. Prefer **LLD** for per-port items once cardinality is known.

---

## 11. Troubleshooting

| Symptom | Checks |
|---------|--------|
| Item type SSH missing / unsupported key | Upgrade to **≥ 7.2**; confirm package includes SSH support |
| SSH item unsupported: library | Server/proxy linked with libssh/libssh2 |
| Cannot connect | Routing, ACL, credentials, mgmt network-instance; try from proxy host |
| Works on 830 elsewhere, fails on X1b | Use **port 22**; confirm `netconf-server` + `ssh-server` |
| Auth fails | Username/password macros; key files under `SSHKeyLocation` |
| Empty or error RPC reply | Filter namespaces; simplify subtree; test with `netconf_probe.py` |
| `Unknown namespace` | Bare filters; no guessed YANG URNs |
| Huge values / timeout | Narrow filter; increase item timeout; reduce interval concurrency |
| Dependent items empty | Master value shape changed; fix regex/JS/JSONPath; use preprocessing test |
| Caps work in Python, Zabbix fails | Subsystem spelling `netconf`; RPC framing `]]>]]>`; unique key description |
| Worked then stopped | Config reconcile removed NETCONF; password rotation; ACL change |
| Poller trapper `processed: 0` | Wrong technical host name; item not trapper type; key typo |

### Useful device commands

```text
info from state system netconf-server *
info system ssh-server *
show version
```

### Useful Zabbix checks

- Server/proxy log for SSH poller errors  
- **Monitoring → Queue** (SSH backlog)  
- Item configuration: type **SSH agent**, 6th key param `netconf`  
- Macro resolution on the host  
- `StartSSH` in `zabbix_server.conf` / proxy conf  

---

## 12. Security

- Prefer **read-only** device accounts for monitoring.  
- Prefer **secret macros** or vault integration for passwords.  
- Restrict SSH sources to Zabbix proxy/server addresses.  
- Protect private keys used by the Zabbix process.  
- Rotate device and Zabbix API credentials per policy.  
- Do not commit production secrets to repositories.  
- Lab sample passwords in any demo materials are **not** for production.

---

## 13. Extending beyond the baseline

| Goal | Approach |
|------|----------|
| One extra leaf / metric | §7.6 recipe (master SSH item + dependent parse) |
| Many X1bs | Template + API/Ansible host create + macro fill |
| Per-port optics | LLD from JS preprocessing of transceiver XML |
| Numeric DOM / DCO | Dependent float items + triggers |
| Dashboards | Filter tags `monitor=netconf`, `platform=7250-IXR-X1b` |
| gNMI | Separate collector; optional trapper or other pipeline |
| Still on Zabbix 7.0 | Use §9 poller→trapper until upgrade to 7.2+ |

---

## 14. Quick reference

```
Platform:     Nokia 7250 IXR-X1b / SR Linux
Native:       Zabbix ≥ 7.2 — NETCONF via SSH subsystem (built-in; no external poller)
UI type:      SSH agent  (not a separate "NETCONF" type name)
Key:          ssh.run[<unique>,{$NETCONF.IP},{$NETCONF.PORT},,,netconf]
Script:       client hello base:1.0 + <rpc>...</rpc> + ]]>]]> + close-session
Port:         22 (typical when netconf-server bound to ssh-server mgmt)
Enable:       system netconf-server <name> { admin-state enable; ssh-server <ssh>; }
Parse:        Preprocessing + dependent items (regex / JS / JSONPath)
Fallback:     ncclient poller → trapper only if Zabbix < 7.2
Optics:       Start with presence; add DOM/DCO when pluggables exist
UI check:     Monitoring → Latest data · items not Unsupported
Docs:         zabbix.com SSH checks · What’s new 7.2 (subsystem)
```

---

## 15. Reference materials (optional lab)

Helpers in this repository for demos and script reuse—not required when using native SSH+NETCONF on a customer Zabbix 7.2+ estate:

| Path | Role |
|------|------|
| `README.md` | Lab stack quick start (native SSH NETCONF) |
| `docker-compose.yml` | Zabbix 7.4 + Postgres; `ZBX_STARTSSH` |
| `lab/srl.clab.yml` | Optional two-node SR Linux containerlab |
| `scripts/zabbix_register_hosts.py` | API: hosts + `ssh.run[...,netconf]` + dependents |
| `scripts/netconf_probe.py` | Optional capability / hostname probes |
| `scripts/netconf_optics_inventory.py` | Optional optics inventory |
| `scripts/netconf_poller.py` | **Legacy** trapper poller (fallback only) |

Official Zabbix references:

- [SSH agent items (subsystem / NETCONF examples)](https://www.zabbix.com/documentation/current/en/manual/config/items/itemtypes/ssh_checks)  
- [What’s new in Zabbix 7.2 — NETCONF via SSH subsystem](https://www.zabbix.com/whats_new_7_2)  
- Template pattern: **Juniper MX by NETCONF** (SSH masters + preprocessing + dependents)

---

## Document control

| | |
|--|--|
| **Title** | Zabbix administrator guide: Onboarding Nokia 7250 IXR-X1b with NETCONF |
| **Primary method** | Zabbix ≥ 7.2 SSH agent + subsystem `netconf` |
| **Intended use** | Customer Zabbix operations / professional services runbook |
| **Related lab** | Two-node SR Linux containerlab in this repo (`lab/srl.clab.yml`) |
| **Revision note** | Lab stack migrated from poller→trapper to native `ssh.run[...,netconf]` (Zabbix 7.4, StartSSH, SRL client hello + YANG namespaces, `ZBX_TIMEOUT`) |
