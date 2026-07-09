"""Console SOS watcher (PRD 2.2 — Phase 1 MVP, console-alarm variant).

A daemon thread that polls `sos_alerts` every few seconds and ALARMS in the
terminal for every PENDING alert that is due: a bold red banner plus an audible
beep (winsound on Windows, the ASCII bell elsewhere). Because the alarm runs in
the server/desktop PROCESS — not in the browser — it keeps ringing even when
no admin UI is open. It re-alarms every `cooldown_seconds` until the alert is
acknowledged (via /admin/sos, the API, or the chatbot).

Config lives in config/rules.yaml under `sos_alert:`; the repo contract is
SosAlertRepository.list_pending_for_beep() / mark_beeped().
"""

from __future__ import annotations

import logging
import sys
import threading
import time

try:
    import winsound
    HAS_WINSOUND = True
except ImportError:                      # non-Windows: fall back to the ASCII bell
    HAS_WINSOUND = False

try:
    from rich.console import Console
    console = Console()
except ImportError:
    console = None

logger = logging.getLogger("screen_watcher.sos_job")


class SosWatcherJob(threading.Thread):
    """Poll sos_alerts and alarm on the console until each alert is acknowledged."""

    daemon = True

    def __init__(self, sos_repo, config: dict | None = None):
        super().__init__(name="SosWatcherJob")
        config = config or {}
        self.repo = sos_repo
        self.poll_interval = float(config.get("poll_interval_seconds", 3))
        self.cooldown = int(config.get("cooldown_seconds", 300))
        self.beep_freq = int(config.get("beep_frequency_hz", 1000))
        self.beep_dur = int(config.get("beep_duration_ms", 500))
        self.beep_repeat = int(config.get("beep_repeat", 3))
        self.enabled = bool(config.get("enabled", True))
        self.sound_enabled = bool(config.get("sound_enabled", True))
        self._stop = threading.Event()

    def run(self) -> None:
        if not self.enabled:
            logger.info("SOS watcher job disabled (sos_alert.enabled=false).")
            return
        logger.info("SOS watcher job started (poll=%ss, re-alarm cooldown=%ss).",
                    self.poll_interval, self.cooldown)
        while not self._stop.is_set():
            try:
                for alert in self.repo.list_pending_for_beep(self.cooldown):
                    self._alarm(alert)
                    self.repo.mark_beeped(alert["id"])
            except Exception as e:  # the alarm loop must never die
                if console:
                    console.log(f"[red]SOS job error: {e}")
                logger.exception("SOS watcher job error: %s", e)
            self._stop.wait(self.poll_interval)
        logger.info("SOS watcher job stopped.")

    def _alarm(self, alert) -> None:
        msg = (f"🚨🚨🚨 [SOS] {alert['severity']} — {alert['message']} "
               f"@ {alert['created_at']} 🚨🚨🚨")
        if console:
            console.print(msg, style="bold red on yellow")
        else:
            print(f"\n{msg}\n", file=sys.stderr, flush=True)
        logger.warning("SOS ALARM: alert=%s severity=%s", alert["id"], alert["severity"])
        if self.sound_enabled:
            self._beep()

    def _beep(self) -> None:
        for _ in range(self.beep_repeat):
            try:
                if HAS_WINSOUND:
                    winsound.Beep(self.beep_freq, self.beep_dur)
                else:
                    print("\a", end="", flush=True)
                time.sleep(0.1)
            except Exception:
                print("\a", end="", flush=True)

    def stop(self, timeout: float | None = 5.0) -> None:
        """Graceful shutdown: signal the loop and wait for it to exit."""
        self._stop.set()
        if self.is_alive():
            self.join(timeout=timeout)
