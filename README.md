# Proton Pass — Alfred Workflow

Search and access [Proton Pass](https://proton.me/pass) items from [Alfred](https://www.alfredapp.com/) via [pass-cli](https://github.com/nicholasgasior/pass-cli).

## Features

- **Fuzzy search** across titles, usernames, emails, vaults
- **Auto-type** passwords and TOTP codes via ⌘V
- **Copy username** with ⌘ modifier
- **Generate TOTP** with ⌥ modifier — no Proton app needed
- **Open URL** with ⌃ modifier
- **Auto-clear clipboard** after configurable delay (default: 30s)
- **Zero secrets on disk** — passwords and TOTP fetched from pass-cli at runtime

## Requirements

- macOS
- [Alfred 5](https://www.alfredapp.com/) with Powerpack
- [pass-cli](https://github.com/nicholasgasior/pass-cli) authenticated (`pass-cli login`)

## Install

### From Release

Download `ProtonPass.alfredworkflow` from [Releases](https://github.com/lcampoverde/proton-pass-alfred/releases) and double-click to install.

### Build from Source

```bash
git clone https://github.com/lcampoverde/proton-pass-alfred.git
cd proton-pass-alfred
zip -r ProtonPass.alfredworkflow info.plist scripts/ icon.png
```

Double-click `ProtonPass.alfredworkflow` to install.

## Setup

### 1. Configure Script Filter

After import, Alfred resets Script Filter settings. Fix:

1. Open Alfred Workflows → Proton Pass
2. Double-click **pp** (Script Filter)
3. Set **Argument Required** and **with input as argv**
4. Set **Scriptargtype** to `argv`

### 2. Configure Sync Keyword

1. Double-click **pp-sync** (Keyword)
2. Set **Argument** to `No argument`

### 3. Build Index

Run `pp-sync` in Alfred to build the local metadata index.

## Usage

| Key | Action |
|-----|--------|
| `Enter` | Auto-type password |
| `⌘ Enter` | Copy username to clipboard |
| `⌥ Enter` | Auto-type TOTP code |
| `⌃ Enter` | Open URL in browser |

### Workflow Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `clipboard_clear_seconds` | `30` | Seconds before clipboard is cleared |

Change in: Alfred → Workflows → Proton Pass → ⚙️ → Workflow Variables.

## Architecture

```
pp (Script Filter)
  └── search.py — fuzzy search index.json
  └── action.sh — dispatch: password/username/totp/open_url
        ├── password → pass-cli item view (runtime)
        ├── username → index.json (metadata only)
        ├── totp    → pass-cli item totp (runtime)
        └── open_url → open in browser

pp-sync (Keyword)
  └── sync.py — rebuild index from pass-cli
```

### What's stored on disk

| File | Content | Secrets? |
|------|---------|----------|
| `index.json` | id, title, email, username, url, vault | No |
| `clipboard.pid` | PID of background clear process | No |

Passwords and TOTP are fetched from pass-cli on each action. Clipboard holds secrets for `clipboard_clear_seconds` then clears.

## Security

- No secrets in index.json (password/totp_uri removed)
- Clipboard auto-clears after configurable delay
- Symlink checks on index file/directory
- No shell interpolation in Python calls
- URL scheme validation (http/https only)
- Background processes fully detached (setsid+disown)

## License

MIT
