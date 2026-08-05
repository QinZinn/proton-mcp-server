"""The MCP server: read-only Proton Mail tools over the Model Context Protocol.

Exposes a small, agent-friendly set of tools backed by :mod:`imap_client`,
each parameterized by an account ``name`` chosen from the loaded configuration.
All return plain text so results render cleanly in any MCP client / agent.
"""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from . import __version__
from . import imap_client as imap
from .config import Config, load_config
from .imap_client import FolderInfo, GetMessage, ImapError, MessageSummary


def _fmt_flags(flags: list[str]) -> str:
    return " ".join(f[-1].upper() if f.startswith("\\") else f for f in flags) or "-"


def _format_summaries(messages: list[MessageSummary]) -> str:
    if not messages:
        return "No messages found."
    lines: list[str] = []
    for m in messages:
        flags = _fmt_flags(m.flags)
        lines.append(
            f"UID: {m.uid}  Folder: {m.folder}  Disposition: {flags}  Size: {m.size}B"
        )
        if m.subject:
            lines.append(f"  Subject: {m.subject}")
        if m.sender:
            lines.append(f"  From: {m.sender}")
        if m.to:
            lines.append(f"  To: {m.to}")
        if m.date:
            lines.append(f"  Date: {m.date}")
    return "\n".join(lines)


def _format_folders(folders: list[FolderInfo]) -> str:
    lines: list[str] = []
    for f in folders:
        marker = "" if f.selectable else "  (not selectable)"
        flags = ",".join(f.flags) if f.flags else ""
        lines.append(f"{f.name}{marker}" + (f"  [{flags}]" if flags else ""))
    return "\n".join(lines) if lines else "No folders found."


def _trim(text: str, limit: int = 20000) -> str:
    if len(text) <= limit:
        return text
    return (
        text[:limit]
        + f"\n\n... (truncated; original length {len(text)} characters) ..."
    )


def create_server(config_path: str | None = None) -> MCPServer:
    """Build and configure the :class:`MCPServer` with all tools registered."""
    config: Config = load_config(config_path)

    mcp = MCPServer(
        name="proton-mail",
        title="Proton Mail",
        description=(
            "Read-only access to Proton Mail through Proton Mail Bridge IMAP. "
            "Supports multiple accounts selected by name."
        ),
        instructions=(
            "All tools take an `account` name matching one in the config. "
            "Call `list_accounts` first to discover available account names, "
            "then `list_folders`, `list_messages`, `search_messages`, and "
            "`get_message` to read mail. Access is read-only."
        ),
        version=__version__,
    )

    @mcp.tool()
    def list_accounts() -> str:
        """List the configured Proton Mail accounts available to this server.

        Returns a plain-text list of account names with their IMAP host/port.
        Call this first to learn the `account` argument used by other tools.
        """
        lines = [
            f"{a.name}  (imap://{a.host}:{a.port}, user={a.username}, security={a.security})"
            for a in config.accounts
        ]
        return (
            f"{len(config.accounts)} account(s) configured:\n" + "\n".join(lines)
        )

    @mcp.tool()
    def list_folders(account: str) -> str:
        """List all mail folders/mailboxes for an account (e.g. INBOX, Sent).

        Args:
            account: Name of a configured account (see `list_accounts`).

        Returns a plain-text list with one folder per line.
        """
        acc = config.get_account(account)
        folders = imap.list_folders(acc)
        return f"{len(folders)} folder(s) for account {account!r}:\n" + _format_folders(folders)

    @mcp.tool()
    def list_messages(
        account: str, folder: str = "INBOX", limit: int = 20, page: int = 0
    ) -> str:
        """List recent messages in a folder, newest first.

        Args:
            account: Name of a configured account.
            folder: Mailbox to read (e.g. "INBOX", "Sent"). Defaults to INBOX.
            limit: Max messages to return (1-200, default 20).
            page: Page of results going backwards (0 = newest window).

        Returns envelopes (uid, subject, from, to, date, flags, size), one per
        message. Use `get_message` with the returned UID to read the body.
        """
        acc = config.get_account(account)
        limit = max(1, min(int(limit), 200))
        page = max(0, int(page))
        messages = imap.list_messages(acc, folder=folder, limit=limit, page=page)
        header = (
            f"Account {account!r}, folder {folder!r}, "
            f"limit {limit}, page {page}: {len(messages)} message(s)"
        )
        return header + "\n\n" + _trim(_format_summaries(messages))

    @mcp.tool()
    def search_messages(
        account: str,
        query: str,
        folder: str = "INBOX",
        criteria: str = "subject",
        limit: int = 50,
    ) -> str:
        """Search messages by a single field and return matching envelopes.

        Args:
            account: Name of a configured account.
            query: Text to search for.
            folder: Mailbox to search in (default INBOX).
            criteria: Field to match: subject, from, sender, to, cc, bcc, body,
                or text. Default "subject".
            limit: Max matches to return (1-200, default 50).

        Returns matching envelopes (uid, subject, from, to, date, flags, size)
        newest-first. Use `get_message` with a returned UID to read a body.
        """
        acc = config.get_account(account)
        limit = max(1, min(int(limit), 200))
        results = imap.search_messages(
            acc, query=query, folder=folder, criteria=criteria, limit=limit
        )
        header = (
            f"Account {account!r}, search {criteria!r}={query!r} in {folder!r}: "
            f"{len(results)} match(es)"
        )
        return header + "\n\n" + _trim(_format_summaries(results))

    @mcp.tool()
    def get_message(
        account: str, uid: int, folder: str = "INBOX", include_html: bool = False
    ) -> str:
        """Fetch and render a full message by its UID.

        Args:
            account: Name of a configured account.
            uid: Message UID returned by `list_messages` / `search_messages`.
            folder: Mailbox containing the message (default INBOX).
            include_html: If true and no text/plain body exists, include a
                tag-stripped rendering of text/html.

        Returns a readable plain-text rendering: headers, body, and a list of
        attachments (filename, type, size). Access is read-only.
        """
        acc = config.get_account(account)
        msg: GetMessage = imap.get_message(acc, uid=int(uid), folder=folder)
        h = msg.headers

        lines: list[str] = []
        lines.append(f"UID: {msg.uid}  Folder: {msg.folder}  Size: {msg.raw_size}B")
        for key, label in (
            ("subject", "Subject"),
            ("from", "From"),
            ("to", "To"),
            ("cc", "Cc"),
            ("date", "Date"),
            ("reply-to", "Reply-To"),
            ("message-id", "Message-ID"),
        ):
            value = h.get(key)
            if value:
                lines.append(f"{label}: {value}")
        lines.append("")

        body = msg.body_text
        if not body and msg.body_html and include_html:
            body = imap._strip_tags(msg.body_html)
        if body:
            lines.append("----- BODY -----")
            lines.append(_trim(body))
        elif msg.body_html:
            lines.append(
                "----- BODY -----\n(No text/plain body; HTML-only message — "
                "call with include_html=true to render an approximate text body.)"
            )
        else:
            lines.append("----- BODY -----\n(no textual body)")

        if msg.attachments:
            lines.append("\n----- ATTACHMENTS -----")
            for i, att in enumerate(msg.attachments, 1):
                lines.append(
                    f"{i}. {att['filename']}  "
                    f"({att['content_type']}, {att['size']}B)"
                )
        return "\n".join(lines)

    return mcp