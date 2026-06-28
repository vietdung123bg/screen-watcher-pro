"""Send alert emails via SMTP (with screenshot attachment).

Supports provider presets (Gmail / Outlook / Office 365) so the YAML only needs
`provider` + `username` + `password_env`. A "Send test email" path forces a real
send regardless of the DRY-RUN flag so SMTP can be verified.
"""

from __future__ import annotations

import logging
import os
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path

logger = logging.getLogger("screen_watcher.email")

# Built-in SMTP presets. Explicit smtp_host/smtp_port in YAML override these.
PROVIDER_PRESETS: dict[str, dict] = {
    "gmail": {"smtp_host": "smtp.gmail.com", "smtp_port": 587, "use_tls": True},
    "outlook": {"smtp_host": "smtp.office365.com", "smtp_port": 587, "use_tls": True},
    "office365": {"smtp_host": "smtp.office365.com", "smtp_port": 587, "use_tls": True},
    "outlook-personal": {"smtp_host": "smtp-mail.outlook.com", "smtp_port": 587, "use_tls": True},
}


@dataclass
class EmailSendResult:
    sent: bool
    simulated: bool          # True if DRY-RUN (not actually sent)
    detail: str              # human-readable explanation


class EmailService:
    def __init__(self, email_cfg: dict):
        self.cfg = dict(email_cfg or {})
        provider = str(self.cfg.get("provider", "")).lower().strip()
        preset = PROVIDER_PRESETS.get(provider, {})
        for key, val in preset.items():
            self.cfg.setdefault(key, val)  # explicit values win over preset

    @property
    def enabled(self) -> bool:
        return bool(self.cfg.get("enabled", False))

    def _password(self) -> str | None:
        env_name = self.cfg.get("password_env", "")
        return os.environ.get(env_name) if env_name else None

    # ---------- public ----------
    def send_alert(self, recipients: list[str], subject: str, body: str,
                   attachment: Path | None = None) -> EmailSendResult:
        """Send an alert. If disabled (DRY-RUN) returns a simulated result."""
        if not recipients:
            return EmailSendResult(False, False, "No owner address to send to.")
        if not self.enabled:
            return EmailSendResult(
                False, True,
                f"DRY-RUN (email.enabled=false): simulated send to {recipients}, "
                f"nothing actually sent. Set enabled=true in rules.yaml to send for real.",
            )
        return self._smtp_send(recipients, subject, body, attachment)

    def send_test(self, to: str | None = None) -> EmailSendResult:
        """Force a REAL send (ignores DRY-RUN) to verify SMTP configuration."""
        recipient = to or self.cfg.get("from") or self.cfg.get("username")
        if not recipient:
            return EmailSendResult(False, False,
                                   "No recipient — set `from`/`username` in rules.yaml.")
        subject = "[Screen Watcher] SMTP test email"
        body = ("This is a test email from Screen Watcher Pro.\n"
                "If you received it, your SMTP settings are working.\n")
        return self._smtp_send([recipient], subject, body, None)

    # ---------- internal ----------
    def _smtp_send(self, recipients: list[str], subject: str, body: str,
                   attachment: Path | None) -> EmailSendResult:
        host = self.cfg.get("smtp_host")
        port = int(self.cfg.get("smtp_port", 587))
        username = self.cfg.get("username")
        password = self._password()
        sender = self.cfg.get("from", username)
        use_tls = bool(self.cfg.get("use_tls", True))

        if not host or not username:
            return EmailSendResult(False, False,
                                   "Missing smtp_host/username in email config "
                                   "(set `provider` or explicit smtp_host).")
        if not password:
            return EmailSendResult(
                False, False,
                f"Missing SMTP password — environment variable "
                f"'{self.cfg.get('password_env')}' is not set.",
            )

        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = sender
        msg["To"] = ", ".join(recipients)
        msg.set_content(body)

        if attachment and Path(attachment).exists():
            data = Path(attachment).read_bytes()
            msg.add_attachment(data, maintype="image", subtype="png",
                               filename=Path(attachment).name)

        try:
            with smtplib.SMTP(host, port, timeout=20) as server:
                if use_tls:
                    server.starttls()
                server.login(username, password)
                server.send_message(msg)
            logger.info("Email sent to %s via %s:%s", recipients, host, port)
            return EmailSendResult(True, False,
                                   f"Email sent to {recipients} via {host}:{port}.")
        except Exception as e:
            logger.error("Email send failed: %s", e)
            return EmailSendResult(False, False, f"SMTP error: {e}")
