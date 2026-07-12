#!/usr/bin/env python3
"""search.py — Search local Proton Pass metadata index.

Security:
- Read-only: no writes, no subprocess
- Symlink-safe: validates index file before reading
- Only metadata from index.json (no secrets)
- Max 5 search terms to prevent resource exhaustion
"""

import json
import os
import sys
import urllib.parse

INDEX_DIR = os.environ.get("alfred_workflow_data", "")
if not INDEX_DIR:
    INDEX_DIR = os.path.join(os.path.expanduser("~"), ".local", "share", "proton-pass-alfred")
INDEX_PATH = os.path.join(INDEX_DIR, "index.json")
MAX_RESULTS = 20
MAX_SEARCH_TERMS = 5


def log(msg):
    print(f"[search] {msg}", file=sys.stderr)


def load_index():
    """Load metadata index. Returns list of items."""
    if not INDEX_PATH:
        return []

    # Symlink check: refuse to read symlinked index
    if os.path.islink(INDEX_PATH):
        log("Symlink detected at index, refusing")
        return []

    if not os.path.exists(INDEX_PATH):
        return []

    try:
        with open(INDEX_PATH, "r") as f:
            data = json.load(f)
    except (json.JSONDecodeError, PermissionError, FileNotFoundError):
        return []
    except OSError as e:
        log(f"OS error reading index: {e}")
        return []

    items = data.get("items", [])
    if not isinstance(items, list):
        return []

    # Validate each item has required fields
    validated = []
    for item in items:
        if isinstance(item, dict) and "id" in item and "title" in item:
            validated.append(item)
    return validated


def extract_domain(url):
    """Extract domain from URL."""
    if not url or not isinstance(url, str):
        return ""
    try:
        parsed = urllib.parse.urlparse(url)
        return parsed.netloc or url
    except Exception:
        return ""


def search_items(items, query):
    """Fuzzy search: all terms must appear in title+username+url."""
    if not query.strip():
        return items[:MAX_RESULTS]

    terms = query.lower().split()[:MAX_SEARCH_TERMS]
    scored = []

    for item in items:
        title_lower = item.get("title", "").lower()
        username_lower = item.get("username", "").lower()
        email_lower = item.get("email", "").lower()
        url = item.get("url", "")
        vault_name = item.get("vault_name", "").lower()

        searchable = f"{title_lower} {username_lower} {email_lower} {url} {vault_name}"

        if not all(t in searchable for t in terms):
            continue

        score = 0
        domain = extract_domain(url).lower()

        for t in terms:
            if title_lower == t:
                score += 100
            elif title_lower.startswith(t):
                score += 80
            elif t in title_lower:
                score += 60
            if t in username_lower:
                score += 40
            if t in email_lower:
                score += 40
            if t in domain:
                score += 20

        scored.append((score, item))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in scored[:MAX_RESULTS]]


def build_alfred_items(results):
    """Convert search results to Alfred Script Filter JSON."""
    alfred_items = []

    for item in results:
        item_id = item.get("id", "")
        vault_share_id = item.get("vault_share_id", "")
        title = item.get("title", "Untitled")
        username = item.get("username", "")
        email = item.get("email", "")
        login = email or username
        url = item.get("url", "")
        vault_name = item.get("vault_name", "")
        domain = extract_domain(url)

        subtitle_parts = []
        if login:
            subtitle_parts.append(login)
        if vault_name:
            subtitle_parts.append(vault_name)
        subtitle = " — ".join(subtitle_parts) if subtitle_parts else "No username"

        mods = {}

        if login:
            mods["cmd"] = {
                "subtitle": f"Copy username: {login}",
                "arg": f"username|{item_id}|{vault_share_id}",
                "variables": {
                    "action": "username",
                    "item_id": item_id,
                    "vault_share_id": vault_share_id,
                },
            }

        mods["alt"] = {
            "subtitle": "Copy TOTP code",
            "arg": f"totp|{item_id}|{vault_share_id}",
            "variables": {
                "action": "totp",
                "item_id": item_id,
                "vault_share_id": vault_share_id,
            },
        }

        if url:
            mods["ctrl"] = {
                "subtitle": f"Open: {domain}",
                "arg": f"open_url|{url}",
                "variables": {
                    "action": "open_url",
                    "url": url,
                },
            }

        alfred_items.append({
            "uid": item_id,
            "title": title,
            "subtitle": subtitle,
            "arg": f"password|{item_id}|{vault_share_id}",
            "icon": {"path": "icon.png"},
            "autocomplete": title,
            "valid": True,
            "mods": mods,
            "variables": {
                "action": "password",
                "item_id": item_id,
                "vault_share_id": vault_share_id,
            },
        })

    return alfred_items


def main():
    query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else ""
    items = load_index()

    if not items:
        print(json.dumps({"items": [{
            "title": "No items found",
            "subtitle": "Run 'pp-sync' to build index",
            "valid": False,
            "icon": {"path": "icon.png"},
        }]}))
        return

    results = search_items(items, query)
    alfred_items = build_alfred_items(results)

    if not alfred_items:
        alfred_items = [{
            "title": f"No match for '{query}'",
            "subtitle": f"{len(items)} items indexed",
            "valid": False,
            "icon": {"path": "icon.png"},
        }]

    print(json.dumps({"items": alfred_items}))


if __name__ == "__main__":
    main()
