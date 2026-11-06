# GhostSender

A simple desktop app for sending email through your own email account
(Gmail, Outlook/Office 365, Yahoo, iCloud, or a custom SMTP server) CREATED BY BENTLEY TECH INNOVATIONS.

## Platforms

GhostSender runs on **Windows, macOS, and Linux**. Native binaries for all
three are built automatically on GitHub (see *Cross-platform builds* below) —
no Python required by the end user. The Windows `.exe` in `dist/` is a
64-bit Windows build only; it will not run on Mac or Linux.

## Download & run (Windows)

1. Download **GhostSender.exe** (in the `dist` folder).
2. Double-click it. No installation and no Python needed — it's a single
   self-contained app for 64-bit Windows.
3. The first launch may take a few seconds while Windows unpacks it.

### macOS / Linux

Download the matching binary from the project's GitHub **Releases** or
**Actions** page (`GhostSender-macos.zip` / `GhostSender-linux.zip`), unzip,
and run it. On macOS, right-click the app -> *Open* the first time to get
past the unsigned-app warning. On Linux, mark it executable if needed:
`chmod +x GhostSender`.

> **Antivirus note:** PyInstaller one-file apps are sometimes flagged by
> SmartScreen or antivirus as "unknown publisher." That's a false positive
> from not being code-signed, not malware. Click *More info -> Run anyway*,
> or build it yourself from the source (below) if you prefer.

## How to use it

1. **Provider** – pick your email provider. The SMTP server and port fill
   in automatically. Choose **Custom** to type your own server.
2. **Email / login** and **App password** – see the note below about app
   passwords.
3. **Recipients file** – a `.csv` with an `email` column (extra columns like
   `name` become `{placeholders}`), or a `.txt` with one address per line.
4. **Subject** and **Body** – you can use `{name}`, `{email}`, etc. Tick
   **HTML body** if your body is HTML. Add attachments if you like.
5. **Preview (dry run)** – lists exactly what would be sent, connecting to
   nothing. No password required.
6. **Send** – confirms the count, then sends with a live log and progress bar.

## App passwords (important)

For Gmail, Yahoo, and iCloud — and for Outlook/365 accounts with 2FA — your
normal login password will **not** work for SMTP. Generate an *app password*:

- **Gmail:** Google Account -> Security -> 2-Step Verification -> App passwords
- **Outlook/365:** Microsoft account security -> app passwords
- **Yahoo:** Account Security -> Generate app password
- **iCloud:** appleid.apple.com -> Sign-In and Security -> App-Specific Passwords

## Responsible use

GhostSender signs in as your own account and sends with a truthful From
address. Only send mail you're authorized to send — your own notifications,
transactional mail, or a list people opted into. It does not spoof senders
or disguise origin. If recipients aren't receiving your mail, set up
SPF/DKIM/DMARC on your sending domain rather than trying to bypass filters.

## Run from source (optional)

```bash
python ghostsender_gui.py          # GUI
python ghostsender.py --help       # command-line version
```

## Rebuild locally (current OS only)

```bash
pip install pyinstaller
pyinstaller --noconfirm --onefile --windowed --name GhostSender \
    --hidden-import ghostsender ghostsender_gui.py
# result: dist/GhostSender(.exe)
```

A local build only produces a binary for the OS you build on.

## Cross-platform builds (Windows + macOS + Linux)

A GitHub Actions workflow (`.github/workflows/build.yml`) builds all three
binaries on GitHub's own Windows, macOS, and Linux servers.

**One-time setup:**

```bash
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/<you>/ghostsender.git
git push -u origin main
```

- Every push builds all three; download them from the repo's **Actions** tab
  -> the latest run -> *Artifacts*.
- To publish a downloadable **Release** with the three zips attached, push a
  version tag:

  ```bash
  git tag v1.0.0
  git push origin v1.0.0
  ```
