#!/usr/bin/env python3
"""sync.py — Build local metadata index from Proton Pass CLI."""
import json
import os
import shutil
import subprocess
import sys
import tempfile

TIMEOUT = 30
ALLOWED_ITEM_FIELDS = {"id", "title", "username", "email", "url"}


def log(msg):
    print(f"[sync] {msg}", file=sys.stderr, flush=True)


def find_cli():
    found = shutil.which("pass-cli")
    if found:
        return found
    for p in [
        os.path.expanduser("~/.local/bin/pass-cli"),
        "/opt/homebrew/bin/pass-cli",
        "/usr/local/bin/pass-cli",
    ]:
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    return None


def run_cli(cli, args):
    cmd = [cli] + args
    log(f"CLI: {args[0] if args else '?'}")
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=TIMEOUT,
        )
        if result.returncode != 0:
            log(f"Error rc={result.returncode}")
            return None
        return json.loads(result.stdout)
    except Exception as e:
        log(f"Exception: {e}")
        return None


def safe_index_dir():
    env_dir = os.environ.get("alfred_workflow_data", "")
    if not env_dir:
        env_dir = os.path.join(os.path.expanduser("~"), ".local", "share", "proton-pass-alfred")
    if os.path.islink(env_dir):
        sys.exit(1)
    os.makedirs(env_dir, mode=0o700, exist_ok=True)
    return env_dir


def build_index(cli):
    vaults_data = run_cli(cli, ["vault", "list", "--output", "json"])
    if not vaults_data:
        log("No vaults")
        return []

    vaults = vaults_data if isinstance(vaults_data, list) else vaults_data.get("vaults", [])
    if not isinstance(vaults, list):
        vaults = []
    log(f"{len(vaults)} vault(s)")

    items = []
    for vault in vaults:
        share_id = vault.get("share_id", "")
        vault_name = vault.get("name", "Unknown")
        if not share_id or not isinstance(share_id, str):
            continue

        items_data = run_cli(cli, ["item", "list", "--share-id", share_id, "--show-secrets", "--output", "json"])
        if not items_data:
            continue

        vault_items = items_data if isinstance(items_data, list) else items_data.get("items", [])
        if not isinstance(vault_items, list):
            vault_items = []
        log(f"  {vault_name}: {len(vault_items)} item(s)")

        for item in vault_items:
            if not isinstance(item, dict):
                continue
            meta = {"vault_share_id": share_id, "vault_name": vault_name}
            content = item.get("content", {})
            login = content.get("content", {}).get("Login", {})
            for field in ALLOWED_ITEM_FIELDS:
                if field == "title":
                    meta[field] = content.get("title", "")
                elif field in ("email", "username"):
                    meta[field] = login.get(field, "")
                elif field == "url":
                    urls = login.get("urls", [])
                    meta[field] = urls[0] if urls else ""
                else:
                    val = item.get(field, "")
                    meta[field] = val if isinstance(val, str) else str(val)
            items.append(meta)

    return items


def main():
    log("Starting sync")

    cli = find_cli()
    if not cli:
        log("pass-cli NOT FOUND")
        print("pass-cli not found", file=sys.stderr)
        sys.exit(1)
    log(f"CLI: {cli}")

    items = build_index(cli)

    index_dir = safe_index_dir()
    index_path = os.path.join(index_dir, "index.json")

    if os.path.islink(index_path):
        sys.exit(1)

    with open(index_path, "w") as f:
        json.dump({"items": items, "count": len(items)}, f)

    try:
        os.chmod(index_path, 0o600)
    except OSError:
        pass

    log(f"Saved {len(items)} item(s)")


if __name__ == "__main__":
    main()
