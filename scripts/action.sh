#!/bin/bash
# action.sh — Dispatch credential actions from Alfred.
#
# SECURITY NOTES:
# - Never writes secrets to files or logs
# - Secrets go directly to pbcopy, never stored in variables longer than needed
# - All Python calls pass values via sys.argv (no string interpolation)
# - URL scheme validation prevents file:// abuse
#
# ENV VARS (set by Alfred workflow variables):
#   $clipboard_clear_seconds — clipboard clear delay (default: 30)
#   $action        — password | username | totp | open_url
#   $item_id       — Proton Pass item ID
#   $vault_share_id — Proton Pass vault share ID
#   $url           — URL (only for open_url action)

set -o pipefail

CLIPBOARD_CLEAR_SECONDS="${clipboard_clear_seconds:-30}"
WORKFLOW_DIR="$HOME/.local/share/proton-pass-alfred"
mkdir -p "$WORKFLOW_DIR" 2>/dev/null || true

# Kill any previous clipboard-clear process
CLIPBOARD_PID_FILE="$WORKFLOW_DIR/clipboard.pid"
if [[ -f "$CLIPBOARD_PID_FILE" ]]; then
    old_pid=$(cat "$CLIPBOARD_PID_FILE" 2>/dev/null)
    if [[ -n "$old_pid" ]] && kill -0 "$old_pid" 2>/dev/null; then
        kill "$old_pid" 2>/dev/null || true
    fi
    rm -f "$CLIPBOARD_PID_FILE"
fi

# Index path — never fallback to world-writable /tmp
INDEX_PATH="${alfred_workflow_data:-$HOME/.local/share/proton-pass-alfred}/index.json"
if [[ ! -f "$INDEX_PATH" ]]; then
    INDEX_PATH="$HOME/Library/Application Support/Alfred/Workflow Data/com.alfred.protonpass.v2/index.json"
fi

# Find pass-cli
find_cli() {
    local found
    found=$(command -v pass-cli 2>/dev/null) && echo "$found" && return
    for p in "$HOME/.local/bin/pass-cli" /opt/homebrew/bin/pass-cli /usr/local/bin/pass-cli; do
        [[ -x "$p" ]] && echo "$p" && return
    done
    return 1
}
PASS_CLI=$(find_cli)

log() {
    echo "[action] $*" >&2
}

index_read() {
    local item_id="$1"
    shift
    python3 - "$INDEX_PATH" "$item_id" "$@" <<'PYEOF'
import json, sys

index_path = sys.argv[1]
item_id = sys.argv[2]
fields = sys.argv[3:]

with open(index_path) as f:
    data = json.load(f)

for item in data.get("items", []):
    if item.get("id") == item_id:
        for field in fields:
            val = item.get(field, "")
            print(val)
        sys.exit(0)
sys.exit(1)
PYEOF
}

notify() {
    local msg="$1"
    local sub="$2"
    osascript -e "display notification \"${msg}\" with title \"Proton Pass\" subtitle \"${sub}\"" 2>/dev/null || true
}

schedule_clipboard_clear() {
    local label="$1"
    setsid bash -c "
        sleep $CLIPBOARD_CLEAR_SECONDS
        pbcopy < /dev/null
        osascript -e 'display notification \"Clipboard cleared\" with title \"Proton Pass\" subtitle \"$label\"'
    " </dev/null >/dev/null 2>&1 &
    local bg_pid=$!
    echo "$bg_pid" > "$CLIPBOARD_PID_FILE"
    disown "$bg_pid" 2>/dev/null
}

clipboard_copy_and_clear() {
    local secret="$1"
    local label="$2"

    printf '%s' "$secret" | pbcopy
    notify "Copied to clipboard" "$label"
    schedule_clipboard_clear "$label"
    log "Copied ${label}, clipboard clears in ${CLIPBOARD_CLEAR_SECONDS}s"
}

auto_type() {
    local secret="$1"
    local label="$2"

    printf '%s' "$secret" | pbcopy
    sleep 0.1
    osascript -e 'tell application "System Events" to keystroke "v" using command down' 2>/dev/null
    notify "Auto-typed" "$label"
    schedule_clipboard_clear "$label"
    log "Auto-typed ${label}, clipboard clears in ${CLIPBOARD_CLEAR_SECONDS}s"
}

# --- Parse arg field (action|item_id|vault_share_id) ---
input="${1:-}"
if [[ -z "$input" ]]; then
    log "ERROR: No input received"
    notify "Error: no input" "Proton Pass"
    exit 1
fi

IFS='|' read -r action item_id vault_share_id url <<< "$input"

case "$action" in
    password)
        if [[ -z "${item_id:-}" ]]; then
            log "ERROR: Missing item_id"
            notify "Error: missing item info" "Proton Pass"
            exit 1
        fi
        if [[ -z "$PASS_CLI" ]]; then
            log "ERROR: pass-cli not found"
            notify "pass-cli not found" "Proton Pass"
            exit 1
        fi
        secret=$("$PASS_CLI" item view --share-id "$vault_share_id" --item-id "$item_id" --field password 2>/dev/null)

        if [[ -z "$secret" ]]; then
            log "ERROR: No password from pass-cli"
            notify "No password found" "Proton Pass"
            exit 1
        fi

        auto_type "$secret" "Password"
        ;;

    username)
        if [[ -z "${item_id:-}" ]]; then
            log "ERROR: Missing item_id"
            notify "Error: missing item info" "Proton Pass"
            exit 1
        fi
        secret=$(index_read "$item_id" "email" "username")
        secret=$(echo "$secret" | while IFS= read -r line; do
            [[ -n "$line" ]] && echo "$line" && break
        done)

        if [[ -z "$secret" ]]; then
            log "ERROR: No username in index"
            notify "No username found" "Proton Pass"
            exit 1
        fi

        clipboard_copy_and_clear "$secret" "Username"
        ;;

    totp)
        if [[ -z "${item_id:-}" ]]; then
            log "ERROR: Missing item_id"
            notify "Error: missing item info" "Proton Pass"
            exit 1
        fi
        if [[ -z "$PASS_CLI" ]]; then
            log "ERROR: pass-cli not found"
            notify "pass-cli not found" "Proton Pass"
            exit 1
        fi
        secret=$("$PASS_CLI" item totp --share-id "$vault_share_id" --item-id "$item_id" --output json 2>/dev/null | python3 -c "import json,sys; print(json.load(sys.stdin).get('totp',''))" 2>/dev/null)

        if [[ -z "$secret" ]]; then
            log "ERROR: TOTP generation failed"
            notify "TOTP generation failed" "Proton Pass"
            exit 1
        fi

        auto_type "$secret" "TOTP Code"
        ;;

    open_url)
        if [[ -z "${url:-}" ]]; then
            log "ERROR: No URL provided"
            notify "No URL found" "Proton Pass"
            exit 1
        fi
        if [[ ! "$url" =~ ^https?:// ]]; then
            log "ERROR: Invalid URL scheme"
            notify "Invalid URL" "Proton Pass"
            exit 1
        fi
        log "Opening URL"
        open "$url"
        notify "Opened in browser" "Proton Pass"
        ;;

    *)
        log "ERROR: Unknown action: $action"
        notify "Unknown action" "Proton Pass"
        exit 1
        ;;
esac
