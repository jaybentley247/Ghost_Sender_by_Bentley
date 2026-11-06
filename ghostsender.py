#!/usr/bin/env python3
"""
GhostSender - a small, honest SMTP email sender.

Sends email through YOUR OWN authenticated SMTP account to a list of
recipients, with optional per-recipient personalization, HTML bodies,
attachments, rate limiting, and a dry-run mode.

It authenticates normally and uses a truthful From address that matches
the account you log in with. It is meant for mail you are authorized to
send (transactional mail, notifications, a list people opted into).

Usage examples
--------------
  # Dry run: render everything, connect to nothing
  python ghostsender.py --recipients recipients.csv \
      --subject "Hello {name}" --body-file template.txt --dry-run

  # Real send (credentials read from env or .env)
  python ghostsender.py --recipients recipients.csv \
      --subject "Monthly update" --body-file template.html --html

Credentials (never hard-code them) are read from the environment:
  GHOST_SMTP_HOST   e.g. smtp.gmail.com
  GHOST_SMTP_PORT   e.g. 587
  GHOST_SMTP_USER   your full email / login
  GHOST_SMTP_PASS   an app password, not your main password
  GHOST_FROM_NAME   optional display name
A .env file in the working directory is loaded automatically if present.
"""

from __future__ import annotations

import argparse
import csv
import os
import smtplib
import ssl
import sys
import time
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from pathlib import Path


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

def load_dotenv(path: str = ".env") -> None:
    """Minimal .env loader: KEY=VALUE lines, no external dependency."""
    p = Path(path)
    if not p.is_file():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


@dataclass
class SmtpConfig:
    host: str
    port: int
    user: str
    password: str
    from_name: str | None = None

    @classmethod
    def from_env(cls) -> "SmtpConfig":
        try:
            host = os.environ["GHOST_SMTP_HOST"]
            user = os.environ["GHOST_SMTP_USER"]
            password = os.environ["GHOST_SMTP_PASS"]
        except KeyError as e:
            raise SystemExit(
                f"Missing required env var {e}. Set GHOST_SMTP_HOST, "
                "GHOST_SMTP_USER and GHOST_SMTP_PASS (a .env file works too)."
            )
        port = int(os.environ.get("GHOST_SMTP_PORT", "587"))
        from_name = os.environ.get("GHOST_FROM_NAME") or None
        return cls(host=host, port=port, user=user,
                   password=password, from_name=from_name)


# --------------------------------------------------------------------------- #
# Recipients
# --------------------------------------------------------------------------- #

@dataclass
class Recipient:
    email: str
    fields: dict[str, str]


def parse_recipients_text(text: str) -> list[Recipient]:
    """
    Parse pasted addresses separated by commas, semicolons, or whitespace
    (including newlines). Duplicates are dropped, order preserved.
    """
    import re
    if not text or not text.strip():
        raise ValueError("Paste at least one email address.")
    parts = [p.strip() for p in re.split(r"[,;\s]+", text) if p.strip()]
    out: list[Recipient] = []
    seen: set[str] = set()
    bad: list[str] = []
    for addr in parts:
        if "@" not in addr or addr.startswith("@") or addr.endswith("@"):
            bad.append(addr)
            continue
        key = addr.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(Recipient(email=addr, fields={}))
    if bad:
        raise ValueError("These don't look like email addresses:\n  "
                         + ", ".join(bad[:10])
                         + ("  ..." if len(bad) > 10 else ""))
    if not out:
        raise ValueError("No valid email addresses found.")
    return out


def load_recipients_or_raise(path: str) -> list[Recipient]:
    """Like load_recipients, but raises ValueError (GUI-friendly, no SystemExit)."""
    if not path:
        raise ValueError("Choose a recipients file first.")
    try:
        return load_recipients(path)
    except SystemExit as e:
        raise ValueError(str(e))


def load_recipients(path: str) -> list[Recipient]:
    """
    Load recipients from a CSV. An 'email' column is required; any other
    columns become template fields (e.g. {name}).

    A plain .txt file with one address per line is also accepted.
    """
    p = Path(path)
    if not p.is_file():
        raise SystemExit(f"Recipients file not found: {path}")

    out: list[Recipient] = []
    if p.suffix.lower() == ".txt":
        for line in p.read_text(encoding="utf-8").splitlines():
            addr = line.strip()
            if addr and not addr.startswith("#"):
                out.append(Recipient(email=addr, fields={}))
        return out

    with p.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or "email" not in reader.fieldnames:
            raise SystemExit("CSV must have an 'email' column.")
        for row in reader:
            email = (row.get("email") or "").strip()
            if not email:
                continue
            fields = {k: (v or "").strip() for k, v in row.items() if k != "email"}
            out.append(Recipient(email=email, fields=fields))
    return out


# --------------------------------------------------------------------------- #
# Message building
# --------------------------------------------------------------------------- #

def render(template: str, recipient: Recipient) -> str:
    """Fill {placeholders} from recipient fields; unknown ones are left as-is."""
    data = {"email": recipient.email, **recipient.fields}
    try:
        return template.format_map(_Default(data))
    except Exception:
        return template


class _Default(dict):
    def __missing__(self, key):  # leave unknown {tokens} untouched
        return "{" + key + "}"


def build_message(cfg: SmtpConfig, recipient: Recipient, subject: str,
                  body: str, html: bool, attachments: list[str]) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = formataddr((cfg.from_name or "", cfg.user))
    msg["To"] = recipient.email
    msg["Subject"] = render(subject, recipient)
    msg["Message-ID"] = make_msgid()

    rendered = render(body, recipient)
    if html:
        msg.set_content("This message requires an HTML-capable email client.")
        msg.add_alternative(rendered, subtype="html")
    else:
        msg.set_content(rendered)

    for path in attachments:
        fp = Path(path)
        if not fp.is_file():
            raise SystemExit(f"Attachment not found: {path}")
        data = fp.read_bytes()
        msg.add_attachment(data, maintype="application", subtype="octet-stream",
                           filename=fp.name)
    return msg


# --------------------------------------------------------------------------- #
# Sending
# --------------------------------------------------------------------------- #

def connect(cfg: SmtpConfig) -> smtplib.SMTP:
    context = ssl.create_default_context()
    if cfg.port == 465:
        server = smtplib.SMTP_SSL(cfg.host, cfg.port, context=context, timeout=30)
    else:
        server = smtplib.SMTP(cfg.host, cfg.port, timeout=30)
        server.ehlo()
        server.starttls(context=context)
        server.ehlo()
    server.login(cfg.user, cfg.password)
    return server


def run(args: argparse.Namespace) -> int:
    load_dotenv(args.env)
    recipients = load_recipients(args.recipients)
    if not recipients:
        print("No recipients found; nothing to do.")
        return 0

    body = Path(args.body_file).read_text(encoding="utf-8") if args.body_file else args.body
    if body is None:
        raise SystemExit("Provide a body with --body or --body-file.")

    attachments = args.attach or []

    print(f"Recipients: {len(recipients)} | html={args.html} | "
          f"attachments={len(attachments)} | dry_run={args.dry_run}")

    # In dry-run we don't need credentials or a connection.
    cfg = None if args.dry_run else SmtpConfig.from_env()
    server = None
    sent = failed = 0

    try:
        if not args.dry_run:
            cfg = cfg or SmtpConfig.from_env()
            server = connect(cfg)
        else:
            # Build a placeholder config so messages can be rendered/printed.
            cfg = SmtpConfig(host="dry-run", port=0,
                             user=os.environ.get("GHOST_SMTP_USER", "you@example.com"),
                             password="", from_name=os.environ.get("GHOST_FROM_NAME"))

        for i, r in enumerate(recipients, 1):
            msg = build_message(cfg, r, args.subject, body, args.html, attachments)
            if args.dry_run:
                print(f"[{i}/{len(recipients)}] DRY  -> {r.email} | "
                      f"subject={msg['Subject']!r}")
                sent += 1
                continue
            try:
                server.send_message(msg)
                sent += 1
                print(f"[{i}/{len(recipients)}] sent -> {r.email}")
            except Exception as e:
                failed += 1
                print(f"[{i}/{len(recipients)}] FAIL -> {r.email}: {e}")

            if args.delay > 0 and i < len(recipients):
                time.sleep(args.delay)
    finally:
        if server is not None:
            try:
                server.quit()
            except Exception:
                pass

    print(f"\nDone. sent={sent} failed={failed}")
    return 0 if failed == 0 else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ghostsender",
        description="Send email through your own authenticated SMTP account.",
    )
    p.add_argument("--recipients", required=True,
                   help="CSV (needs an 'email' column) or .txt (one address per line).")
    p.add_argument("--subject", required=True, help="Subject; supports {placeholders}.")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--body", help="Inline body text; supports {placeholders}.")
    g.add_argument("--body-file", help="Read body from a file; supports {placeholders}.")
    p.add_argument("--html", action="store_true", help="Treat the body as HTML.")
    p.add_argument("--attach", action="append", metavar="PATH",
                   help="Attach a file (repeatable).")
    p.add_argument("--delay", type=float, default=1.0,
                   help="Seconds to pause between sends (default: 1.0).")
    p.add_argument("--env", default=".env", help="Path to a .env file (default: .env).")
    p.add_argument("--dry-run", action="store_true",
                   help="Render and list messages without connecting or sending.")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return run(args)
    except KeyboardInterrupt:
        print("\nInterrupted.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
