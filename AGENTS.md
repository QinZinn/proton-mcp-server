# AGENTS.md — Setup guide for AI agents

> This file is a runbook an AI agent (e.g. Hermes / opencode / Claude Code) can
> follow to install and configure the **proton-mcp-server** MCP server for a
> user. Execute the steps in order, verify at each checkpoint, and surface the
> final result to the user.

## What this server does

Exposes a user's Proton Mail (read-only) to MCP-capable agents over the stdio
transport, reading mail from the local Proton Mail Bridge IMAP server. Supports
multiple Proton accounts, selected by name on each tool call. Read-only:
`list_accounts`, `list_folders`, `list_messages`, `search_messages`,
`get_message`.

## Prerequisites (verify before starting)

1. **Proton Mail Bridge is installed and running.**
   - Check: a TCP listener on `127.0.0.1:1143` (IMAP).
   - Linux: `ss -tlnp 2>/dev/null | grep -E '1143|1025'`
   - macOS: `lsof -iTCP:1143 -sTCP:LISTEN`
   - If not running, tell the user to open the Bridge GUI and sign in. IMAP/SMTP
     must be enabled in Bridge settings.
2. **Bridge credentials available.** For each Proton account the user wants to
   connect, you need the **bridge-generated password** (shown in the Bridge GUI
   per account) — *not* the user's Proton login password — and the Proton
   address as the username. Security is STARTTLS on `127.0.0.1:1143`.
3. **Python 3.11+.** Check: `python3 --version`.
4. **uv** (recommended installer). Check: `uv --version`. If missing, install:
   `curl -LsSf https://astral.sh/uv/install.sh | sh` (Linux/macOS) — confirm
   with the user before running an install script.

## Install steps

```sh
git clone https://github.com/QinZinn/proton-mcp-server.git
cd proton-mcp-server
uv sync            # creates .venv and installs dependencies
```

The server binary is `.venv/bin/proton-mcp-server` (or `uv run proton-mcp-server`).

## Configure accounts

Create the config at the default path (or a path you choose):

```sh
mkdir -p "${XDG_CONFIG_HOME:-$HOME/.config}/proton-mcp"
```

Then write `$XDG_CONFIG_HOME/proton-mcp/config.toml` (default
`~/.config/proton-mcp/config.toml`) — one `[[accounts]]` table per account:

```toml
[[accounts]]
name = "personal"                         # unique label the agent passes as `account`
username = "me@proton.me"                 # Proton address (IMAP login)
password = "BRIDGE_GENERATED_PASSWORD"    # from Proton Mail Bridge GUI
# host = "127.0.0.1"                       # optional, default 127.0.0.1
# port = 1143                             # optional, default 1143
# security = "starttls"                   # optional: starttls (default) | ssl | plain
```

Config path resolution (first wins): `--config PATH` flag >
`PROTON_MCP_CONFIG` env var > `$XDG_CONFIG_HOME/proton-mcp/config.toml`.

Set file permissions so only the owner can read it (it contains bridge
passwords): `chmod 600 "$HOME/.config/proton-mcp/config.toml"`.

**Never write the user's real bridge password into any file inside the git
repo** (the repo's `config.example.toml` is a template with placeholders). The
real config lives outside the repo and is `.gitignore`d by convention.

## Verify (smoke tests — do not skip)

```sh
uv run proton-mcp-server --print-config-path     # prints the config file it will load
uv run proton-mcp-server --list-accounts         # parses config, lists accounts (no IMAP)
```

Then verify a real IMAP round-trip for each configured account. From Python:

```python
from proton_mcp_server.config import load_config
from proton_mcp_server import imap_client as ic
for acc in load_config(None).accounts:
    print(acc.name, len(ic.list_folders(acc)), "folders")
```

Each account must return its folder list (INBOX, Sent, …) without raising
`ImapError`. If you see "IMAP login failed": the username is the Proton address
and the password is the **Bridge-generated** one (common mistake: using the
Proton account password instead). If you see "Cannot connect": Bridge is not
running or not listening on 127.0.0.1:1143.

## Wire into an MCP client (agent side)

Add a stdio server entry to your client's MCP config (Hermes / opencode /
Claude Desktop / Claude Code). For example:

```jsonc
{
  "mcpServers": {
    "proton-mail": {
      "command": "/ABS/PATH/proton-mcp-server/.venv/bin/proton-mcp-server",
      "env": { "PROTON_MCP_CONFIG": "/ABS/PATH/proton-mcp/config.toml" }
    }
  }
}
```

Use the absolute path to the venv binary. Omit `env` if using the default
config path. Restart the agent, then confirm the five tools
(`list_accounts`, `list_folders`, `list_messages`, `search_messages`,
`get_message`) are discoverable.

## Capabilities & limits (so you can reason about the tools)

- All operations are **read-only** (`BODY.PEEK`, no STORE/EXPUNGE). No sending,
  flagging, moving, or deleting.
- `list_messages(folder, limit, page)`: newest-first, paginated backwards
  (`page` 0 = newest window). Returns envelopes only.
- `search_messages(query, criteria)`: `criteria` ∈ subject/from/sender/to/cc/
  bcc/body/text. Single-field IMAP search; returns envelopes.
- `get_message(uid, folder, include_html)`: full message. HTML-only bodies are
  not rendered unless `include_html=true` (then a tag-stripped approximation is
  returned). Attachment metadata (name/type/size) is listed; bodies are not
  downloaded.
- Folder names are IMAP mailbox names (e.g. `INBOX`, `Sent`, `All Mail`,
  `Archive`). Use `list_folders` to get exact names before `list_messages` /
  `get_message` on non-default folders.
- UIDs are returned by `list_messages` / `search_messages`; pass them to
  `get_message`. UIDs are valid within a folder; if a mailbox is rebuilt, old
  UIDs may become stale.

## Troubleshooting map

| Symptom                                  | Likely cause / fix                                            |
|------------------------------------------|---------------------------------------------------------------|
| `Configuration file not found`           | Create `~/.config/proton-mcp/config.toml` or pass `--config`. |
| `IMAP login failed ... no such user`     | Wrong username (use the Proton address) or bridge password.   |
| `Cannot connect ... Is Proton Mail Bridge running?` | Bridge not running / not listening on 1143.        |
| `STARTTLS upgrade failed`                | Bridge version doesn't advertise STARTTLS; try `security="plain"` (localhost only) or `security="ssl"`. |
| Tools listed but `list_folders` errors   | Same as IMAP login failure — check credentials.              |
| `get_message` says message not found    | UID invalid for that folder, or mailbox rebuilt (UIDs stale). Call `list_messages` again. |