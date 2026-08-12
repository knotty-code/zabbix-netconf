/**
 * PowerPoint from README.md — Zabbix NETCONF lab overview.
 */
const pptxgen = require("pptxgenjs");
const React = require("react");
const ReactDOMServer = require("react-dom/server");
const sharp = require("sharp");

function renderIconSvg(IC, color, size = 256) {
  return ReactDOMServer.renderToStaticMarkup(React.createElement(IC, { color, size: String(size) }));
}
async function iconPng(IC, color, sz = 256) {
  return "image/png;base64," + (await sharp(Buffer.from(renderIconSvg(IC, color, sz))).png().toBuffer()).toString("base64");
}

async function main() {
  const {
    FaServer, FaNetworkWired, FaShieldAlt, FaPlay, FaCog, FaEye, FaKey, FaFolderOpen
  } = require("react-icons/fa");

  const pres = new pptxgen();
  pres.layout = "LAYOUT_16x9";
  pres.author = "zabbix-netconf";
  pres.title = "Zabbix Lab — NETCONF Monitoring of Magic Kingdom X1b";
  pres.subject = "Overview from README.md";

  const C = {
    navy: "0F2B3C", teal: "0D7377", tealLight: "14A3A8",
    white: "FFFFFF", offWhite: "F4F7F6",
    gray: "6B7F82", dkGray: "4A5C60", darkText: "1A2E35",
    amber: "E8A838", green: "2D9B6E", red: "D94452",
  };
  const F = "DejaVu Sans";
  const shadow = () => ({ type: "outer", blur: 4, offset: 2, angle: 135, color: "000000", opacity: 0.08 });

  const TX = 0.5, TY = 0.38, TW = 9, TH = 0.35;
  const LBL_Y = 0.18, BODY_Y = 0.82, FTR_Y = 5.25, FTR_H = 0.375;
  const TOTAL = 7;

  function addFooter(sl, n) {
    sl.addShape(pres.shapes.RECTANGLE, { x: 0, y: FTR_Y, w: 10, h: FTR_H, fill: { color: C.navy } });
    sl.addText("Zabbix Lab · NETCONF · Magic Kingdom X1b", {
      x: 0.35, y: FTR_Y, w: 5.5, h: FTR_H, fontSize: 8, fontFace: F, color: C.tealLight, valign: "middle", margin: 0
    });
    sl.addText("No SNMP  ·  Native SSH NETCONF  ·  SR Linux", {
      x: 5.5, y: FTR_Y, w: 3.3, h: FTR_H, fontSize: 7, fontFace: F, color: C.white, valign: "middle", align: "center", margin: 0
    });
    sl.addText(`${n} / ${TOTAL}`, {
      x: 9.0, y: FTR_Y, w: 0.7, h: FTR_H, fontSize: 7, fontFace: F, color: C.white, align: "right", valign: "middle", margin: 0
    });
  }
  function addLabel(sl, t) {
    sl.addText(t, {
      x: TX, y: LBL_Y, w: TW, h: 0.16, fontSize: 9, fontFace: F, color: C.teal, charSpacing: 2.5, bold: true, margin: 0
    });
  }
  function addTitle(sl, t) {
    sl.addText(t, {
      x: TX, y: TY, w: TW, h: TH, fontSize: 15, fontFace: F, color: C.darkText, bold: true, margin: 0, valign: "middle"
    });
  }

  const icoServer = await iconPng(FaServer, "#14A3A8", 256);
  const icoNet = await iconPng(FaNetworkWired, "#14A3A8", 256);
  const icoShield = await iconPng(FaShieldAlt, "#14A3A8", 256);
  const icoPlay = await iconPng(FaPlay, "#FFFFFF", 256);
  const icoCog = await iconPng(FaCog, "#14A3A8", 256);
  const icoEye = await iconPng(FaEye, "#14A3A8", 256);
  const icoKey = await iconPng(FaKey, "#14A3A8", 256);
  const icoFolder = await iconPng(FaFolderOpen, "#14A3A8", 256);

  // ── 1 Title ───────────────────────────────────────────────
  let s = pres.addSlide();
  s.background = { color: C.navy };
  s.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: 0.12, h: 5.625, fill: { color: C.teal } });
  s.addShape(pres.shapes.RECTANGLE, { x: 6.35, y: 0, w: 3.65, h: 5.625, fill: { color: "0A2230" } });
  s.addShape(pres.shapes.RECTANGLE, { x: 6.35, y: 0, w: 0.06, h: 5.625, fill: { color: C.teal } });

  s.addText("LAB OVERVIEW", {
    x: 0.55, y: 1.2, w: 5.4, h: 0.28, fontSize: 11, fontFace: F, color: C.tealLight, charSpacing: 3, bold: true, margin: 0
  });
  s.addText("Zabbix Lab\nNETCONF Monitoring", {
    x: 0.55, y: 1.55, w: 5.4, h: 1.35, fontSize: 30, fontFace: F, color: C.white, bold: true, margin: 0
  });
  s.addShape(pres.shapes.RECTANGLE, { x: 0.55, y: 3.05, w: 2.6, h: 0.04, fill: { color: C.teal } });
  s.addText("Magic Kingdom border leafs\n7250 IXR-X1b · SR Linux · No SNMP", {
    x: 0.55, y: 3.25, w: 5.4, h: 0.7, fontSize: 14, fontFace: F, color: "A8C0C4", margin: 0
  });
  s.addText("From README.md · github.com/knotty-code/zabbix-netconf", {
    x: 0.55, y: 4.85, w: 5.4, h: 0.25, fontSize: 11, fontFace: F, color: C.gray, margin: 0
  });

  [
    { t: "bleaf1", d: "172.30.40.21" },
    { t: "bleaf2", d: "172.30.40.22" },
    { t: "UI", d: "localhost:8080" },
  ].forEach((row, i) => {
    const y = 1.35 + i * 1.1;
    s.addText(row.t, { x: 6.7, y: y, w: 3.0, h: 0.3, fontSize: 12, fontFace: F, color: C.tealLight, bold: true, margin: 0 });
    s.addText(row.d, { x: 6.7, y: y + 0.32, w: 3.0, h: 0.35, fontSize: 16, fontFace: F, color: C.white, bold: true, margin: 0 });
  });

  // ── 2 Targets ─────────────────────────────────────────────
  s = pres.addSlide();
  s.background = { color: C.offWhite };
  addFooter(s, 2);
  addLabel(s, "TARGETS");
  addTitle(s, "Containerlab X1b border leafs — monitor without SNMP");

  // host cards
  [
    { name: "bleaf1.magic-kingdom.io", role: "Border leaf", ip: "172.30.40.21", plat: "7250 IXR-X1b · SR Linux 26.3.1" },
    { name: "bleaf2.magic-kingdom.io", role: "Border leaf", ip: "172.30.40.22", plat: "7250 IXR-X1b · SR Linux 26.3.1" },
  ].forEach((h, i) => {
    const x = 0.5 + i * 4.7;
    s.addShape(pres.shapes.RECTANGLE, { x, y: BODY_Y, w: 4.45, h: 2.35, fill: { color: C.white }, shadow: shadow() });
    s.addShape(pres.shapes.RECTANGLE, { x, y: BODY_Y, w: 4.45, h: 0.1, fill: { color: C.teal } });
    s.addImage({ data: icoServer, x: x + 0.25, y: BODY_Y + 0.35, w: 0.36, h: 0.36 });
    s.addText(h.role, { x: x + 0.75, y: BODY_Y + 0.3, w: 3.4, h: 0.22, fontSize: 11, fontFace: F, color: C.teal, bold: true, margin: 0 });
    s.addText(h.name, { x: x + 0.75, y: BODY_Y + 0.55, w: 3.4, h: 0.35, fontSize: 14, fontFace: F, color: C.darkText, bold: true, margin: 0 });
    s.addText([
      { text: "Mgmt IP  ", options: { bold: true, color: C.dkGray } },
      { text: h.ip, options: { breakLine: true, color: C.darkText } },
      { text: "Platform  ", options: { bold: true, color: C.dkGray } },
      { text: h.plat, options: { color: C.darkText } },
    ], { x: x + 0.25, y: BODY_Y + 1.15, w: 3.95, h: 0.95, fontSize: 13, fontFace: F, margin: 0, paraSpaceAfter: 6 });
  });

  s.addShape(pres.shapes.RECTANGLE, { x: 0.5, y: BODY_Y + 2.6, w: 9.0, h: 1.35, fill: { color: C.white }, shadow: shadow() });
  s.addShape(pres.shapes.RECTANGLE, { x: 0.5, y: BODY_Y + 2.6, w: 0.08, h: 1.35, fill: { color: C.amber } });
  s.addText("Lab context", {
    x: 0.8, y: BODY_Y + 2.75, w: 8.5, h: 0.28, fontSize: 13, fontFace: F, color: C.darkText, bold: true, margin: 0
  });
  s.addText("Topology: repo-hq-magic-kingdom/eda/lab/magic-kingdom.clab.yml\nCredentials: admin / NokiaSrl1!   ·   Production (Zabbix ≥7.2): native ssh.run[...,netconf] — see ZABBIX-NETCONF-ADMIN-GUIDE", {
    x: 0.8, y: BODY_Y + 3.1, w: 8.5, h: 0.65, fontSize: 12, fontFace: F, color: C.dkGray, margin: 0
  });

  // ── 3 Quick start ─────────────────────────────────────────
  s = pres.addSlide();
  s.background = { color: C.offWhite };
  addFooter(s, 3);
  addLabel(s, "QUICK START");
  addTitle(s, "Bring up the stack and register hosts");

  const steps = [
    { n: "1", t: "git clone …/zabbix-netconf", d: "Requires containerlab network magic-kingdom-mgmt" },
    { n: "2", t: "docker compose up -d", d: "Postgres · Zabbix 7.4 · web · StartSSH pollers" },
    { n: "3", t: "python3 scripts/zabbix_register_bleafs.py", d: "Hosts + native ssh.run[...,netconf] items" },
    { n: "4", t: "Open UI → Latest data", d: "Magic Kingdom · ssh.run masters + netconf.*" },
  ];
  steps.forEach((st, i) => {
    const y = BODY_Y + i * 0.95;
    s.addShape(pres.shapes.RECTANGLE, { x: 0.5, y, w: 9.0, h: 0.85, fill: { color: C.white }, shadow: shadow() });
    s.addShape(pres.shapes.OVAL, { x: 0.7, y: y + 0.18, w: 0.5, h: 0.5, fill: { color: C.teal } });
    s.addText(st.n, {
      x: 0.7, y: y + 0.18, w: 0.5, h: 0.5, fontSize: 16, fontFace: F, color: C.white, bold: true, align: "center", valign: "middle", margin: 0
    });
    s.addText(st.t, {
      x: 1.45, y: y + 0.15, w: 7.8, h: 0.32, fontSize: 14, fontFace: F, color: C.darkText, bold: true, margin: 0
    });
    s.addText(st.d, {
      x: 1.45, y: y + 0.48, w: 7.8, h: 0.28, fontSize: 12, fontFace: F, color: C.dkGray, margin: 0
    });
  });

  // ── 4 Access ──────────────────────────────────────────────
  s = pres.addSlide();
  s.background = { color: C.offWhite };
  addFooter(s, 4);
  addLabel(s, "ACCESS");
  addTitle(s, "How to log in and find the data");

  const access = [
    { ico: icoEye, title: "Zabbix UI", body: "http://localhost:8080\nAdmin / zabbix" },
    { ico: icoNet, title: "SSH / NETCONF", body: "Port 22 on bleafs\nsubsystem netconf" },
    { ico: icoCog, title: "SSH pollers", body: "ZBX_STARTSSH=5\nNative Zabbix 7.4" },
    { ico: icoFolder, title: "Latest data path", body: "Monitoring → Latest data\nGroup: Magic Kingdom" },
  ];
  access.forEach((a, i) => {
    const col = i % 2, row = Math.floor(i / 2);
    const x = 0.5 + col * 4.7, y = BODY_Y + row * 1.85;
    s.addShape(pres.shapes.RECTANGLE, { x, y, w: 4.45, h: 1.7, fill: { color: C.white }, shadow: shadow() });
    s.addShape(pres.shapes.RECTANGLE, { x, y, w: 0.08, h: 1.7, fill: { color: C.teal } });
    s.addImage({ data: a.ico, x: x + 0.3, y: y + 0.35, w: 0.4, h: 0.4 });
    s.addText(a.title, {
      x: x + 0.9, y: y + 0.3, w: 3.3, h: 0.35, fontSize: 15, fontFace: F, color: C.darkText, bold: true, margin: 0
    });
    s.addText(a.body, {
      x: x + 0.9, y: y + 0.75, w: 3.3, h: 0.7, fontSize: 13, fontFace: F, color: C.dkGray, margin: 0
    });
  });

  // ── 5 Architecture ────────────────────────────────────────
  s = pres.addSlide();
  s.background = { color: C.offWhite };
  addFooter(s, 5);
  addLabel(s, "ARCHITECTURE");
  addTitle(s, "Native path: Zabbix SSH pollers → NETCONF subsystem on X1b");

  // flow boxes
  const boxes = [
    { x: 0.5, title: "Zabbix", sub: "SSH pollers\nStartSSH ≥ 1", fill: C.teal },
    { x: 3.5, title: "X1b bleafs", sub: "NETCONF/SSH\n:22 subsystem", fill: C.navy },
    { x: 6.5, title: "Items", sub: "ssh.run masters\n+ dependents", fill: C.teal },
  ];
  boxes.forEach((b, i) => {
    s.addShape(pres.shapes.RECTANGLE, {
      x: b.x, y: BODY_Y + 0.15, w: 2.7, h: 1.55, fill: { color: b.fill }, shadow: shadow()
    });
    s.addText(b.title, {
      x: b.x, y: BODY_Y + 0.35, w: 2.7, h: 0.4, fontSize: 16, fontFace: F, color: C.white, bold: true, align: "center", margin: 0
    });
    s.addText(b.sub, {
      x: b.x + 0.15, y: BODY_Y + 0.85, w: 2.4, h: 0.65, fontSize: 12, fontFace: F, color: "A8C0C4", align: "center", margin: 0
    });
    if (i < 2) {
      s.addText("→", {
        x: b.x + 2.55, y: BODY_Y + 0.55, w: 0.5, h: 0.5, fontSize: 22, fontFace: F, color: C.dkGray, bold: true, margin: 0
      });
    }
  });

  s.addShape(pres.shapes.RECTANGLE, { x: 0.5, y: BODY_Y + 2.0, w: 9.0, h: 2.0, fill: { color: C.white }, shadow: shadow() });
  s.addText("Why this design", {
    x: 0.75, y: BODY_Y + 2.15, w: 8.5, h: 0.3, fontSize: 14, fontFace: F, color: C.darkText, bold: true, margin: 0
  });
  s.addText([
    { text: "X1b runs SR Linux — SNMP was the operational pain point.", options: { breakLine: true } },
    { text: "Zabbix 7.2+ uses SSH agent + subsystem netconf (not a separate item type).", options: { breakLine: true } },
    { text: "Lab path: StartSSH pollers run RPCs; JS preprocessing fills netconf.* dependents.", options: { breakLine: true } },
    { text: "All Zabbix services join Docker network magic-kingdom-mgmt (same as containerlab).", options: {} },
  ], { x: 0.75, y: BODY_Y + 2.55, w: 8.5, h: 1.3, fontSize: 13, fontFace: F, color: C.dkGray, margin: 0, paraSpaceAfter: 4 });

  // ── 6 Metrics + NETCONF enable ────────────────────────────
  s = pres.addSlide();
  s.background = { color: C.offWhite };
  addFooter(s, 6);
  addLabel(s, "METRICS & DEVICE");
  addTitle(s, "SSH masters + dependents · NETCONF on SR Linux port 22");

  // left: items
  s.addShape(pres.shapes.RECTANGLE, { x: 0.5, y: BODY_Y, w: 4.45, h: 3.95, fill: { color: C.white }, shadow: shadow() });
  s.addShape(pres.shapes.RECTANGLE, { x: 0.5, y: BODY_Y, w: 4.45, h: 0.45, fill: { color: C.navy } });
  s.addText("Items (per host)", {
    x: 0.7, y: BODY_Y + 0.08, w: 4.0, h: 0.3, fontSize: 14, fontFace: F, color: C.white, bold: true, margin: 0
  });
  const items = [
    ["netconf.availability", "Probe success 1/0"],
    ["netconf.caps", "Capability smoke test"],
    ["netconf.hostname", "System host-name"],
    ["netconf.if.summary", "Interface oper summary"],
    ["netconf.version", "Software version"],
    ["netconf.optics.*", "Cages / present / missing"],
  ];
  items.forEach((row, i) => {
    const y = BODY_Y + 0.6 + i * 0.5;
    s.addText(row[0], { x: 0.7, y, w: 4.0, h: 0.22, fontSize: 12, fontFace: F, color: C.teal, bold: true, margin: 0 });
    s.addText(row[1], { x: 0.7, y: y + 0.2, w: 4.0, h: 0.22, fontSize: 11, fontFace: F, color: C.dkGray, margin: 0 });
  });

  // right: netconf enable
  s.addShape(pres.shapes.RECTANGLE, { x: 5.15, y: BODY_Y, w: 4.35, h: 3.95, fill: { color: C.white }, shadow: shadow() });
  s.addShape(pres.shapes.RECTANGLE, { x: 5.15, y: BODY_Y, w: 4.35, h: 0.45, fill: { color: C.teal } });
  s.addText("Enable on X1b (SRL)", {
    x: 5.35, y: BODY_Y + 0.08, w: 4.0, h: 0.3, fontSize: 14, fontFace: F, color: C.white, bold: true, margin: 0
  });
  s.addText("SSH subsystem on port 22\n(not classic 830)", {
    x: 5.35, y: BODY_Y + 0.6, w: 3.95, h: 0.55, fontSize: 12, fontFace: F, color: C.dkGray, margin: 0
  });
  s.addShape(pres.shapes.RECTANGLE, {
    x: 5.35, y: BODY_Y + 1.25, w: 3.95, h: 1.7, fill: { color: "1A2E35" }
  });
  s.addText("system netconf-server mgmt {\n    admin-state enable\n    ssh-server mgmt\n}", {
    x: 5.5, y: BODY_Y + 1.4, w: 3.65, h: 1.45, fontSize: 12, fontFace: "DejaVu Sans Mono", color: "A7E8D0", margin: 0
  });
  s.addText("Re-apply if EDA reconciles config.\ngNMI already on :57410 (EDA TLS).", {
    x: 5.35, y: BODY_Y + 3.15, w: 3.95, h: 0.6, fontSize: 11, fontFace: F, color: C.dkGray, margin: 0
  });

  // ── 7 Files & security ────────────────────────────────────
  s = pres.addSlide();
  s.background = { color: C.offWhite };
  addFooter(s, 7);
  addLabel(s, "FILES & SECURITY");
  addTitle(s, "Repo artifacts and lab-only credentials");

  const files = [
    { f: "ZABBIX-NETCONF-ADMIN-GUIDE", d: "Full admin handbook (+ .docx)" },
    { f: "docker-compose.yml", d: "Postgres + Zabbix 7.4 + StartSSH" },
    { f: "zabbix_register_bleafs.py", d: "API: hosts + ssh.run NETCONF" },
    { f: "netconf_probe.py", d: "Optional offline probe" },
    { f: "netconf_optics_inventory.py", d: "Optional optics inventory" },
    { f: "netconf_poller.py", d: "Legacy trapper only" },
  ];
  files.forEach((row, i) => {
    const col = i % 2, r = Math.floor(i / 2);
    const x = 0.5 + col * 4.7, y = BODY_Y + r * 0.95;
    s.addShape(pres.shapes.RECTANGLE, { x, y, w: 4.45, h: 0.85, fill: { color: C.white }, shadow: shadow() });
    s.addText(row.f, {
      x: x + 0.2, y: y + 0.12, w: 4.05, h: 0.3, fontSize: 12, fontFace: F, color: C.teal, bold: true, margin: 0
    });
    s.addText(row.d, {
      x: x + 0.2, y: y + 0.45, w: 4.05, h: 0.28, fontSize: 12, fontFace: F, color: C.dkGray, margin: 0
    });
  });

  s.addShape(pres.shapes.RECTANGLE, { x: 0.5, y: BODY_Y + 3.05, w: 9.0, h: 0.9, fill: { color: C.navy } });
  s.addImage({ data: icoKey, x: 0.7, y: BODY_Y + 3.28, w: 0.32, h: 0.32 });
  s.addText("Security: lab defaults only (Admin/zabbix, admin/NokiaSrl1!). Do not expose 8080/10051 beyond the lab host without hardening.", {
    x: 1.2, y: BODY_Y + 3.2, w: 8.0, h: 0.6, fontSize: 12, fontFace: F, color: C.white, margin: 0, valign: "middle"
  });

  const path = require("path");
  const out = path.join(__dirname, "Zabbix-Lab-NETCONF-Overview.pptx");
  await pres.writeFile({ fileName: out });
  console.log("Wrote", out);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
