// Workshop deck for PRD 2.2 — AI Assisted Event Review & Rule Governance (Phase 1 MVP)
// Embeds REAL evidence screenshots captured from the running /admin UI.
const pptxgen = require("pptxgenjs");
const fs = require("fs");

const IMG = "D:/AI/screen-watcher-pro/workshop/evidence/";
const dim = f => { const b = fs.readFileSync(IMG + f); return { w: b.readUInt32BE(16), h: b.readUInt32BE(20) }; };

// ---- palette (informed by the app's own UI colors) ----
const INK = "172033", BG = "EEF1F5", CARD = "FFFFFF", BLUE = "24466E",
      RED = "D63031", GREEN = "1F8A4C", AMBER = "B06E00", MUTED = "5A6474",
      ICE = "CADCFC", LINE = "D9DFE7", INKSOFT = "9FB0C9";
const HEAD = "Cambria", BODY = "Calibri", MONO = "Consolas";
const W = 13.33, H = 7.5;

const pres = new pptxgen();
pres.defineLayout({ name: "WIDE", width: W, height: H });
pres.layout = "WIDE";
pres.author = "Screen Watcher Pro";
pres.title = "PRD 2.2 — AI Assisted Event Review & Rule Governance";

const shadow = () => ({ type: "outer", color: "000000", blur: 7, offset: 3, angle: 90, opacity: 0.13 });

// place an image contained inside a box, centered
function img(slide, file, bx, by, bw, bh) {
  const { w, h } = dim(file);
  const r = Math.min(bw / w, bh / h);
  const iw = w * r, ih = h * r;
  slide.addImage({ path: IMG + file, x: bx + (bw - iw) / 2, y: by + (bh - ih) / 2, w: iw, h: ih });
}

function titleBar(slide, kicker, title) {
  slide.addText(kicker.toUpperCase(), { x: 0.6, y: 0.42, w: 12, h: 0.3, fontFace: BODY,
    fontSize: 12, color: BLUE, bold: true, charSpacing: 2, margin: 0 });
  slide.addText(title, { x: 0.6, y: 0.68, w: 12.1, h: 0.7, fontFace: HEAD, fontSize: 30,
    color: INK, bold: true, margin: 0 });
}

function card(slide, x, y, w, h, fill) {
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.09,
    fill: { color: fill || CARD }, line: { color: LINE, width: 1 }, shadow: shadow() });
}

function chip(slide, x, y, txt, col) {
  const w = 0.24 + txt.length * 0.098;
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h: 0.32, rectRadius: 0.16,
    fill: { color: col } });
  slide.addText(txt, { x, y, w, h: 0.32, fontFace: BODY, fontSize: 11, bold: true,
    color: "FFFFFF", align: "center", valign: "middle", margin: 0 });
  return w;
}

// ============================================================ SLIDE 1 — TITLE
(() => {
  const s = pres.addSlide();
  s.background = { color: INK };
  s.addShape(pres.shapes.OVAL, { x: 10.3, y: -1.5, w: 5.2, h: 5.2, fill: { color: "20304C" } });
  s.addShape(pres.shapes.OVAL, { x: 11.6, y: 4.4, w: 3.6, h: 3.6, fill: { color: "1d2a42" } });
  s.addText("SCREEN WATCHER PRO", { x: 0.85, y: 1.15, w: 10, h: 0.4, fontFace: BODY,
    fontSize: 14, color: INKSOFT, bold: true, charSpacing: 3, margin: 0 });
  s.addText("AI Assisted Event Review\n& Rule Governance", { x: 0.8, y: 1.7, w: 11.4, h: 2.1,
    fontFace: HEAD, fontSize: 46, color: "FFFFFF", bold: true, lineSpacingMultiple: 1.0, margin: 0 });
  s.addText([
    { text: "PRD 2.2", options: { bold: true, color: "FFD764" } },
    { text: "  ·  Phase 1 MVP", options: { color: ICE } },
  ], { x: 0.85, y: 3.95, w: 10, h: 0.5, fontFace: BODY, fontSize: 20, margin: 0 });
  s.addText("AI Review cấp 1   ·   User Review cấp 2   ·   Console SOS   ·   Rule Governance có audit",
    { x: 0.85, y: 4.7, w: 11.5, h: 0.4, fontFace: BODY, fontSize: 15, color: INKSOFT, margin: 0 });
  // footer chips
  s.addShape(pres.shapes.LINE, { x: 0.85, y: 5.7, w: 11.6, h: 0, line: { color: "2c3c58", width: 1 } });
  const foot = [["106/106", "unit tests PASS"], ["6", "bảng + 4 service mới"], ["GR22-001…004", "governance enforced"]];
  foot.forEach(([a, b], i) => {
    const x = 0.85 + i * 4.0;
    s.addText(a, { x, y: 5.9, w: 3.7, h: 0.5, fontFace: HEAD, fontSize: 26, bold: true, color: "FFD764", margin: 0 });
    s.addText(b, { x, y: 6.45, w: 3.7, h: 0.4, fontFace: BODY, fontSize: 13, color: INKSOFT, margin: 0 });
  });
  s.addText("Workshop demo  ·  09/07/2026", { x: 8.5, y: 6.9, w: 4, h: 0.3, fontFace: BODY,
    fontSize: 11, color: "6d7d99", align: "right", margin: 0 });
})();

// ============================================ SLIDE 2 — VẤN ĐỀ & GIẢI PHÁP
(() => {
  const s = pres.addSlide(); s.background = { color: BG };
  titleBar(s, "Bối cảnh", "Vấn đề & Giải pháp");
  // problem card
  card(s, 0.6, 1.7, 5.9, 5.2, "FFFFFF");
  s.addText("VẤN ĐỀ HIỆN TẠI", { x: 0.95, y: 1.95, w: 5.3, h: 0.4, fontFace: BODY, fontSize: 13,
    bold: true, color: RED, charSpacing: 1, margin: 0 });
  s.addText("Watcher core đã có capture/OCR/rule/email, nhưng THIẾU lớp quản trị Event–Rule–Review:",
    { x: 0.95, y: 2.35, w: 5.25, h: 0.8, fontFace: BODY, fontSize: 13.5, color: INK, margin: 0 });
  const probs = [
    "Nhiều alert SAI → nhiễu, mất niềm tin",
    "BỎ SÓT Incident quan trọng chưa có rule",
    "Người vận hành phải review THỦ CÔNG quá nhiều",
    "Rule thay đổi KHÔNG có kiểm soát / audit",
  ];
  s.addText(probs.map((t, i) => ({ text: t, options: { bullet: { code: "2022" }, color: INK,
    breakLine: true, paraSpaceAfter: 10 } })),
    { x: 1.0, y: 3.25, w: 5.2, h: 3.4, fontFace: BODY, fontSize: 14, margin: 0 });

  // solution card
  card(s, 6.85, 1.7, 5.9, 5.2, "FFFFFF");
  s.addText("GIẢI PHÁP — PRD 2.2", { x: 7.2, y: 1.95, w: 5.3, h: 0.4, fontFace: BODY, fontSize: 13,
    bold: true, color: GREEN, charSpacing: 1, margin: 0 });
  const steps = [
    ["1", "AI Review cấp 1", "Phân loại Event mới, đánh giá risk, đề xuất action / Draft Rule", AMBER],
    ["2", "User Review cấp 2", "Người duyệt Approve / Edit / Reject đề xuất của AI", BLUE],
    ["3", "Rule Governance", "AI KHÔNG tự Active rule — mọi thay đổi có audit đầy đủ", GREEN],
    ["4", "SOS Alert (console)", "Incident rule khớp → rú âm thanh nền + Acknowledge", RED],
  ];
  steps.forEach(([n, t, d, c], i) => {
    const y = 2.45 + i * 1.06;
    s.addShape(pres.shapes.OVAL, { x: 7.2, y, w: 0.5, h: 0.5, fill: { color: c } });
    s.addText(n, { x: 7.2, y, w: 0.5, h: 0.5, fontFace: HEAD, fontSize: 18, bold: true,
      color: "FFFFFF", align: "center", valign: "middle", margin: 0 });
    s.addText(t, { x: 7.85, y: y - 0.05, w: 4.7, h: 0.4, fontFace: BODY, fontSize: 15, bold: true,
      color: INK, margin: 0 });
    s.addText(d, { x: 7.85, y: y + 0.33, w: 4.75, h: 0.6, fontFace: BODY, fontSize: 12,
      color: MUTED, margin: 0 });
  });
})();

// ============================================ SLIDE 3 — DOMAIN FLOW TO-BE
(() => {
  const s = pres.addSlide(); s.background = { color: BG };
  titleBar(s, "Kiến trúc", "Luồng xử lý To-Be");
  // top bar: pipeline
  const top = ["Sự kiện (capture + OCR)", "Normalize", "Store SQLite", "Evaluate · ACTIVE rules_db"];
  const tw = 2.95, gap = 0.15; let x = 0.6;
  top.forEach((t, i) => {
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: 1.75, w: tw, h: 0.8, rectRadius: 0.08,
      fill: { color: INK }, shadow: shadow() });
    s.addText(t, { x, y: 1.75, w: tw, h: 0.8, fontFace: BODY, fontSize: 12.5, bold: true,
      color: "FFFFFF", align: "center", valign: "middle", margin: 0 });
    if (i < 3) s.addShape(pres.shapes.LINE, { x: x + tw, y: 2.15, w: gap, h: 0,
      line: { color: MUTED, width: 1.5, endArrowType: "triangle" } });
    x += tw + gap;
  });
  // three lanes
  const laneY = [3.05, 4.35, 5.65];
  const laneMeta = [
    ["Khớp INCIDENT Rule", RED, "FDECEC", [["🚨 SOS Alert", RED], ["Console rú + Acknowledge", INK]]],
    ["Khớp Normal Rule", BLUE, "EAF0F8", [["Alert / Email", BLUE], ["(giữ nguyên flow cũ)", MUTED]]],
    ["KHÔNG khớp rule", AMBER, "FBF1DF", [["AI Review cấp 1", AMBER], ["Draft Rule (AI_SUGGESTED)", AMBER], ["User Review cấp 2", BLUE], ["ACTIVE ✅ / REJECTED ✋", GREEN]]],
  ];
  laneMeta.forEach(([label, col, tint, boxes], li) => {
    const y = laneY[li];
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 0.6, y, w: 2.55, h: 0.95, rectRadius: 0.08,
      fill: { color: tint }, line: { color: col, width: 1.5 } });
    s.addText(label, { x: 0.6, y, w: 2.55, h: 0.95, fontFace: BODY, fontSize: 12.5, bold: true,
      color: col, align: "center", valign: "middle", margin: 0 });
    let bx = 3.5;
    const bw = li === 2 ? 2.05 : 3.4;
    s.addShape(pres.shapes.LINE, { x: 3.15, y: y + 0.47, w: 0.35, h: 0,
      line: { color: col, width: 1.5, endArrowType: "triangle" } });
    boxes.forEach(([bt, bc], bi) => {
      s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: bx, y, w: bw, h: 0.95, rectRadius: 0.08,
        fill: { color: "FFFFFF" }, line: { color: LINE, width: 1 }, shadow: shadow() });
      s.addText(bt, { x: bx, y, w: bw, h: 0.95, fontFace: BODY, fontSize: 12, bold: true,
        color: bc, align: "center", valign: "middle", margin: 0 });
      if (bi < boxes.length - 1) s.addShape(pres.shapes.LINE, { x: bx + bw, y: y + 0.47, w: 0.22, h: 0,
        line: { color: MUTED, width: 1.3, endArrowType: "triangle" } });
      bx += bw + 0.22;
    });
  });
  s.addText("GR22-001: rule do AI đề xuất chỉ ở AI_SUGGESTED (enabled=0) — chỉ người dùng mới được đưa lên ACTIVE.",
    { x: 0.6, y: 6.85, w: 12.1, h: 0.4, fontFace: BODY, fontSize: 12.5, italic: true, color: MUTED, margin: 0 });
})();

// ============================================ SLIDE 4 — CONSOLE SOS ⭐
(() => {
  const s = pres.addSlide(); s.background = { color: BG };
  titleBar(s, "Điểm mới chính ⭐", "Console SOS Alarm — rú kể cả khi UI đóng");
  // left bullets
  card(s, 0.6, 1.7, 4.7, 5.2, "FFFFFF");
  s.addText("Vì sao chạy trên console?", { x: 0.9, y: 1.9, w: 4.2, h: 0.4, fontFace: BODY,
    fontSize: 14, bold: true, color: RED, margin: 0 });
  const pts = [
    "Job nền (thread) poll bảng sos_alerts mỗi 3 giây",
    "Incident rule khớp → tạo SOS PENDING → beep ngay",
    "Beep bằng winsound (Windows) / '\\a' (khác)",
    "Rú lại mỗi 300s cho tới khi có người Acknowledge",
    "Chạy trong tiến trình server & desktop → không cần mở web UI",
    "Acknowledge ghi lại người + thời điểm (GR22-004)",
  ];
  s.addText(pts.map(t => ({ text: t, options: { bullet: { code: "2022" }, breakLine: true,
    paraSpaceAfter: 12, color: INK } })),
    { x: 0.95, y: 2.4, w: 4.15, h: 4.3, fontFace: BODY, fontSize: 13.5, margin: 0 });

  // right: SOS panel screenshot on top
  card(s, 5.5, 1.7, 7.25, 2.75, "FFFFFF");
  img(s, "s03_sos_pending.png", 5.62, 1.82, 7.0, 2.5);
  // terminal box below with the real banner
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 5.5, y: 4.55, w: 7.25, h: 2.5, rectRadius: 0.06,
    fill: { color: "0E1420" }, line: { color: "31405c", width: 1 }, shadow: shadow() });
  s.addText("console — uvicorn (app/jobs/sos_watcher_job.py)", { x: 5.72, y: 4.64, w: 6.9, h: 0.3,
    fontFace: MONO, fontSize: 10, color: "6d7d99", margin: 0 });
  s.addText([
    { text: "18:57:09  sos  SOS alert created: Payment declined / fraud (INCIDENT)\n", options: { color: "b9c4d6", breakLine: true } },
    { text: "🚨🚨🚨 [SOS] CRITICAL — Incident rule 'payment_declined_incident'\n", options: { color: "ff6b6b", bold: true, breakLine: true } },
    { text: "         matched event EVT-019f46bd… @ 2026-07-09T18:57:09 🚨🚨🚨\n", options: { color: "ff6b6b", bold: true, breakLine: true } },
    { text: "18:57:11  sos_job  SOS ALARM: severity=CRITICAL\n", options: { color: "ffd764", breakLine: true } },
    { text: "— 5 phút sau, CHƯA ack → TỰ RÚ LẠI —\n", options: { color: "7fd39a", italic: true, breakLine: true } },
    { text: "19:02:14  sos_job  SOS ALARM: severity=CRITICAL", options: { color: "ffd764" } },
  ], { x: 5.72, y: 4.98, w: 6.95, h: 1.78, fontFace: MONO, fontSize: 10.5, lineSpacingMultiple: 1.0, margin: 0 });
})();

// ============================================ SLIDE 5 — AI REVIEW → REVIEW QUEUE
(() => {
  const s = pres.addSlide(); s.background = { color: BG };
  titleBar(s, "AI Review cấp 1", "Phân loại & đề xuất → Review Queue");
  card(s, 6.05, 1.68, 6.75, 5.35, "FFFFFF");
  img(s, "s02_review_queue.png", 6.17, 1.8, 6.5, 5.1);
  // left: output spec
  card(s, 0.6, 1.68, 5.2, 5.35, "FFFFFF");
  s.addText("Output bắt buộc của AI Review", { x: 0.9, y: 1.9, w: 4.6, h: 0.4, fontFace: BODY,
    fontSize: 14, bold: true, color: AMBER, margin: 0 });
  const rows = [
    ["classification", "nhãn phân loại sự kiện"],
    ["risk_level", "LOW / MEDIUM / HIGH / CRITICAL"],
    ["confidence", "độ tin cậy 0.0 – 1.0"],
    ["reason", "giải thích ngắn gọn"],
    ["suggested_action", "IGNORE / MONITOR / CREATE_DRAFT_RULE"],
    ["suggested_rule", "JSON rule đề xuất (nếu cần)"],
  ];
  rows.forEach(([k, v], i) => {
    const y = 2.45 + i * 0.72;
    s.addText(k, { x: 0.95, y, w: 4.6, h: 0.3, fontFace: MONO, fontSize: 13, bold: true, color: INK, margin: 0 });
    s.addText(v, { x: 0.95, y: y + 0.3, w: 4.6, h: 0.3, fontFace: BODY, fontSize: 12, color: MUTED, margin: 0 });
  });
  s.addText([
    { text: "An toàn: ", options: { bold: true, color: INK } },
    { text: "timeout 120s → RETRY_REQUIRED · JSON sai → FAILED · OCR cắt 6000 ký tự, không log nội dung.",
      options: { color: MUTED } },
  ], { x: 0.9, y: 6.5, w: 4.9, h: 0.5, fontFace: BODY, fontSize: 11.5, italic: true, margin: 0 });
})();

// ============================================ SLIDE 6 — RULE GOVERNANCE
(() => {
  const s = pres.addSlide(); s.background = { color: BG };
  titleBar(s, "Rule Governance", "AI đề xuất — Con người quyết định");
  card(s, 0.6, 1.68, 7.3, 5.35, "FFFFFF");
  img(s, "s08_rules_after.png", 0.72, 1.8, 7.06, 5.1);
  s.addText("rules_db: draft do AI (ai_review) → 1 đã APPROVE thành ACTIVE, 1 bị REJECTED (giữ lại + lý do)",
    { x: 0.72, y: 6.95, w: 7.1, h: 0.35, fontFace: BODY, fontSize: 10.5, italic: true, color: MUTED, margin: 0 });
  // right: 4 governance rules
  const gy = 1.68;
  const gr = [
    ["GR22-001", "AI KHÔNG được set rule = ACTIVE/enabled → GovernanceError", RED],
    ["GR22-002", "Incident rule phải do người tạo/approve trước khi phát SOS", BLUE],
    ["GR22-003", "Rule REJECTED được GIỮ lại (soft) kèm reject_reason", AMBER],
    ["GR22-004", "SOS acknowledge ghi acknowledged_by + acknowledged_at", GREEN],
  ];
  gr.forEach(([code, desc, col], i) => {
    const y = gy + i * 1.02;
    card(s, 8.1, y, 4.65, 0.88, "FFFFFF");
    chip(s, 8.32, y + 0.16, code, col);
    s.addText(desc, { x: 8.32, y: y + 0.52, w: 4.25, h: 0.32, fontFace: BODY, fontSize: 11.5,
      color: INK, margin: 0 });
  });
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 8.1, y: gy + 4.14, w: 4.65, h: 1.2, rectRadius: 0.08,
    fill: { color: "E7F5EC" }, line: { color: GREEN, width: 1.2 } });
  s.addText("10 / 10", { x: 8.25, y: gy + 4.28, w: 1.95, h: 0.7, fontFace: HEAD, fontSize: 32, bold: true,
    color: GREEN, align: "center", valign: "middle", margin: 0 });
  s.addText("governance\ntests PASSED", { x: 10.3, y: gy + 4.3, w: 2.35, h: 0.9, fontFace: BODY,
    fontSize: 13, bold: true, color: INK, valign: "middle", margin: 0 });
})();

// ============================================ SLIDE 7 — USER REVIEW APPROVE/REJECT
(() => {
  const s = pres.addSlide(); s.background = { color: BG };
  titleBar(s, "User Review cấp 2", "Approve → ACTIVE · Reject (bắt buộc lý do)");
  // approve column
  card(s, 0.6, 1.75, 6.0, 5.1, "FFFFFF");
  s.addShape(pres.shapes.OVAL, { x: 0.9, y: 2.0, w: 0.55, h: 0.55, fill: { color: GREEN } });
  s.addText("✓", { x: 0.9, y: 2.0, w: 0.55, h: 0.55, fontFace: BODY, fontSize: 22, bold: true,
    color: "FFFFFF", align: "center", valign: "middle", margin: 0 });
  s.addText("APPROVE", { x: 1.6, y: 2.05, w: 4.6, h: 0.45, fontFace: HEAD, fontSize: 20, bold: true, color: GREEN, margin: 0 });
  s.addText([
    { text: "POST /api/ai/reviews/{id}/approve", options: { fontFace: MONO, color: INK, breakLine: true, paraSpaceAfter: 8 } },
    { text: "→ Draft rule chuyển ACTIVE (enabled=1)", options: { color: INK, breakLine: true, paraSpaceAfter: 6 } },
    { text: "→ Event chuyển CONFIRMED_ISSUE", options: { color: INK, breakLine: true, paraSpaceAfter: 6 } },
    { text: "→ Audit: review.approve + rule.active", options: { color: MUTED, breakLine: true } },
  ], { x: 0.95, y: 2.75, w: 5.3, h: 1.9, fontFace: BODY, fontSize: 13.5, margin: 0 });
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 0.95, y: 5.0, w: 5.35, h: 1.55, rectRadius: 0.06,
    fill: { color: "0E1420" } });
  s.addText([
    { text: "// kết quả thực tế (evidence)\n", options: { color: "6d7d99", breakLine: true } },
    { text: '"rule_status": "ACTIVE",\n', options: { color: "7fd39a", breakLine: true } },
    { text: '"event_status": "CONFIRMED_ISSUE"', options: { color: "7fd39a" } },
  ], { x: 1.15, y: 5.16, w: 5.0, h: 1.25, fontFace: MONO, fontSize: 12.5, lineSpacingMultiple: 1.1, margin: 0 });

  // reject column
  card(s, 6.8, 1.75, 5.95, 5.1, "FFFFFF");
  s.addShape(pres.shapes.OVAL, { x: 7.1, y: 2.0, w: 0.55, h: 0.55, fill: { color: RED } });
  s.addText("✕", { x: 7.1, y: 2.0, w: 0.55, h: 0.55, fontFace: BODY, fontSize: 20, bold: true,
    color: "FFFFFF", align: "center", valign: "middle", margin: 0 });
  s.addText("REJECT", { x: 7.8, y: 2.05, w: 4.6, h: 0.45, fontFace: HEAD, fontSize: 20, bold: true, color: RED, margin: 0 });
  s.addText([
    { text: "Bắt buộc nhập reject_reason", options: { bold: true, color: INK, breakLine: true, paraSpaceAfter: 6 } },
    { text: "→ Thiếu lý do: HTTP 422 (từ chối)", options: { color: INK, breakLine: true, paraSpaceAfter: 6 } },
    { text: "→ Rule chuyển REJECTED nhưng GIỮ lại", options: { color: INK, breakLine: true, paraSpaceAfter: 6 } },
    { text: "→ Event chuyển IGNORED", options: { color: INK, breakLine: true, paraSpaceAfter: 6 } },
    { text: "→ Audit: review.reject + rule.rejected (kèm lý do)", options: { color: MUTED } },
  ], { x: 7.15, y: 2.75, w: 5.3, h: 2.2, fontFace: BODY, fontSize: 13.5, margin: 0 });
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 7.15, y: 5.25, w: 5.35, h: 1.3, rectRadius: 0.06,
    fill: { color: "FDECEC" }, line: { color: RED, width: 1 } });
  s.addText([
    { text: "GR22-003  ", options: { bold: true, color: RED } },
    { text: "“Không xoá cứng” — rule bị từ chối vẫn tra cứu được kèm lý do, phục vụ audit.",
      options: { color: INK } },
  ], { x: 7.35, y: 5.4, w: 5.0, h: 1.0, fontFace: BODY, fontSize: 12.5, valign: "middle", margin: 0 });
})();

// ============================================ SLIDE 8 — RBAC & AUDIT
(() => {
  const s = pres.addSlide(); s.background = { color: BG };
  titleBar(s, "Bảo mật & Truy vết", "RBAC theo vai trò + Audit đầy đủ");
  card(s, 0.6, 1.68, 7.55, 5.35, "FFFFFF");
  img(s, "s09_audit_after.png", 0.72, 1.8, 7.31, 5.1);
  s.addText("/admin/audit — mọi approve/reject/enable/disable/acknowledge đều ghi log", {
    x: 0.72, y: 6.95, w: 7.3, h: 0.3, fontFace: BODY, fontSize: 10.5, italic: true, color: MUTED, margin: 0 });
  // RBAC table on right
  const rx = 8.35, ry = 1.75;
  s.addText("Kiểm chứng RBAC (evidence)", { x: rx, y: ry, w: 4.4, h: 0.4, fontFace: BODY,
    fontSize: 14, bold: true, color: BLUE, margin: 0 });
  const tbl = [
    [{ text: "Hành động", options: { bold: true, color: "FFFFFF", fill: { color: INK } } },
     { text: "viewer", options: { bold: true, color: "FFFFFF", fill: { color: INK }, align: "center" } },
     { text: "operator", options: { bold: true, color: "FFFFFF", fill: { color: INK }, align: "center" } },
     { text: "admin", options: { bold: true, color: "FFFFFF", fill: { color: INK }, align: "center" } }],
    ["Xem Events / SOS", "✔", "✔", "✔"],
    ["Approve / Reject review", "403", "✔", "✔"],
    ["Tạo / sửa Rule", "403", "403", "✔"],
    ["Xem Audit log", "403", "403", "✔"],
    ["Acknowledge SOS", "✔", "✔", "✔"],
  ].map((r, ri) => r.map(c => typeof c === "string"
    ? { text: c, options: { align: ri === 0 ? "left" : (c === c.toUpperCase() && c.length < 4 ? "center" : "left"),
        color: c === "403" ? RED : (c === "✔" ? GREEN : INK), bold: c === "403" || c === "✔",
        fontSize: 12 } } : c));
  s.addTable(tbl, { x: rx, y: ry + 0.5, w: 4.4, colW: [2.15, 0.75, 0.85, 0.65], rowH: 0.5,
    border: { pt: 0.5, color: LINE }, fontFace: BODY, fontSize: 12, valign: "middle", align: "center" });
  s.addText([
    { text: "SOS ack: ", options: { bold: true, color: INK } },
    { text: "double-ack trả HTTP 400 — không thể ack lặp; ghi acknowledged_by=admin.", options: { color: MUTED } },
  ], { x: rx, y: 5.55, w: 4.45, h: 0.9, fontFace: BODY, fontSize: 12, italic: true, valign: "top", margin: 0 });
})();

// ============================================ SLIDE 9 — REUSE vs ADD
(() => {
  const s = pres.addSlide(); s.background = { color: BG };
  titleBar(s, "Cách tiếp cận", "Tái sử dụng tối đa — chỉ thêm phần thiếu");
  card(s, 0.6, 1.75, 6.0, 5.1, "FFFFFF");
  s.addText("TÁI SỬ DỤNG (không đụng)", { x: 0.9, y: 2.0, w: 5.4, h: 0.4, fontFace: BODY,
    fontSize: 14, bold: true, color: GREEN, margin: 0 });
  const reuse = [
    "SQLite + Repository + UUIDv7, RBAC seed",
    "JWT auth (PBKDF2) + get_current_user / require_admin",
    "rule_engine — 5 loại rule (contains/regex/keywords…)",
    "FastAPI chat_server + /api/watcher + /api/chat",
    "notification / email service, issue vectorstore",
    "Chatbot tool-calling (mở rộng thêm 6 tool)",
    "Capture pipeline (bridge sang event flow)",
  ];
  s.addText(reuse.map(t => ({ text: t, options: { bullet: { code: "2713" }, breakLine: true,
    paraSpaceAfter: 10, color: INK } })),
    { x: 0.95, y: 2.5, w: 5.35, h: 4.2, fontFace: BODY, fontSize: 13.5, margin: 0 });

  card(s, 6.8, 1.75, 5.95, 5.1, "FFFFFF");
  s.addText("BỔ SUNG (Phase 1 MVP)", { x: 7.1, y: 2.0, w: 5.4, h: 0.4, fontFace: BODY,
    fontSize: 14, bold: true, color: BLUE, margin: 0 });
  const add = [
    "Migration 002_prd22.sql — 6 bảng (idempotent + backup)",
    "6 repository + 4 service (event/rule/ai_review/sos)",
    "GovernanceError — chốt chặn GR22-001",
    "Console SOS watcher job (poll + beep + ack)",
    "REST API prd22_routes — events/rules/review/sos/audit",
    "Web Admin UI /admin (Jinja2 + HTMX, poll 2s)",
    "6 chatbot tool mới (SOS/queue/approve/test/list)",
  ];
  s.addText(add.map(t => ({ text: t, options: { bullet: { code: "25B8" }, breakLine: true,
    paraSpaceAfter: 10, color: INK } })),
    { x: 7.15, y: 2.5, w: 5.35, h: 4.2, fontFace: BODY, fontSize: 13.5, margin: 0 });
})();

// ============================================ SLIDE 10 — TESTS & DELIVERABLES
(() => {
  const s = pres.addSlide(); s.background = { color: BG };
  titleBar(s, "Chất lượng", "Kiểm thử & Bàn giao");
  const stats = [["106", "unit tests PASS", GREEN], ["35", "test PRD 2.2", BLUE], ["10", "governance tests", AMBER]];
  stats.forEach(([n, l, c], i) => {
    const x = 0.6 + i * 4.05;
    card(s, x, 1.75, 3.75, 1.7, "FFFFFF");
    s.addText(n, { x: x, y: 1.85, w: 3.75, h: 1.0, fontFace: HEAD, fontSize: 52, bold: true,
      color: c, align: "center", valign: "middle", margin: 0 });
    s.addText(l, { x: x, y: 2.85, w: 3.75, h: 0.5, fontFace: BODY, fontSize: 14, bold: true,
      color: INK, align: "center", margin: 0 });
  });
  card(s, 0.6, 3.75, 12.15, 3.15, "FFFFFF");
  s.addText("Bộ test (tests/) + Bàn giao", { x: 0.9, y: 3.95, w: 11.5, h: 0.4, fontFace: BODY,
    fontSize: 14, bold: true, color: BLUE, margin: 0 });
  const left = [
    "test_migration_prd22 — idempotent + backup + indexes",
    "test_sos_watcher_job — beep, cooldown, graceful stop",
    "test_event_service — SOS / email / AI review routing",
    "test_ai_review_governance — GR22-001…004",
    "test_prd22_routes — RBAC + happy path (API)",
  ];
  const right = [
    "002_prd22.sql + database.apply_migrations()",
    "app/services/*_service.py + prd22_bootstrap.py",
    "app/jobs/sos_watcher_job.py + FastAPI lifespan",
    "app/ai/prd22_routes.py + admin_ui/ (Jinja2/HTMX)",
    "README §9 (Mermaid) + RUNBOOK-PRD22.md (demo 5 bước)",
  ];
  s.addText(left.map(t => ({ text: t, options: { bullet: { code: "2713" }, breakLine: true,
    paraSpaceAfter: 9, color: INK } })), { x: 0.95, y: 4.45, w: 5.7, h: 2.4, fontFace: BODY,
    fontSize: 13, margin: 0 });
  s.addText(right.map(t => ({ text: t, options: { bullet: { code: "25B8" }, breakLine: true,
    paraSpaceAfter: 9, color: INK } })), { x: 6.95, y: 4.45, w: 5.6, h: 2.4, fontFace: BODY,
    fontSize: 13, margin: 0 });
})();

// ============================================ SLIDE 11 — DEMO 5 BƯỚC / CLOSING
(() => {
  const s = pres.addSlide(); s.background = { color: INK };
  s.addShape(pres.shapes.OVAL, { x: 10.6, y: -1.6, w: 5, h: 5, fill: { color: "20304C" } });
  s.addText("KỊCH BẢN DEMO", { x: 0.85, y: 0.7, w: 10, h: 0.4, fontFace: BODY, fontSize: 13,
    color: INKSOFT, bold: true, charSpacing: 3, margin: 0 });
  s.addText("Demo 5 bước — RUNBOOK-PRD22.md", { x: 0.8, y: 1.05, w: 11.5, h: 0.7, fontFace: HEAD,
    fontSize: 30, bold: true, color: "FFFFFF", margin: 0 });
  const steps = [
    ["1", "Capture trang “Payment declined” → Incident rule khớp → console TỰ RÚ 🚨 ngay (chưa cần UI)", RED],
    ["2", "Acknowledge tại /admin/sos → console DỪNG rú, ghi người + thời điểm", GREEN],
    ["3", "Capture text lạ chưa có rule → AI Review tạo Draft Rule → hiện ở /admin/review-queue", AMBER],
    ["4", "Admin Approve → Rule ACTIVE → lần capture sau khớp rule mới", BLUE],
    ["5", "Admin Reject kèm lý do → Rule REJECTED (giữ lại) → audit_logs ghi đầy đủ", "8A5CF6"],
  ];
  steps.forEach(([n, t, c], i) => {
    const y = 2.05 + i * 0.92;
    s.addShape(pres.shapes.OVAL, { x: 0.85, y, w: 0.62, h: 0.62, fill: { color: c } });
    s.addText(n, { x: 0.85, y, w: 0.62, h: 0.62, fontFace: HEAD, fontSize: 22, bold: true,
      color: "FFFFFF", align: "center", valign: "middle", margin: 0 });
    s.addText(t, { x: 1.7, y: y - 0.02, w: 9.4, h: 0.66, fontFace: BODY, fontSize: 15,
      color: "E7ECF5", valign: "middle", margin: 0 });
  });
  s.addShape(pres.shapes.LINE, { x: 0.85, y: 6.75, w: 11.6, h: 0, line: { color: "2c3c58", width: 1 } });
  s.addText("Chạy: uvicorn app.ai.chat_server:app --port 8000   ·   Admin: http://127.0.0.1:8000/admin",
    { x: 0.85, y: 6.9, w: 11.6, h: 0.4, fontFace: MONO, fontSize: 12, color: INKSOFT, margin: 0 });
})();

pres.writeFile({ fileName: "D:/AI/screen-watcher-pro/workshop/PRD2.2_Event_Review_Workshop.pptx" })
  .then(f => console.log("WROTE", f));
