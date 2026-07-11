"""Automated end-to-end evidence capture for PRD 2.2 (+ ChromaDB / HF TTS).

Runs the full test suite, spins up an isolated demo server, drives the
Incident->SOS->Acknowledge and AI-Review->Approve/Reject flows through the
REST API, screenshots every /admin page, captures the console SOS banner, and
(if the ML extras are installed) demos ChromaDB dedup + a real Hugging Face
TTS synthesis. Everything lands in workshop/<DDMMYY>/evidence/ (today by
default) so it can be dropped straight into README/RUNBOOK/slides.

Usage:
    python workshop/capture_evidence.py [folder_name]   # default: today, DDMMYY

Invoked by `run.cmd evidence`.
"""

from __future__ import annotations

import io
import json
import shutil
import socket
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace as NS

ROOT = Path(__file__).resolve().parent.parent
WORKSHOP = ROOT / "workshop"
PY = sys.executable

# `python workshop/capture_evidence.py` puts this script's own directory on
# sys.path[0], not ROOT — unlike the `-m pytest` / `-m uvicorn` subprocesses
# below (which get cwd=ROOT on their path automatically). chroma_demo() and
# tts_demo() run in-process and need `import app...` to resolve, so add it.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def log(msg: str) -> None:
    print(f"[evidence] {msg}", flush=True)


def jdump(obj, path: Path) -> None:
    with io.open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)


def _read_text_retrying(path: Path, attempts: int = 15, delay: float = 0.3) -> str:
    """Windows can keep a terminated child's duplicated file handle open for a
    beat after Popen.wait() returns; retry briefly instead of failing hard."""
    for i in range(attempts):
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except PermissionError:
            if i == attempts - 1:
                return ""
            time.sleep(delay)
    return ""


def _unlink_retrying(path: Path, attempts: int = 15, delay: float = 0.3) -> None:
    for i in range(attempts):
        try:
            path.unlink(missing_ok=True)
            return
        except PermissionError:
            if i == attempts - 1:
                return
            time.sleep(delay)


def free_port(default: int = 8010) -> int:
    for port in (default, 8011, 8012, 8013, 8020):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    return default


# ---------------------------------------------------------------- pytest ----
def run_pytest(evidence: Path, basetemp: Path) -> None:
    """Run the suite with an explicit --basetemp: pytest's default temp dir
    accumulates old runs and prunes them on exit, which throws PermissionError
    on Windows the moment any file from a prior run is still locked (e.g. by
    antivirus or a lingering handle). A fresh, self-owned basetemp avoids that
    entirely — see the several PermissionError incidents earlier in this repo's
    history for why this is not optional."""
    import os
    bt = f"--basetemp={basetemp}"

    log("Running full pytest suite...")
    r = subprocess.run([PY, "-m", "pytest", "tests/", "-v", "--no-header", bt],
                       cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=300)
    lines = [ln for ln in (r.stdout + r.stderr).splitlines()
            if any(k in ln for k in ("PASSED", "FAILED", "SKIPPED", "passed", "failed"))]
    (evidence / "00_pytest_full.txt").write_text("\n".join(lines), encoding="utf-8")
    log(f"  -> {lines[-1] if lines else '(no summary — check for a pytest error above)'}")

    log("Running real HF-TTS synthesis test (SW_TTS_REAL=1)...")
    env = {**os.environ, "SW_TTS_REAL": "1"}
    r = subprocess.run([PY, "-m", "pytest", "tests/test_voice_alert_hf.py", "-v", "--no-header", bt],
                       cwd=ROOT, capture_output=True, text=True, encoding="utf-8", env=env, timeout=300)
    lines = [ln for ln in (r.stdout + r.stderr).splitlines()
            if any(k in ln for k in ("PASSED", "FAILED", "SKIPPED", "passed", "failed"))]
    (evidence / "01_pytest_tts_real.txt").write_text("\n".join(lines), encoding="utf-8")
    log(f"  -> {lines[-1] if lines else '(no summary)'}")

    for name, files in [
        ("02_pytest_prd22.txt", ["tests/test_migration_prd22.py", "tests/test_sos_watcher_job.py",
                                 "tests/test_event_service.py", "tests/test_ai_review_governance.py",
                                 "tests/test_prd22_routes.py"]),
        ("03_pytest_chroma.txt", ["tests/test_chroma_issue_store.py"]),
    ]:
        r = subprocess.run([PY, "-m", "pytest", *files, "-v", "--no-header", bt],
                           cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=300)
        lines = [ln for ln in (r.stdout + r.stderr).splitlines()
                if any(k in ln for k in ("PASSED", "FAILED", "passed", "failed"))]
        (evidence / name).write_text("\n".join(lines), encoding="utf-8")
        log(f"  -> {name}: {lines[-1] if lines else '(no summary)'}")


# ------------------------------------------------------------- demo server --
def write_demo_server(folder: str) -> Path:
    path = WORKSHOP / f"_demo_server_{folder}.py"
    path.write_text(f'''"""Auto-generated by capture_evidence.py — isolated demo server for {folder}."""
from __future__ import annotations
import pathlib
from app import config
_demo = pathlib.Path(__file__).resolve().parent / "{folder}" / "demo_data"
_demo.mkdir(parents=True, exist_ok=True)
config.DATA_DIR = _demo
config.SCREENSHOT_DIR = _demo / "screenshots"
config.OCR_DIR = _demo / "ocr_results"
config.DB_PATH = _demo / "demo.db"
from app.ai.chat_server import create_app  # noqa: E402
_cfg = config.load_app_config()
_cfg.setdefault("prd22", {{}}).setdefault("ai_review", {{}})["mock"] = True
app = create_app(_cfg)
''', encoding="utf-8")
    return path


def wait_for_health(port: int, timeout: float = 20.0) -> bool:
    import urllib.request
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1) as r:
                if r.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def _session_with_timeout(seconds: float = 20.0):
    """A requests.Session where every call defaults to a timeout, so a slow/
    contended demo server fails loudly instead of hanging the whole capture
    run forever (seen once under heavy machine load from unrelated processes)."""
    import requests

    class _TimeoutSession(requests.Session):
        def request(self, *a, **kw):
            kw.setdefault("timeout", seconds)
            return super().request(*a, **kw)

    return _TimeoutSession()


def seed_and_capture(port: int, evidence: Path) -> None:
    requests = _session_with_timeout()
    B = f"http://127.0.0.1:{port}"
    log("Logging in as admin...")
    H = {"Authorization": "Bearer " + requests.post(
        f"{B}/api/auth/login", json={"username": "admin", "password": "admin123"}).json()["access_token"]}
    for u, role in [("oscar", "operator"), ("vera", "viewer")]:
        requests.post(f"{B}/api/admin/users", headers=H,
                      json={"username": u, "password": "secret123", "role": role})
    OH = {"Authorization": "Bearer " + requests.post(
        f"{B}/api/auth/login", json={"username": "oscar", "password": "secret123"}).json()["access_token"]}
    VH = {"Authorization": "Bearer " + requests.post(
        f"{B}/api/auth/login", json={"username": "vera", "password": "secret123"}).json()["access_token"]}

    log("Creating user-approved INCIDENT rule...")
    requests.post(f"{B}/api/rules", headers=H, json={
        "rule_id": "payment_declined_incident", "name": "Payment declined / fraud (INCIDENT)",
        "rule_type": "any_keywords",
        "condition": {"keywords": ["declined", "fraud", "chargeback"], "ignore_case": True},
        "status": "ACTIVE", "enabled": True, "is_incident_rule": True,
        "severity": "critical", "owner_group": "finance_team"})

    log("Triggering incident event -> expect SOS...")
    inc = requests.post(f"{B}/api/events", headers=H, json={
        "raw_text": "ALERT: Payment declined for order #10293 - possible fraud on card ****4417",
        "screen": "Payment monitoring"}).json()
    log(f"  -> {inc['evaluation']['status']}, sos_created={inc['evaluation']['sos_created']}")

    log("Triggering unmatched events -> AI review drafts...")
    for txt, scr in [
        ("Unhandled exception: inventory sync FAILED at step 7 (worker-3)", "Sentry"),
        ("Database backup TIMEOUT after 1800s on node db-02", "DB backup dashboard"),
        ("Kafka consumer lag CRITICAL: 240k messages, broker unavailable", "Grafana")]:
        requests.post(f"{B}/api/events", headers=H, json={"raw_text": txt, "screen": scr})
    requests.post(f"{B}/api/events", headers=H,
                 json={"raw_text": "All systems operational. 0 open incidents.", "screen": "Ops dashboard"})
    time.sleep(3)
    q = requests.get(f"{B}/api/ai/reviews/queue", headers=H).json()["reviews"]
    jdump({"reviews": q}, evidence / "20_review_queue.json")
    log(f"  -> review queue: {len(q)}")

    out = {}
    out["viewer_create_rule_status"] = requests.post(f"{B}/api/rules", headers=VH, json={
        "rule_id": "x", "name": "x", "rule_type": "contains", "condition": {"value": "a"}}).status_code
    out["operator_create_rule_status"] = requests.post(f"{B}/api/rules", headers=OH, json={
        "rule_id": "x", "name": "x", "rule_type": "contains", "condition": {"value": "a"}}).status_code
    out["viewer_audit_status"] = requests.get(f"{B}/api/audit", headers=VH).status_code

    high = [r for r in q if r["suggested_rule_id"]][0]
    out["approve"] = requests.post(f"{B}/api/ai/reviews/{high['id']}/approve", headers=H,
                                   json={"review_note": "valid infra signal"}).json()

    requests.post(f"{B}/api/events", headers=H,
                 json={"raw_text": "User login denied: too many attempts from 10.0.0.9", "screen": "Auth service"})
    time.sleep(2)
    q2 = requests.get(f"{B}/api/ai/reviews/queue", headers=H).json()["reviews"]
    draft = [r for r in q2 if r["suggested_rule_id"]][0]
    out["reject_missing_reason_status"] = requests.post(
        f"{B}/api/ai/reviews/{draft['id']}/reject", headers=H, json={}).status_code
    out["reject"] = requests.post(f"{B}/api/ai/reviews/{draft['id']}/reject", headers=H,
                                  json={"reject_reason": "false positive - expected lockout"}).json()

    sos = requests.get(f"{B}/api/sos/alerts?status=PENDING", headers=H).json()["alerts"][0]
    out["sos_ack"] = requests.post(f"{B}/api/sos/alerts/{sos['id']}/acknowledge", headers=H).json()
    out["sos_ack_double_status"] = requests.post(
        f"{B}/api/sos/alerts/{sos['id']}/acknowledge", headers=H).status_code
    jdump(out, evidence / "40_flow_responses.json")
    jdump(requests.get(f"{B}/api/rules", headers=H).json(), evidence / "41_rules_after.json")
    jdump(requests.get(f"{B}/api/audit?limit=40", headers=H).json(), evidence / "42_audit_after.json")
    log(f"  -> approve rule_status={out['approve']['rule_status']}, "
       f"reject rule_status={out['reject']['rule_status']}, "
       f"sos ack by={out['sos_ack']['acknowledged_by']}")

    # fresh PENDING SOS + draft so screenshots show live data
    log("Seeding a fresh SOS + draft for screenshots...")
    requests.post(f"{B}/api/events", headers=H, json={
        "raw_text": "CRITICAL: Payment declined - chargeback fraud spike on gateway A",
        "screen": "Payment monitoring"})
    requests.post(f"{B}/api/events", headers=H, json={
        "raw_text": "Unhandled EXCEPTION in checkout worker: NullPointer at line 88, retry loop",
        "screen": "Sentry"})
    time.sleep(3)


def capture_screenshots(port: int, evidence: Path) -> None:
    from playwright.sync_api import sync_playwright
    B = f"http://127.0.0.1:{port}"
    log("Capturing /admin screenshots (Playwright)...")

    def shot(page, name):
        page.wait_for_timeout(400)
        h = page.evaluate(
            "(() => { const m = document.querySelector('main');"
            " return Math.min(Math.ceil(m ? m.getBoundingClientRect().bottom + 20 : 760), 900); })()")
        page.screenshot(path=str(evidence / name), clip={"x": 0, "y": 0, "width": 1280, "height": h})

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 1900})
        page.goto(f"{B}/admin/login"); page.wait_for_load_state("networkidle")
        page.fill("input[name=username]", "admin"); page.fill("input[name=password]", "admin123")
        page.click("button[type=submit]"); page.wait_for_load_state("networkidle")
        for url, name in [("/admin/review-queue", "s02_review_queue.png"),
                          ("/admin/sos", "s03_sos_pending.png"),
                          ("/admin/rules", "s08_rules_after.png"),
                          ("/admin/events", "s05_events.png"),
                          ("/admin/rules/new", "s06_rule_new.png")]:
            page.goto(B + url); page.wait_for_load_state("networkidle"); shot(page, name)
        page.goto(f"{B}/admin/audit"); page.wait_for_load_state("networkidle"); page.wait_for_timeout(400)
        page.screenshot(path=str(evidence / "s09_audit_after.png"),
                        clip={"x": 0, "y": 0, "width": 1280, "height": 758})

        lp = browser.new_page(viewport={"width": 1100, "height": 620})
        lp.goto(f"{B}/admin/login"); lp.wait_for_load_state("networkidle"); lp.wait_for_timeout(300)
        lp.screenshot(path=str(evidence / "s01_login.png"))
        browser.close()
    log("  -> screenshots saved")


# ------------------------------------------------------------- chroma / tts -
def chroma_demo(evidence: Path) -> None:
    try:
        import chromadb  # noqa: F401
    except ImportError:
        log("chromadb not installed — skipping ChromaDB demo (pip install -r requirements-ml.txt)")
        return
    import tempfile
    from app import config
    from app.db.database import Database
    from app.db.repository import Repository
    from app.services.issue_vectorstore import IssueVectorStore

    log("Running ChromaDB dedup demo...")
    tmp = Path(tempfile.mkdtemp())
    config.DATA_DIR = tmp; config.DB_PATH = tmp / "d.db"
    db = Database(config.DB_PATH); db.init_schema(); repo = Repository(db)
    admin = repo.get_user_by_username("admin")["id"]; sess = repo.create_session(admin, "chrome")
    store = IssueVectorStore(repo, {"issues": {"enabled": True, "backend": "chroma",
                                               "similarity_threshold": 0.78, "vector_dimensions": 256,
                                               "chroma_path": str(tmp / "chroma")}})

    def rule(rid, name, reason, terms):
        return NS(matched=True, rule_id=rid, rule_name=name, rule_type="any_keywords",
                  severity="high", owner_group="ops", reason=reason, matched_terms=terms, metadata={})

    def classify(txt, r):
        sid = repo.create_screenshot(sess, admin, "chrome", "Screen", None, 1, 1, "success")
        return store.classify_event(screenshot_id=sid, target_label="Chrome",
                                    window_title="Screen", ocr_text=txt, rule_eval=r)

    pay = rule("payment", "Payment declined", "declined", ["declined"])
    scenarios = [
        ("Payment declined for order #10293 - fraud on card 4417", pay, "Lan dau thay loi thanh toan"),
        ("Payment declined for order #55019 - fraud suspected", pay, "Loi thanh toan TUONG TU lan truoc"),
        ("ERROR: disk full 98% on node db-02, service degraded",
         rule("disk", "Disk full", "ERROR disk", ["ERROR"]), "Loi ha tang KHAC HAN"),
        ("Payment declined for order #77123 - chargeback fraud", pay, "Lai la loi thanh toan"),
        ("Kafka broker CRITICAL unavailable, consumer lag spike",
         rule("kafka", "Kafka lag", "CRITICAL unavailable", ["CRITICAL", "unavailable"]),
         "Loi ha tang MOI (Kafka)"),
    ]
    lines = ["=== DEMO ChromaDB - nhan biet su co 'MOI' vs 'DA TUNG GAP' ===",
            "(nguong giong nhau >= 78% thi coi la cung mot van de)\n"]
    for txt, r, desc in scenarios:
        res = classify(txt, r)
        tag = (f"[MOI]     su co lan dau" if res.status == "new_issue"
              else f"[DA GAP]  giong {round(res.similarity * 100)}% mot su co truoc")
        lines += [f"- {desc}", f"    input : {txt[:52]}",
                 f"    ket qua: {tag}  (xuat hien lan thu {res.occurrence_count})\n"]
    unique = store._delegate._col.count()
    lines.append(f"=> {len(scenarios)} canh bao dua vao, ChromaDB gom con {unique} su co DUY NHAT.")
    lines.append("   Nghia la doi truc/nguoi van hanh khong bi spam nhieu lan cho cung 1 van de.")
    (evidence / "52_chroma_demo.txt").write_text("\n".join(lines), encoding="utf-8")
    log(f"  -> {len(scenarios)} alerts -> {unique} unique issues")


def tts_demo(evidence: Path) -> None:
    try:
        import torch  # noqa: F401
        import transformers  # noqa: F401
    except ImportError:
        log("torch/transformers not installed — skipping HF TTS demo (pip install -r requirements-ml.txt)")
        return
    import numpy as np
    import torch
    from PIL import Image, ImageDraw
    from transformers import AutoTokenizer, VitsModel
    from app.services.voice_alert_service import VoiceAlertService

    log("Running HF TTS synthesis demo (facebook/mms-tts-vie, CPU)...")
    svc = VoiceAlertService({"tts": {"enabled": True, "provider": "transformers",
                                     "hf_model_id": "facebook/mms-tts-vie"}})
    t0 = time.time()
    model = VitsModel.from_pretrained(svc.hf_model_id)
    tok = AutoTokenizer.from_pretrained(svc.hf_model_id)
    model.to("cpu").eval()
    load_t = time.time() - t0

    phrase = "Cảnh báo. Sự cố nghiêm trọng vừa được xác nhận. Vui lòng kiểm tra hệ thống ngay lập tức."
    t1 = time.time()
    inputs = tok(phrase, return_tensors="pt")
    with torch.no_grad():
        waveform = model(**inputs).waveform
    audio = waveform.squeeze().cpu().numpy().astype("float32")
    sr = int(model.config.sampling_rate)
    synth_t = time.time() - t1

    wav_path = evidence / "tts_alert_vi.wav"
    tmp_path = svc._write_wav(audio, sr)
    shutil.copy(tmp_path, wav_path)

    W, H = 1100, 240
    img = Image.new("RGB", (W, H), "#0E1420"); d = ImageDraw.Draw(img)
    step = max(1, len(audio) // W); mid = H // 2
    for x, i in enumerate(range(0, len(audio), step)):
        chunk = audio[i:i + step]
        amp = float(np.max(np.abs(chunk))) if len(chunk) else 0.0
        h = int(amp * (H * 0.46))
        d.line([(x, mid - h), (x, mid + h)], fill="#7fd39a", width=1)
        if x >= W - 1:
            break
    d.line([(0, mid), (W, mid)], fill="#31405c", width=1)
    img.save(str(evidence / "tts_waveform.png"))

    dur = len(audio) / sr
    meta = [
        "=== HuggingFace TTS - bang chung synth THAT (offline / CPU) ===",
        f"Model      : {svc.hf_model_id}  (VITS / MMS-TTS, tieng Viet)",
        "Thiet bi   : CPU (khong dung GPU)",
        f"Sample rate: {sr} Hz, mono 16-bit PCM",
        f'Cau doc    : "{phrase}"',
        f"Do dai     : {dur:.2f} giay  ({len(audio)} mau)",
        f"File WAV   : {wav_path.relative_to(ROOT)}",
        "Waveform   : tts_waveform.png",
        "",
        f"Thoi gian load model: {load_t:.1f}s  |  synth cau tren: {synth_t:.1f}s",
        "Offline: sau lan tai model dau tien (cache ~/.cache/huggingface) khong can mang.",
        "Fallback: neu thieu thu vien/loi -> tu dong chuyen sang beep, khong chan luong rule.",
    ]
    (evidence / "53_tts_demo.txt").write_text("\n".join(meta), encoding="utf-8")
    log(f"  -> synth {dur:.2f}s @ {sr}Hz (load={load_t:.1f}s, synth={synth_t:.1f}s)")


# ------------------------------------------------------- server flow (retry) -
def run_server_flow(folder: str, evidence: Path) -> None:
    """Start the demo server, seed the scenario, screenshot the admin UI, and
    capture the console SOS banner.

    The server's stdout/stderr is redirected to a FILE, not subprocess.PIPE.
    A PIPE has a small OS buffer (64KB on Windows); if nothing actively drains
    it while the child keeps logging (every request logs several lines here),
    the child blocks the instant a write() call fills that buffer — and since
    logging happens synchronously on the same thread handling the request,
    the whole single-worker server stops responding to ANY request, including
    /health. That is what a `proc.communicate()` called only once at the very
    end (after seeding + screenshots) guarantees will eventually happen. A
    file has no such ceiling, so this class of hang cannot occur."""
    port = free_port()
    server_module = write_demo_server(folder)
    module_name = f"workshop.{server_module.stem}"
    server_log = WORKSHOP / folder / "_server.log"
    demo_data = WORKSHOP / folder / "demo_data"
    log(f"Starting demo server on port {port} ({module_name})...")
    try:
        with open(server_log, "w", encoding="utf-8") as logf:
            proc = subprocess.Popen(
                [PY, "-u", "-m", "uvicorn", f"{module_name}:app", "--host", "127.0.0.1",
                 "--port", str(port), "--workers", "1"],
                cwd=ROOT, stdout=logf, stderr=subprocess.STDOUT, text=True, encoding="utf-8")
            try:
                if not wait_for_health(port):
                    raise RuntimeError("Demo server did not become healthy in time.")
                seed_and_capture(port, evidence)
                capture_screenshots(port, evidence)
                time.sleep(1.0)   # let the SOS job's alarm lines land in the log
            finally:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()

        # Windows can hold the child's duplicated file handle open for a beat
        # after the process object reports exited; retry the read briefly.
        out = _read_text_retrying(server_log)
        sos_lines = [ln for ln in out.splitlines()
                    if "sos" in ln.lower() or "SOS" in ln or "🚨" in ln]
        (evidence / "30_console_sos.txt").write_text(
            "=== CONSOLE SOS ALARM (captured from the demo server's stdout) ===\n\n"
            + "\n".join(sos_lines), encoding="utf-8")
        log(f"  -> console SOS evidence: {len(sos_lines)} line(s)")
    finally:
        # ALWAYS runs — including when seed_and_capture()/screenshots raise, or
        # when a delete below hits the same Windows file-lock lag — so a retry
        # never inherits this attempt's half-seeded database (which previously
        # caused duplicate-rule_id/rule-already-exists errors that cascaded
        # into unrelated-looking failures on the next attempt). Each cleanup
        # step is independently guarded so one failing can't block the others.
        _unlink_retrying(server_module)
        _unlink_retrying(server_log)
        if demo_data.exists():
            for _ in range(10):
                try:
                    shutil.rmtree(demo_data)
                    break
                except (PermissionError, OSError):
                    time.sleep(0.3)
            else:
                log(f"  -> WARNING: could not remove {demo_data} (left for manual cleanup)")


# --------------------------------------------------------------------- main -
def main() -> int:
    folder = sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime("%d%m%y")
    evidence = WORKSHOP / folder / "evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    log(f"Evidence folder: {evidence}")

    basetemp = WORKSHOP / folder / "_pytest_tmp"
    if basetemp.exists():
        shutil.rmtree(basetemp, ignore_errors=True)
    basetemp.mkdir(parents=True, exist_ok=True)
    run_pytest(evidence, basetemp)

    attempts = 3
    for attempt in range(1, attempts + 1):
        try:
            run_server_flow(folder, evidence)
            break
        except Exception as e:
            log(f"Server flow attempt {attempt}/{attempts} failed: {type(e).__name__}: {e}")
            if attempt == attempts:
                raise
            log("Retrying with a fresh server...")
            time.sleep(2.0)

    chroma_demo(evidence)
    tts_demo(evidence)

    shutil.rmtree(basetemp, ignore_errors=True)
    log(f"DONE. Evidence saved to: {evidence}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
