"""Command-line entry point for the Proton Mail MCP server."""

from __future__ import annotations

import argparse
import sys

from .config import ConfigError, resolve_config_path
from .server import create_server


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="proton-mcp-server",
        description=(
            "MCP server exposing Proton Mail (read-only) through Proton Mail "
            "Bridge IMAP, with multi-account support. Designed for AI agents "
            "such as Hermes over the stdio transport."
        ),
    )
    parser.add_argument(
        "--config",
        "-c",
        default=None,
        help=(
            "Path to the accounts config TOML. Overrides the "
            "PROTON_MCP_CONFIG env var and the default "
            "($XDG_CONFIG_HOME/proton-mcp/config.toml)."
        ),
    )
    parser.add_argument(
        "--transport",
        choices=("stdio",),
        default="stdio",
        help="Transport to use (only 'stdio' is supported). Default: stdio.",
    )
    parser.add_argument(
        "--print-config-path",
        action="store_true",
        help="Print the config file path that would be loaded and exit.",
    )
    parser.add_argument(
        "--list-accounts",
        action="store_true",
        help="Load the config, list configured accounts, and exit "
        "(does not start the server).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.print_config_path:
        print(resolve_config_path(args.config))
        return 0

    # Load configuration once; produce helpful errors before touching stdio.
    try:
        from .config import load_config

        cfg = load_config(args.config)
    except ConfigError as exc:
        print(f"proton-mcp-server: configuration error:\n{exc}", file=sys.stderr)
        return 2

    if args.list_accounts:
        for acc in cfg.accounts:
            print(
                f"{acc.name}\timap://{acc.host}:{acc.port}\t"
                f"user={acc.username}\tsecurity={acc.security}"
            )
        return 0

    mcp = create_server(config_path=args.config)
    mcp.run(transport=args.transport)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())