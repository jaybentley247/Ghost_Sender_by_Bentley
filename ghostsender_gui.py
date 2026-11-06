#!/usr/bin/env python3
"""
GhostSender GUI - a friendly desktop front-end for ghostsender.py.

Pick your email provider (Gmail, Outlook/Office 365, Yahoo, or Custom),
enter your account + app password, choose a recipients file and a message,
then Preview (dry run) or Send. Sending runs in the background with a live
log, so the window stays responsive.

Run:
    python ghostsender_gui.py

It authenticates as your own account and sends with a truthful From that
matches the account you log in with. Use it only for mail you're
authorized to send.
"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

import ghostsender as backend

APP_NAME = "GhostSender"
APP_VERSION = "1.0.0"
APP_VENDOR = "Bentley Tech Innovations"


# --------------------------------------------------------------------------- #
# Provider presets: (host, port, help text)
# --------------------------------------------------------------------------- #
# Encryption presets and the port each one uses.
SECURITY_PORTS: dict[str, int] = {
    "STARTTLS": 587,
    "SSL/TLS": 465,
}

PROVIDERS: dict[str, dict] = {
    "Gmail": {
        "host": "smtp.gmail.com",
        "security": "STARTTLS",
        "note": "Use a 16-char App Password (Google Account - Security - "
                "2-Step Verification - App passwords). Your normal password "
                "will not work.",
    },
    "Outlook / Office 365": {
        "host": "smtp.office365.com",
        "security": "STARTTLS",
        "note": "Use your Microsoft 365 / Outlook.com address and an app "
                "password if your account has 2FA enabled.",
    },
    "Yahoo Mail": {
        "host": "smtp.mail.yahoo.com",
        "security": "SSL/TLS",
        "note": "Generate an app password in Yahoo Account Security.",
    },
    "iCloud Mail": {
        "host": "smtp.mail.me.com",
        "security": "STARTTLS",
        "note": "Use an app-specific password from appleid.apple.com.",
    },
    "Custom": {
        "host": "",
        "security": "STARTTLS",
        "note": "Enter your provider's SMTP host and port manually. "
                "SSL/TLS uses port 465; STARTTLS uses 587.",
    },
}


class GhostSenderApp(ttk.Frame):
    def __init__(self, master: tk.Tk):
        super().__init__(master, padding=12)
        self.master_window = master
        master.title(f"{APP_NAME} — {APP_VENDOR}")
        master.minsize(640, 720)
        self.grid(sticky="nsew")
        master.columnconfigure(0, weight=1)
        master.rowconfigure(0, weight=1)

        self.log_queue: queue.Queue[str] = queue.Queue()
        self._worker: threading.Thread | None = None

        self._build_ui()
        self._on_provider_change()
        self._on_rec_mode()
        self.after(100, self._drain_log)

    # ------------------------------------------------------------------ UI --
    def _build_ui(self) -> None:
        self.columnconfigure(1, weight=1)
        row = 0

        # --- Branded header --------------------------------------------- #
        header = ttk.Frame(self)
        header.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(0, 8))
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text=APP_NAME,
                  font=("Segoe UI", 18, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(header, text=f"by {APP_VENDOR}",
                  foreground="#666").grid(row=1, column=0, sticky="w")
        ttk.Button(header, text="About",
                   command=self._show_about).grid(row=0, column=1, rowspan=2, sticky="e")
        row += 1

        # --- Account section -------------------------------------------- #
        acct = ttk.LabelFrame(self, text="Email account", padding=10)
        acct.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(0, 10))
        acct.columnconfigure(1, weight=1)
        row += 1

        ttk.Label(acct, text="Provider:").grid(row=0, column=0, sticky="w", pady=3)
        self.provider_var = tk.StringVar(value="Gmail")
        self.provider_cb = ttk.Combobox(
            acct, textvariable=self.provider_var, state="readonly",
            values=list(PROVIDERS.keys()))
        self.provider_cb.grid(row=0, column=1, columnspan=2, sticky="ew", pady=3)
        self.provider_cb.bind("<<ComboboxSelected>>", lambda e: self._on_provider_change())

        self.note_var = tk.StringVar()
        note = ttk.Label(acct, textvariable=self.note_var, foreground="#555",
                         wraplength=560, justify="left")
        note.grid(row=1, column=0, columnspan=3, sticky="w", pady=(0, 6))

        ttk.Label(acct, text="SMTP host:").grid(row=2, column=0, sticky="w", pady=3)
        self.host_var = tk.StringVar()
        self.host_entry = ttk.Entry(acct, textvariable=self.host_var)
        self.host_entry.grid(row=2, column=1, sticky="ew", pady=3)

        ttk.Label(acct, text="Port:").grid(row=2, column=2, sticky="e", padx=(8, 2))
        self.port_var = tk.StringVar(value="587")
        self.port_entry = ttk.Entry(acct, textvariable=self.port_var, width=7)
        self.port_entry.grid(row=2, column=3, sticky="w", pady=3)
        acct.columnconfigure(3, weight=0)

        ttk.Label(acct, text="Encryption:").grid(row=3, column=0, sticky="w", pady=3)
        self.security_var = tk.StringVar(value="STARTTLS")
        self.security_cb = ttk.Combobox(
            acct, textvariable=self.security_var, state="readonly", width=12,
            values=list(SECURITY_PORTS.keys()))
        self.security_cb.grid(row=3, column=1, sticky="w", pady=3)
        self.security_cb.bind("<<ComboboxSelected>>",
                              lambda e: self._on_security_change())

        ttk.Label(acct, text="Email / login:").grid(row=4, column=0, sticky="w", pady=3)
        self.user_var = tk.StringVar()
        ttk.Entry(acct, textvariable=self.user_var).grid(
            row=4, column=1, columnspan=3, sticky="ew", pady=3)

        ttk.Label(acct, text="App password:").grid(row=5, column=0, sticky="w", pady=3)
        self.pass_var = tk.StringVar()
        self.pass_entry = ttk.Entry(acct, textvariable=self.pass_var, show="•")
        self.pass_entry.grid(row=5, column=1, columnspan=2, sticky="ew", pady=3)
        self.show_pass = tk.BooleanVar(value=False)
        ttk.Checkbutton(acct, text="Show", variable=self.show_pass,
                        command=self._toggle_pass).grid(row=5, column=3, sticky="w")

        ttk.Label(acct, text="From name:").grid(row=6, column=0, sticky="w", pady=3)
        self.fromname_var = tk.StringVar()
        ttk.Entry(acct, textvariable=self.fromname_var).grid(
            row=6, column=1, columnspan=3, sticky="ew", pady=3)

        # --- Message section -------------------------------------------- #
        msg = ttk.LabelFrame(self, text="Message", padding=10)
        msg.grid(row=row, column=0, columnspan=3, sticky="nsew", pady=(0, 10))
        msg.columnconfigure(1, weight=1)
        self.rowconfigure(row, weight=1)
        row += 1

        # --- Recipients: choose file upload OR pasted addresses --------- #
        rec = ttk.LabelFrame(msg, text="Recipients", padding=8)
        rec.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 6))
        rec.columnconfigure(1, weight=1)

        self.rec_mode = tk.StringVar(value="file")
        mode_bar = ttk.Frame(rec)
        mode_bar.grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 4))
        ttk.Radiobutton(mode_bar, text="Upload file (CSV / TXT)", value="file",
                        variable=self.rec_mode,
                        command=self._on_rec_mode).pack(side="left")
        ttk.Radiobutton(mode_bar, text="Paste addresses", value="paste",
                        variable=self.rec_mode,
                        command=self._on_rec_mode).pack(side="left", padx=(14, 0))

        # File row
        self.rec_file_row = ttk.Frame(rec)
        self.rec_file_row.grid(row=1, column=0, columnspan=3, sticky="ew")
        self.rec_file_row.columnconfigure(0, weight=1)
        self.recipients_var = tk.StringVar()
        ttk.Entry(self.rec_file_row, textvariable=self.recipients_var).grid(
            row=0, column=0, sticky="ew", pady=3)
        ttk.Button(self.rec_file_row, text="Browse...",
                   command=self._pick_recipients).grid(row=0, column=1, padx=(6, 0))

        # Paste row
        self.rec_paste_row = ttk.Frame(rec)
        self.rec_paste_row.grid(row=1, column=0, columnspan=3, sticky="ew")
        self.rec_paste_row.columnconfigure(0, weight=1)
        ttk.Label(self.rec_paste_row,
                  text="Separate addresses with commas, spaces, or new lines:",
                  foreground="#555").grid(row=0, column=0, sticky="w")
        self.paste_text = scrolledtext.ScrolledText(self.rec_paste_row, height=4,
                                                    wrap="word")
        self.paste_text.grid(row=1, column=0, sticky="ew", pady=(2, 3))

        ttk.Label(msg, text="Subject:").grid(row=1, column=0, sticky="w", pady=3)
        self.subject_var = tk.StringVar()
        ttk.Entry(msg, textvariable=self.subject_var).grid(
            row=1, column=1, columnspan=2, sticky="ew", pady=3)

        head = ttk.Frame(msg)
        head.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(8, 2))
        ttk.Label(head, text="Body  (use {name}, {email} for personalization):").pack(
            side="left")
        self.html_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(head, text="HTML body", variable=self.html_var).pack(side="right")
        ttk.Button(head, text="Load from file...",
                   command=self._load_body).pack(side="right", padx=(0, 10))

        self.body_text = scrolledtext.ScrolledText(msg, height=10, wrap="word")
        self.body_text.grid(row=3, column=0, columnspan=3, sticky="nsew", pady=3)
        msg.rowconfigure(3, weight=1)

        ttk.Label(msg, text="Attachments:").grid(row=4, column=0, sticky="w", pady=3)
        self.attach_var = tk.StringVar()
        ttk.Entry(msg, textvariable=self.attach_var).grid(
            row=4, column=1, sticky="ew", pady=3)
        ttk.Button(msg, text="Add file...",
                   command=self._add_attachment).grid(row=4, column=2, padx=(6, 0))

        opt = ttk.Frame(msg)
        opt.grid(row=5, column=0, columnspan=3, sticky="w", pady=(6, 0))
        ttk.Label(opt, text="Delay between sends (sec):").pack(side="left")
        self.delay_var = tk.StringVar(value="1.0")
        ttk.Entry(opt, textvariable=self.delay_var, width=6).pack(side="left", padx=(4, 0))

        # --- Action buttons --------------------------------------------- #
        actions = ttk.Frame(self)
        actions.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(0, 8))
        self.preview_btn = ttk.Button(actions, text="Preview (dry run)",
                                      command=lambda: self._start(dry_run=True))
        self.preview_btn.pack(side="left")
        self.send_btn = ttk.Button(actions, text="Send", command=lambda: self._start(dry_run=False))
        self.send_btn.pack(side="left", padx=(8, 0))
        self.progress = ttk.Progressbar(actions, mode="determinate")
        self.progress.pack(side="right", fill="x", expand=True, padx=(12, 0))
        row += 1

        # --- Log --------------------------------------------------------- #
        logf = ttk.LabelFrame(self, text="Log", padding=6)
        logf.grid(row=row, column=0, columnspan=3, sticky="nsew")
        logf.columnconfigure(0, weight=1)
        logf.rowconfigure(0, weight=1)
        self.rowconfigure(row, weight=1)
        self.log_text = scrolledtext.ScrolledText(logf, height=8, wrap="word",
                                                  state="disabled", background="#111",
                                                  foreground="#ddd")
        self.log_text.grid(row=0, column=0, sticky="nsew")
        row += 1

        # --- Footer credit ---------------------------------------------- #
        ttk.Label(self,
                  text=f"{APP_NAME} v{APP_VERSION}  •  © {APP_VENDOR}",
                  foreground="#888", anchor="center").grid(
            row=row, column=0, columnspan=3, sticky="ew", pady=(6, 0))

    def _show_about(self) -> None:
        messagebox.showinfo(
            f"About {APP_NAME}",
            f"{APP_NAME}  v{APP_VERSION}\n"
            f"Created by {APP_VENDOR}\n\n"
            "Send email through your own authenticated SMTP account\n"
            "(Gmail, Outlook/Office 365, Yahoo, iCloud, or custom).\n\n"
            "Use only for mail you are authorized to send.")

    # -------------------------------------------------------------- helpers --
    def _on_provider_change(self) -> None:
        preset = PROVIDERS[self.provider_var.get()]
        is_custom = self.provider_var.get() == "Custom"
        self.host_var.set(preset["host"])
        self.note_var.set(preset["note"])
        # Set the provider's default encryption, which drives the port.
        self.security_var.set(preset["security"])
        self._apply_port()
        state = "normal" if is_custom else "readonly"
        self.host_entry.configure(state=state)
        # Port is always derived from the encryption choice, so keep it
        # read-only (STARTTLS -> 587, SSL/TLS -> 465).
        self.port_entry.configure(state="readonly")

    def _on_security_change(self) -> None:
        self._apply_port()

    def _apply_port(self) -> None:
        """Set the port from the selected encryption type."""
        port = SECURITY_PORTS.get(self.security_var.get(), 587)
        self.port_var.set(str(port))

    def _toggle_pass(self) -> None:
        self.pass_entry.configure(show="" if self.show_pass.get() else "•")

    def _on_rec_mode(self) -> None:
        """Show the file picker or the paste box depending on the chosen mode."""
        if self.rec_mode.get() == "paste":
            self.rec_file_row.grid_remove()
            self.rec_paste_row.grid()
        else:
            self.rec_paste_row.grid_remove()
            self.rec_file_row.grid()

    def _gather_recipients(self) -> list:
        """Build the recipient list from whichever input mode is active."""
        if self.rec_mode.get() == "paste":
            return backend.parse_recipients_text(self.paste_text.get("1.0", "end-1c"))
        return backend.load_recipients_or_raise(self.recipients_var.get().strip())

    def _pick_recipients(self) -> None:
        path = filedialog.askopenfilename(
            title="Select recipients file",
            filetypes=[("Recipient lists", "*.csv *.txt"), ("All files", "*.*")])
        if path:
            self.recipients_var.set(path)

    def _load_body(self) -> None:
        path = filedialog.askopenfilename(
            title="Load message body",
            filetypes=[("Text/HTML", "*.txt *.html *.htm"), ("All files", "*.*")])
        if path:
            self.body_text.delete("1.0", "end")
            self.body_text.insert("1.0", Path(path).read_text(encoding="utf-8"))
            if path.lower().endswith((".html", ".htm")):
                self.html_var.set(True)

    def _add_attachment(self) -> None:
        path = filedialog.askopenfilename(title="Add attachment")
        if path:
            cur = self.attach_var.get().strip()
            self.attach_var.set(f"{cur};{path}" if cur else path)

    def _log(self, text: str) -> None:
        self.log_queue.put(text)

    def _drain_log(self) -> None:
        try:
            while True:
                line = self.log_queue.get_nowait()
                self.log_text.configure(state="normal")
                self.log_text.insert("end", line + "\n")
                self.log_text.see("end")
                self.log_text.configure(state="disabled")
        except queue.Empty:
            pass
        self.after(100, self._drain_log)

    # --------------------------------------------------------------- action --
    def _start(self, dry_run: bool) -> None:
        if self._worker and self._worker.is_alive():
            messagebox.showinfo("GhostSender", "A send is already in progress.")
            return

        # Gather + validate inputs on the UI thread.
        try:
            cfg = None
            if not dry_run:
                cfg = backend.SmtpConfig(
                    host=self.host_var.get().strip(),
                    port=int(self.port_var.get().strip() or "587"),
                    user=self.user_var.get().strip(),
                    password=self.pass_var.get(),
                    from_name=self.fromname_var.get().strip() or None,
                )
                if not (cfg.host and cfg.user and cfg.password):
                    messagebox.showerror(
                        "GhostSender",
                        "Host, email/login and app password are required to send.")
                    return
            recipients = self._gather_recipients()
        except Exception as e:
            messagebox.showerror("GhostSender", str(e))
            return

        subject = self.subject_var.get()
        body = self.body_text.get("1.0", "end-1c")
        html = self.html_var.get()
        attachments = [a for a in self.attach_var.get().split(";") if a.strip()]
        try:
            delay = max(0.0, float(self.delay_var.get() or "0"))
        except ValueError:
            delay = 1.0

        if not subject.strip() or not body.strip():
            messagebox.showerror("GhostSender", "Subject and body are required.")
            return
        if not recipients:
            messagebox.showerror("GhostSender", "No recipients found.")
            return

        if not dry_run:
            if not messagebox.askyesno(
                    "Confirm send",
                    f"Send this message to {len(recipients)} recipient(s)?"):
                return

        # Display-only cfg for dry run.
        if cfg is None:
            cfg = backend.SmtpConfig(
                host="dry-run", port=0,
                user=self.user_var.get().strip() or "you@example.com",
                password="", from_name=self.fromname_var.get().strip() or None)

        self.progress.configure(maximum=len(recipients), value=0)
        self._set_busy(True)
        self._worker = threading.Thread(
            target=self._send_worker,
            args=(cfg, recipients, subject, body, html, attachments, delay, dry_run),
            daemon=True)
        self._worker.start()

    def _send_worker(self, cfg, recipients, subject, body, html,
                     attachments, delay, dry_run) -> None:
        import time
        sent = failed = 0
        server = None
        mode = "DRY RUN" if dry_run else "SENDING"
        self._log(f"=== {mode}: {len(recipients)} recipient(s) ===")
        try:
            if not dry_run:
                self._log(f"Connecting to {cfg.host}:{cfg.port} ...")
                server = backend.connect(cfg)
                self._log("Connected and authenticated.")

            for i, r in enumerate(recipients, 1):
                try:
                    msg = backend.build_message(cfg, r, subject, body, html, attachments)
                except Exception as e:
                    failed += 1
                    self._log(f"[{i}/{len(recipients)}] FAIL build -> {r.email}: {e}")
                    self._bump_progress(i)
                    continue

                if dry_run:
                    self._log(f"[{i}/{len(recipients)}] would send -> {r.email} "
                              f"| subject={msg['Subject']!r}")
                    sent += 1
                else:
                    try:
                        server.send_message(msg)
                        sent += 1
                        self._log(f"[{i}/{len(recipients)}] sent -> {r.email}")
                    except Exception as e:
                        failed += 1
                        self._log(f"[{i}/{len(recipients)}] FAIL -> {r.email}: {e}")
                    if delay > 0 and i < len(recipients):
                        time.sleep(delay)
                self._bump_progress(i)
        except Exception as e:
            self._log(f"ERROR: {e}")
        finally:
            if server is not None:
                try:
                    server.quit()
                except Exception:
                    pass
            self._log(f"=== Done. sent={sent} failed={failed} ===\n")
            self.after(0, lambda: self._set_busy(False))

    def _bump_progress(self, value: int) -> None:
        self.after(0, lambda: self.progress.configure(value=value))

    def _set_busy(self, busy: bool) -> None:
        state = "disabled" if busy else "normal"
        self.send_btn.configure(state=state)
        self.preview_btn.configure(state=state)


def main() -> None:
    root = tk.Tk()
    try:
        ttk.Style().theme_use("clam")
    except tk.TclError:
        pass
    GhostSenderApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
