"""Configuration: load and validate multi-account Proton Mail Bridge settings.

Accounts are declared in a TOML file, by default::

    $XDG_CONFIG_HOME/proton-mcp/config.toml    (i.e. ~/.config/proton-mcp/config.toml)

The path can be overridden with the ``PROTON_MCP_CONFIG`` environment variable or
the ``--config`` CLI flag (flag takes precedence over env, env over default).

Example::

    [[accounts]]
    name = "personal"
    username = "me@proton.me"
    password = "bridge-generated-password"   # from Proton Mail Bridge, not your Proton password

    [[accounts]]
    name = "work"
    username = "work@proton.me"
    password = "another-bridge-password"
    host = "127.0.0.1"      # optional, defaults to 127.0.0.1
    port = 1143            # optional, defaults to 1143 (Proton Bridge IMAP)
    security = "starttls"  # optional: "starttls" (default) | "ssl" | "plain"
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


class ConfigError(Exception):
    """Raised when the configuration file is missing, unreadable, or invalid."""


@dataclass
class Account:
    """A single Proton Mail account reachable through the local Bridge IMAP."""

    name: str
    username: str
    password: str
    host: str = "127.0.0.1"
    port: int = 1143
    security: str = "starttls"


@dataclass
class Config:
    """Resolved configuration containing all declared accounts."""

    accounts: list[Account] = field(default_factory=list)

    def get_account(self, name: str) -> Account:
        """Return the account with ``name`` or raise :class:`ConfigError`."""
        for account in self.accounts:
            if account.name == name:
                return account
        available = ", ".join(a.name for a in self.accounts) or "<none>"
        raise ConfigError(
            f"No account named {name!r}. Available accounts: {available}"
        )


def default_config_path() -> Path:
    """Return the default config file location (XDG-aware)."""
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg and Path(xdg).is_absolute() else Path.home() / ".config"
    return base / "proton-mcp" / "config.toml"


def resolve_config_path(explicit: str | os.PathLike[str] | None) -> Path:
    """Resolve which config file to load, honoring env + explicit override."""
    if explicit:
        return Path(explicit).expanduser()
    env = os.environ.get("PROTON_MCP_CONFIG")
    if env:
        return Path(env).expanduser()
    return default_config_path()


def load_config(explicit_path: str | os.PathLike[str] | None = None) -> Config:
    """Load and validate the configuration from TOML.

    Raises :class:`ConfigError` with a human-friendly message on any problem.
    """
    path = resolve_config_path(explicit_path)
    if not path.exists():
        raise ConfigError(
            f"Configuration file not found: {path}\n"
            f"Create it with your Proton Mail Bridge accounts, e.g.:\n\n"
            f"  [[accounts]]\n"
            f"  name = \"personal\"\n"
            f'  username = "me@proton.me"\n'
            f'  password = "<bridge-password>"\n'
        )

    try:
        with path.open("rb") as fh:
            data = tomllib.load(fh)
    except tomllib.TOMLError as exc:
        raise ConfigError(f"Invalid TOML in {path}: {exc}") from exc
    except OSError as exc:
        raise ConfigError(f"Could not read {path}: {exc}") from exc

    raw_accounts = data.get("accounts", [])
    if not isinstance(raw_accounts, list):
        raise ConfigError(f"{path}: 'accounts' must be a list of tables")

    accounts: list[Account] = []
    seen: set[str] = set()
    for index, entry in enumerate(raw_accounts):
        if not isinstance(entry, dict):
            raise ConfigError(
                f"{path}: accounts[{index}] must be a table, got {type(entry).__name__}"
            )
        for required in ("name", "username", "password"):
            if not entry.get(required):
                raise ConfigError(
                    f"{path}: accounts[{index}] is missing required field "
                    f"{required!r}"
                )
        name = str(entry["name"]).strip()
        if not name:
            raise ConfigError(f"{path}: accounts[{index}]: 'name' must not be empty")
        if name in seen:
            raise ConfigError(
                f"{path}: duplicate account name {name!r} — "
                f"account names must be unique"
            )
        seen.add(name)

        security = _resolve_security(entry, path, index)
        accounts.append(
            Account(
                name=name,
                username=str(entry["username"]),
                password=str(entry["password"]),
                host=str(entry.get("host", "127.0.0.1")),
                port=int(entry.get("port", 1143)),
                security=security,
            )
        )

    if not accounts:
        raise ConfigError(
            f"{path}: no accounts declared. Add at least one [[accounts]] table."
        )

    return Config(accounts=accounts)


_VALID_SECURITY = ("starttls", "ssl", "plain")


def _resolve_security(entry: dict, path: Path, index: int) -> str:
    """Resolve the `security` field, honoring the legacy `use_ssl` boolean."""
    if "security" in entry:
        value = str(entry["security"]).strip().lower()
        if value not in _VALID_SECURITY:
            raise ConfigError(
                f"{path}: accounts[{index}]: invalid security={value!r}. "
                f"Valid: {', '.join(_VALID_SECURITY)}"
            )
        return value
    if "use_ssl" in entry:
        return "ssl" if bool(entry["use_ssl"]) else "plain"
    return "starttls"