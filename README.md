# Proton Mail MCP Server

Read-only access to [Proton Mail](https://proton.me/mail) for AI agents (such
as **Hermes**) over the [Model Context Protocol](https://modelcontextprotocol.io)
(stdio transport).

Mail is read from [Proton Mail Bridge](https://proton.me/mail/bridge), which
runs a local IMAP server. The MCP server wraps that IMAP server and exposes a
small set of tools. Multiple Proton accounts are supported and selected by name
on each tool call.

> Read-only by design: listing folders/messages, searching, and reading a
> message. Sending or moving/deleting mail is intentionally out of scope.

## How it works

```
+----------+   stdio/stdin+stdout   +---------------------+   IMAP (local)  +---------------------+
|  Agent   | <---------------------> | proton-mcp-server   | <------------>  | Proton Mail Bridge  |
| (Hermes) |   MCP (JSON-RPC)        | (this package)      | 127.0.0.1:1143  |  (protonmail-bridge)|
+----------+                        +---------------------+                 +---------------------+
```

Proton Mail Bridge must be installed, signed in, and running. In the Bridge
GUI, for each account enable the IMAP/SMTP client and copy the **generated
password** (this is _not_ your Proton account password).

## Install

Requires Python 3.11+. Using [uv](https://docs.astral.sh/uv/) (recommended):

```bash
git clone <this repo> && cd proton-mcp-server
uv sync          # create venv + install dependencies
```

Or with pip into a venv of your choice: `pip install .`

The `proton-mcp-server` console script is provided.

## Configure accounts

Create a config file listing each account (see `config.example.toml`):

```bash
mkdir -p "${XDG_CONFIG_HOME:-$HOME/.config}/proton-mcp"
cp config.example.toml "${XDG_CONFIG_HOME:-$HOME/.config}/proton-mcp/config.toml"
# then edit it with your bridge username + generated password
```

Config-file lookup order (first wins):

1. `--config PATH` CLI flag
2. `PROTON_MCP_CONFIG` environment variable
3. `$XDG_CONFIG_HOME/proton-mcp/config.toml` (default `~/.config/proton-mcp/config.toml`)

`[[accounts]]` fields:

| field     | required | default     | notes                                                    |
|-----------|----------|-------------|----------------------------------------------------------|
| `name`    | yes      | —           | Unique label agents pass as the `account` argument.      |
| `username`| yes      | —           | Your Proton address (the IMAP login name).               |
| `password`| yes      | —           | Password generated **by Proton Mail Bridge**, not Proton. |
| `host`     | no       | `127.0.0.1` | Bridge listens on localhost.                                   |
| `port`     | no       | `1143`      | Bridge IMAP port.                                              |
| `security` | no       | `starttls`  | `starttls` (Bridge v3 default), `ssl` (TLS from start), `plain`. |

## Tools

| tool             | description                                              |
|------------------|----------------------------------------------------------|
| `list_accounts`  | List configured account names.                           |
| `list_folders`   | List mailboxes for an account (INBOX, Sent, …).          |
| `list_messages`  | List recent messages in a folder, newest first.         |
| `search_messages`| Search a folder by subject/from/to/cc/body/text.         |
| `get_message`    | Fetch and render a full message by UID.                |

Run `proton-mcp-server --list-accounts` to smoke-test the config (this does
_not_ require Bridge to be reachable — it only parses the file).

## Use with Hermes

Add the server to your Hermes MCP configuration (stdio server):
```jsonc
{
  "mcpServers": {
    "proton-mail": {
      "command": "/abs/path/to/proton-mcp-server/.venv/bin/proton-mcp-server",
      "env": { "PROTON_MCP_CONFIG": "/abs/path/to/proton-mcp/config.toml" }
    }
  }
}
```
(Or omit `env` if you use the default config path.) Then ask Hermes to read
your mail; it will discover the tools via MCP.

## Develop / debug

```bash
uv sync
uv run proton-mcp-server --help
uv run proton-mcp-server --print-config-path
uv run proton-mcp-server --list-accounts
```

To inspect the protocol by hand, pipe a JSON-RPC `initialize` + `tools/list`
exchange into the running server over stdio.

## Security notes

- Config holds bridge passwords; keep it readable only by you (`chmod 600`).
  `config.toml` is git-ignored by default.
- The connection to Proton Mail Bridge is **localhost only**. The default
  `security = "starttls"` upgrades to TLS via STARTTLS after connecting; the
  Bridge's local self-signed certificate is accepted with verification
  disabled (the connection never leaves localhost). `security = "ssl"`
  (TLS from connection start) and `security = "plain"` (no encryption) are
  also available. The server never connects to a remote host with
  verification off — and all connection fields are configurable per account.
- All operations are read-only (BODY.PEEK, no STORE/EXPUNGE).

## License

MIT — see [LICENSE](LICENSE).