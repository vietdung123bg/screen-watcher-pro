// Explainer deck (Vietnamese, beginner-friendly): how Screen Watcher uses
// ChromaDB (smart memory) and Hugging Face TTS (spoken alerts).
const pptxgen = require("pptxgenjs");
const fs = require("fs");
const IMG = "D:/AI/screen-watcher-pro/workshop/evidence/";
const dim = f => { const b = fs.readFileSync(IMG + f); return { w: b.readUInt32BE(16), h: b.readUInt32BE(20) }; };

const INK = "172033", BG = "EEF1F5", CARD = "FFFFFF", BLUE = "24466E",
      RED = "D63031", GREEN = "1F8A4C", AMBER = "B06E00", TEAL = "0E7C86",
      PURPLE = "6D4AA0", MUTED = "5A6474", ICE = "CADCFC", LINE = "D9DFE7", INKSOFT = "9FB0C9";
const HEAD = "Cambria", BODY = "Calibri", MONO = "Consolas";
const W = 13.33, H = 7.5;

const pres = new pptxgen();
pres.defineLayout({ name: "WIDE", width: W, height: H });
pres.layout = "WIDE";
pres.title = "Giải thích: ChromaDB & HuggingFace TTS";

const sh = () => ({ type: "outer", color: "000000", blur: 7, offset: 3, angle: 90, opacity: 0.13 });
function img(slide, file, bx, by, bw, bh) {
  const { w, h } = dim(file); const r = Math.min(bw / w, bh / h);
  slide.addImage({ path: IMG + file, x: bx + (bw - w * r) / 2, y: by + (bh - h * r) / 2, w: w * r, h: h * r });
}
function titleBar(s, kicker, title, col) {
  s.addText(kicker.toUpperCase(), { x: 0.6, y: 0.42, w: 12, h: 0.3, fontFace: BODY, fontSize: 12,
    color: col || BLUE, bold: true, charSpacing: 2, margin: 0 });
  s.addText(title, { x: 0.6, y: 0.68, w: 12.1, h: 0.7, fontFace: HEAD, fontSize: 30, color: INK, bold: true, margin: 0 });
}
function card(s, x, y, w, h, fill) {
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.09,
    fill: { color: fill || CARD }, line: { color: LINE, width: 1 }, shadow: sh() });
}
// analogy callout (light bulb style, tinted box)
function analogy(s, x, y, w, h, tint, border, text) {
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.08,
    fill: { color: tint }, line: { color: border, width: 1.2 } });
  s.addText([{ text: "💡 Ví von:  ", options: { bold: true, color: border } },
             { text: text, options: { color: INK } }],
    { x: x + 0.2, y, w: w - 0.4, h, fontFace: BODY, fontSize: 13.5, valign: "middle", margin: 0 });
}
function stepBox(s, x, y, w, h, icon, title, desc, col) {
  card(s, x, y, w, h, CARD);
  s.addText(icon, { x, y: y + 0.15, w, h: 0.6, fontFace: BODY, fontSize: 30, align: "center", margin: 0 });
  s.addText(title, { x: x + 0.1, y: y + 0.8, w: w - 0.2, h: 0.4, fontFace: BODY, fontSize: 14,
    bold: true, color: col, align: "center", margin: 0 });
  s.addText(desc, { x: x + 0.15, y: y + 1.2, w: w - 0.3, h: h - 1.3, fontFace: BODY, fontSize: 11.5,
    color: MUTED, align: "center", margin: 0 });
}
function arrow(s, x, y, w, col) {
  s.addShape(pres.shapes.LINE, { x, y, w, h: 0, line: { color: col || MUTED, width: 2, endArrowType: "triangle" } });
}

// ===================================================== SLIDE 1 — TITLE
(() => {
  const s = pres.addSlide(); s.background = { color: INK };
  s.addShape(pres.shapes.OVAL, { x: 10.2, y: -1.6, w: 5.4, h: 5.4, fill: { color: "20304C" } });
  s.addShape(pres.shapes.OVAL, { x: 11.5, y: 4.3, w: 3.8, h: 3.8, fill: { color: "1d2a42" } });
  s.addText("GIẢI THÍCH DỄ HIỂU", { x: 0.85, y: 1.2, w: 10, h: 0.4, fontFace: BODY, fontSize: 14,
    color: INKSOFT, bold: true, charSpacing: 3, margin: 0 });
  s.addText("ChromaDB & HuggingFace TTS\nhoạt động thế nào?", { x: 0.8, y: 1.75, w: 11.4, h: 1.9,
    fontFace: HEAD, fontSize: 42, color: "FFFFFF", bold: true, lineSpacingMultiple: 1.0, margin: 0 });
  s.addText("Hai \"trợ lý\" mới của Screen Watcher — kể cả không rành kỹ thuật vẫn hiểu",
    { x: 0.85, y: 4.05, w: 11, h: 0.5, fontFace: BODY, fontSize: 18, color: ICE, margin: 0 });
  s.addShape(pres.shapes.LINE, { x: 0.85, y: 5.5, w: 11.6, h: 0, line: { color: "2c3c58", width: 1 } });
  const f = [["🧠 ChromaDB", "trí nhớ nhận ra sự cố lặp lại"], ["🔊 HF TTS", "đọc cảnh báo thành giọng nói"]];
  f.forEach(([a, b], i) => {
    const x = 0.85 + i * 6.0;
    s.addText(a, { x, y: 5.75, w: 5.7, h: 0.5, fontFace: HEAD, fontSize: 22, bold: true, color: "FFD764", margin: 0 });
    s.addText(b, { x, y: 6.3, w: 5.7, h: 0.4, fontFace: BODY, fontSize: 14, color: INKSOFT, margin: 0 });
  });
})();

// ===================================================== SLIDE 2 — TỔNG QUAN
(() => {
  const s = pres.addSlide(); s.background = { color: BG };
  titleBar(s, "Tổng quan", "Hai trợ lý mới — mỗi cái giải quyết một nỗi đau");
  const cards = [
    ["🧠", "ChromaDB — Trí nhớ thông minh", TEAL, "F0F7F8",
      "Ghi nhớ các sự cố đã gặp. Khi có cảnh báo mới, nó tự hỏi:",
      "\"Cái này MỚI, hay mình ĐÃ TỪNG gặp rồi?\"",
      "→ Gom các cảnh báo trùng lặp, đỡ làm phiền người trực."],
    ["🔊", "HuggingFace TTS — Giọng nói cảnh báo", PURPLE, "F5F1FA",
      "Biến dòng chữ cảnh báo thành TIẾNG NÓI tiếng Việt phát ra loa.",
      "\"Cảnh báo nghiêm trọng. Hệ thống phát hiện gian lận…\"",
      "→ Nghe được ngay cả khi không nhìn màn hình."],
  ];
  cards.forEach(([ic, tt, col, tint, l1, l2, l3], i) => {
    const x = 0.6 + i * 6.15;
    card(s, x, 1.75, 5.9, 5.15, CARD);
    s.addShape(pres.shapes.OVAL, { x: x + 0.35, y: 2.05, w: 1.0, h: 1.0, fill: { color: tint }, line: { color: col, width: 1.5 } });
    s.addText(ic, { x: x + 0.35, y: 2.05, w: 1.0, h: 1.0, fontSize: 30, align: "center", valign: "middle", margin: 0 });
    s.addText(tt, { x: x + 1.5, y: 2.2, w: 4.2, h: 0.75, fontFace: HEAD, fontSize: 18, bold: true, color: col, valign: "middle", margin: 0 });
    s.addText(l1, { x: x + 0.4, y: 3.35, w: 5.1, h: 0.7, fontFace: BODY, fontSize: 14, color: INK, margin: 0 });
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: x + 0.4, y: 4.1, w: 5.1, h: 0.85, rectRadius: 0.06, fill: { color: tint } });
    s.addText(l2, { x: x + 0.55, y: 4.1, w: 4.8, h: 0.85, fontFace: BODY, fontSize: 13, italic: true, color: col, valign: "middle", margin: 0 });
    s.addText(l3, { x: x + 0.4, y: 5.15, w: 5.1, h: 1.4, fontFace: BODY, fontSize: 14, bold: true, color: INK, margin: 0 });
  });
})();

// ===================================================== SLIDE 3 — CHROMA: VÌ SAO
(() => {
  const s = pres.addSlide(); s.background = { color: BG };
  titleBar(s, "ChromaDB · Vấn đề", "Vì sao cần \"trí nhớ\"?", TEAL);
  // before
  card(s, 0.6, 1.75, 5.9, 3.4, "FFFFFF");
  s.addText("❌ Khi KHÔNG có trí nhớ", { x: 0.9, y: 1.95, w: 5.3, h: 0.4, fontFace: BODY, fontSize: 15, bold: true, color: RED, margin: 0 });
  s.addText([
    { text: "Mỗi cảnh báo bị coi là một sự cố MỚI", options: { bullet: { code: "2022" }, breakLine: true, paraSpaceAfter: 8 } },
    { text: "Cùng 1 lỗi lặp lại 10 lần → 10 lần làm phiền", options: { bullet: { code: "2022" }, breakLine: true, paraSpaceAfter: 8 } },
    { text: "Người trực bị \"ngập\" thông báo, dễ bỏ sót cái quan trọng", options: { bullet: { code: "2022" } } },
  ], { x: 0.95, y: 2.45, w: 5.2, h: 2.5, fontFace: BODY, fontSize: 14, color: INK, margin: 0 });
  // after
  card(s, 6.85, 1.75, 5.9, 3.4, "FFFFFF");
  s.addText("✅ Khi CÓ ChromaDB", { x: 7.15, y: 1.95, w: 5.3, h: 0.4, fontFace: BODY, fontSize: 15, bold: true, color: GREEN, margin: 0 });
  s.addText([
    { text: "Nhận ra \"cái này giống lần trước\" → gộp lại", options: { bullet: { code: "2713" }, breakLine: true, paraSpaceAfter: 8 } },
    { text: "Chỉ báo 1 lần + đếm số lần tái diễn", options: { bullet: { code: "2713" }, breakLine: true, paraSpaceAfter: 8 } },
    { text: "Người trực thấy đúng số sự cố THẬT SỰ khác nhau", options: { bullet: { code: "2713" } } },
  ], { x: 7.2, y: 2.45, w: 5.2, h: 2.5, fontFace: BODY, fontSize: 14, color: INK, margin: 0 });
  analogy(s, 0.6, 5.5, 12.15, 1.15, "F0F7F8", TEAL,
    "Giống như một thủ thư giỏi — bạn đưa một tờ báo cáo, họ lập tức nhớ ra \"à, vụ này tháng trước gặp rồi\", thay vì lưu thành hồ sơ mới toanh mỗi lần.");
})();

// ===================================================== SLIDE 4 — CHROMA: HOW
(() => {
  const s = pres.addSlide(); s.background = { color: BG };
  titleBar(s, "ChromaDB · Cách hoạt động", "3 bước — so khớp theo Ý NGHĨA, không theo câu chữ", TEAL);
  const y = 2.0, bw = 3.5, bh = 2.35;
  stepBox(s, 0.6, y, bw, bh, "📝", "1. Câu cảnh báo", "Ví dụ: \"Payment declined - fraud on card...\"", INK);
  arrow(s, 4.15, y + bh / 2, 0.45, TEAL);
  stepBox(s, 4.65, y, bw, bh, "🔢", "2. Dấu vân tay số", "AI đổi câu chữ thành một dãy số đại diện cho Ý NGHĨA (embedding)", TEAL);
  arrow(s, 8.2, y + bh / 2, 0.45, TEAL);
  stepBox(s, 8.7, y, bw, bh, "🗂️", "3. So với kho ký ức", "So dấu vân tay mới với các sự cố đã lưu trong ChromaDB", TEAL);
  // decision row
  const dy = 4.75;
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 0.6, y: dy, w: 5.95, h: 0.95, rectRadius: 0.08, fill: { color: "E7F5EC" }, line: { color: GREEN, width: 1.3 } });
  s.addText([{ text: "Giống ≥ 78%  →  ", options: { bold: true, color: GREEN } },
             { text: "\"ĐÃ TỪNG GẶP\" (đếm thêm 1 lần, không báo lại)", options: { color: INK } }],
    { x: 0.8, y: dy, w: 5.6, h: 0.95, fontFace: BODY, fontSize: 13.5, valign: "middle", margin: 0 });
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 6.8, y: dy, w: 5.95, h: 0.95, rectRadius: 0.08, fill: { color: "FFF3D6" }, line: { color: AMBER, width: 1.3 } });
  s.addText([{ text: "Khác nhiều  →  ", options: { bold: true, color: AMBER } },
             { text: "\"SỰ CỐ MỚI\" (lưu vào kho để lần sau nhận ra)", options: { color: INK } }],
    { x: 7.0, y: dy, w: 5.6, h: 0.95, fontFace: BODY, fontSize: 13.5, valign: "middle", margin: 0 });
  analogy(s, 0.6, 5.95, 12.15, 0.95, "F0F7F8", TEAL,
    "\"Dấu vân tay số\" giúp máy hiểu 2 câu KHÁC CHỮ nhưng CÙNG NGHĨA vẫn là một vấn đề — chạy hoàn toàn trên máy, không cần internet.");
})();

// ===================================================== SLIDE 5 — CHROMA: EVIDENCE
(() => {
  const s = pres.addSlide(); s.background = { color: BG };
  titleBar(s, "ChromaDB · Bằng chứng", "Demo thật: 4 cảnh báo vào → 2 sự cố duy nhất", TEAL);
  const rows = [
    ["Payment declined #10293 — fraud", "🆕 SỰ CỐ MỚI", "lần 1", AMBER],
    ["Payment declined #55019 — fraud suspected", "♻️ ĐÃ GẶP (giống 94%)", "lần 2", GREEN],
    ["ERROR: disk full 98% on db-02", "🆕 SỰ CỐ MỚI", "lần 1", AMBER],
    ["Payment declined #77123 — chargeback", "♻️ ĐÃ GẶP (giống 96%)", "lần 3", GREEN],
  ];
  const y0 = 1.95;
  s.addText("Cảnh báo đưa vào", { x: 0.75, y: y0, w: 6.4, h: 0.35, fontFace: BODY, fontSize: 12, bold: true, color: MUTED, margin: 0 });
  s.addText("ChromaDB kết luận", { x: 7.3, y: y0, w: 5.3, h: 0.35, fontFace: BODY, fontSize: 12, bold: true, color: MUTED, margin: 0 });
  rows.forEach(([inp, res, cnt, col], i) => {
    const y = 2.35 + i * 0.92;
    card(s, 0.6, y, 6.5, 0.78, "FFFFFF");
    s.addText(inp, { x: 0.8, y, w: 6.2, h: 0.78, fontFace: MONO, fontSize: 12.5, color: INK, valign: "middle", margin: 0 });
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 7.3, y, w: 5.45, h: 0.78, rectRadius: 0.08,
      fill: { color: col === GREEN ? "E7F5EC" : "FFF3D6" }, line: { color: col, width: 1.2 } });
    s.addText([{ text: res + "   ", options: { bold: true, color: col } },
               { text: "· xuất hiện " + cnt, options: { color: MUTED } }],
      { x: 7.5, y, w: 5.1, h: 0.78, fontFace: BODY, fontSize: 13, valign: "middle", margin: 0 });
  });
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 0.6, y: 6.15, w: 12.15, h: 0.8, rectRadius: 0.08, fill: { color: INK } });
  s.addText([{ text: "Kết quả:  ", options: { bold: true, color: "FFD764" } },
             { text: "4 cảnh báo → chỉ 2 sự cố thật sự khác nhau. Người trực không bị spam 4 lần cho cùng 1 vấn đề. ", options: { color: "FFFFFF" } },
             { text: " (7/7 test tự động PASS)", options: { color: ICE, italic: true } }],
    { x: 0.85, y: 6.15, w: 11.7, h: 0.8, fontFace: BODY, fontSize: 13.5, valign: "middle", margin: 0 });
})();

// ===================================================== SLIDE 6 — TTS: WHY + HOW
(() => {
  const s = pres.addSlide(); s.background = { color: BG };
  titleBar(s, "HuggingFace TTS · Cách hoạt động", "Biến chữ cảnh báo thành giọng nói tiếng Việt", PURPLE);
  const y = 2.0, bw = 2.75, bh = 2.3, gap = 0.32;
  let x = 0.6;
  const steps = [
    ["📝", "Chữ cảnh báo", "\"Cảnh báo nghiêm trọng. Hệ thống phát hiện gian lận…\"", INK],
    ["🤖", "Model AI giọng nói", "facebook/mms-tts-vie tải 1 lần, chạy trên máy (CPU)", PURPLE],
    ["〰️", "Sóng âm thanh", "AI tạo ra file âm thanh (WAV) đọc đúng câu tiếng Việt", PURPLE],
    ["🔊", "Loa đọc to", "Phát ra loa — nghe được ngay cả khi không nhìn màn hình", GREEN],
  ];
  steps.forEach(([ic, t, d, c], i) => {
    stepBox(s, x, y, bw, bh, ic, t, d, c);
    if (i < 3) arrow(s, x + bw + 0.03, y + bh / 2, gap - 0.06, PURPLE);
    x += bw + gap;
  });
  analogy(s, 0.6, 4.75, 12.15, 1.0, "F5F1FA", PURPLE,
    "Giống một chiếc loa phát thanh tự động đọc thông báo — nhưng đây là AI đọc, phát âm tiếng Việt tự nhiên, và không cần internet sau khi cài.");
  // key facts strip
  const facts = [["Offline", "sau lần tải đầu"], ["CPU", "không cần GPU"], ["Tiếng Việt", "phát âm tự nhiên"], ["Tự fallback", "lỗi → chuyển beep"]];
  facts.forEach(([a, b], i) => {
    const fx = 0.6 + i * 3.05;
    card(s, fx, 5.95, 2.9, 0.95, "FFFFFF");
    s.addText(a, { x: fx, y: 6.05, w: 2.9, h: 0.45, fontFace: HEAD, fontSize: 17, bold: true, color: PURPLE, align: "center", margin: 0 });
    s.addText(b, { x: fx, y: 6.5, w: 2.9, h: 0.35, fontFace: BODY, fontSize: 12, color: MUTED, align: "center", margin: 0 });
  });
})();

// ===================================================== SLIDE 7 — TTS: EVIDENCE
(() => {
  const s = pres.addSlide(); s.background = { color: BG };
  titleBar(s, "HuggingFace TTS · Bằng chứng", "Đã tạo ra giọng nói tiếng Việt thật", PURPLE);
  card(s, 0.6, 1.8, 12.15, 2.5, "0E1420");
  s.addText("Sóng âm của câu cảnh báo do AI đọc (file WAV thật)", { x: 0.85, y: 1.95, w: 11, h: 0.35, fontFace: BODY, fontSize: 12, color: "9fb0c9", margin: 0 });
  img(s, "tts_waveform.png", 0.85, 2.35, 11.65, 1.85);
  // metadata cards
  const meta = [
    ["Câu đọc", "\"Cảnh báo nghiêm trọng. Hệ thống thanh toán phát hiện giao dịch gian lận. Vui lòng kiểm tra ngay.\""],
    ["Model", "facebook/mms-tts-vie  (Hugging Face, VITS/MMS-TTS)"],
    ["Thông số", "5.86 giây · 16.000 Hz · mono · dựng trên CPU (không GPU)"],
    ["An toàn", "Offline sau lần tải đầu · thiếu thư viện/lỗi → tự động beep, không chặn cảnh báo"],
  ];
  meta.forEach(([k, v], i) => {
    const y = 4.5 + i * 0.62;
    s.addText(k, { x: 0.75, y, w: 1.9, h: 0.55, fontFace: BODY, fontSize: 13, bold: true, color: PURPLE, valign: "top", margin: 0 });
    s.addText(v, { x: 2.75, y, w: 9.9, h: 0.6, fontFace: BODY, fontSize: 12.5, color: INK, valign: "top", margin: 0 });
  });
  s.addText("File: workshop/evidence/tts_alert_vi.wav  ·  tts_mms_vie_sample.wav  ·  7/7 test tự động PASS",
    { x: 0.75, y: 6.95, w: 12, h: 0.3, fontFace: MONO, fontSize: 10.5, italic: true, color: MUTED, margin: 0 });
})();

// ===================================================== SLIDE 8 — AN TOÀN / TÓM TẮT
(() => {
  const s = pres.addSlide(); s.background = { color: INK };
  s.addShape(pres.shapes.OVAL, { x: 10.6, y: -1.6, w: 5, h: 5, fill: { color: "20304C" } });
  s.addText("TÓM LẠI", { x: 0.85, y: 0.75, w: 10, h: 0.4, fontFace: BODY, fontSize: 13, color: INKSOFT, bold: true, charSpacing: 3, margin: 0 });
  s.addText("Hai trợ lý — mạnh nhưng an toàn", { x: 0.8, y: 1.1, w: 11.5, h: 0.7, fontFace: HEAD, fontSize: 30, bold: true, color: "FFFFFF", margin: 0 });
  const pts = [
    ["🧠", "ChromaDB", "Nhận ra sự cố lặp lại → bớt spam, người trực thấy đúng số vấn đề thật.", TEAL],
    ["🔊", "HuggingFace TTS", "Đọc cảnh báo thành giọng nói tiếng Việt → nghe được, khó bỏ lỡ.", PURPLE],
    ["🔌", "Tùy chọn", "Cả hai là \"lắp thêm\" (requirements-ml.txt). Không cài vẫn chạy: tự dùng bộ nhớ SQLite / beep.", AMBER],
    ["🔒", "Offline & không GPU", "Chạy ngay trên máy, không gửi dữ liệu ra ngoài, không cần card đồ họa.", GREEN],
    ["✅", "Có kiểm thử", "16 test tự động cho 2 tính năng · toàn dự án 119 test PASS.", ICE],
  ];
  pts.forEach(([ic, t, d, c], i) => {
    const y = 2.05 + i * 0.98;
    s.addShape(pres.shapes.OVAL, { x: 0.85, y, w: 0.62, h: 0.62, fill: { color: "20304C" }, line: { color: c, width: 1.3 } });
    s.addText(ic, { x: 0.85, y, w: 0.62, h: 0.62, fontSize: 20, align: "center", valign: "middle", margin: 0 });
    s.addText([{ text: t + ":  ", options: { bold: true, color: c } }, { text: d, options: { color: "E7ECF5" } }],
      { x: 1.7, y: y - 0.02, w: 10.9, h: 0.66, fontFace: BODY, fontSize: 15, valign: "middle", margin: 0 });
  });
})();

pres.writeFile({ fileName: "D:/AI/screen-watcher-pro/workshop/PRD2.2_ChromaDB_HFTTS_Explainer.pptx" })
  .then(f => console.log("WROTE", f));
