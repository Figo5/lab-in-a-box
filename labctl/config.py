"""Load and validate lab.yaml into typed config objects."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Default published host ports, mirroring docker-compose.yml.
TARGET_PORTS: dict = {
    "dvwa": 8081,
    "ssh-lab": 2222,
    "juice-shop": 8082,
    "vuln-api": 8083,
}

SECURITY_LEVELS = ("low", "medium", "high", "impossible")


class ConfigError(Exception):
    pass


@dataclasses.dataclass
class Target:
    name: str
    security_level: str | None = None
    seed_user: str | None = None
    seed_pass: str | None = None
    port: int = 0
    # Per-target brute tool: overrides the global `brute.tool`. `tool_args`
    # are appended to the tool command line (e.g. HTTP login path/field names).
    tool: str | None = None
    tool_args: list | None = None

    @property
    def host(self) -> str:
        return "127.0.0.1"


@dataclasses.dataclass
class BruteConfig:
    default_wordlist: str = "./wordlists/common.txt"
    tool: str | None = None
    usernames: str = "./wordlists/usernames.txt"
    python: str | None = None


@dataclasses.dataclass
class LabConfig:
    network: str = "labnet"
    targets: dict = dataclasses.field(default_factory=dict)
    brute: BruteConfig = dataclasses.field(default_factory=BruteConfig)
    boot_timeout_seconds: int = 300

    def resolve_wordlist(self, path: str | None = None) -> Path:
        p = Path(path) if path else Path(self.brute.default_wordlist)
        if not p.is_absolute():
            p = PROJECT_ROOT / p
        return p

    def resolve_usernames(self) -> Path:
        p = Path(self.brute.usernames)
        if not p.is_absolute():
            p = PROJECT_ROOT / p
        return p

    def get(self, name: str) -> Target:
        if name not in self.targets:
            raise ConfigError(
                f"unknown target {name!r} (known: {', '.join(sorted(self.targets))})"
            )
        return self.targets[name]


def load(path: str | Path | None = None) -> LabConfig:
    path = Path(path) if path else PROJECT_ROOT / "lab.yaml"
    if not path.exists():
        raise ConfigError(f"config not found: {path} (run from the project root)")
    raw = yaml.safe_load(path.read_text()) or {}
    return _parse(raw)


def _parse(raw: dict) -> LabConfig:
    cfg = LabConfig(network=str(raw.get("network") or "labnet"))

    targets = raw.get("targets") or {}
    if not isinstance(targets, dict):
        raise ConfigError("'targets' must be a mapping")
    for name, spec in targets.items():
        spec = spec or {}
        if not isinstance(spec, dict):
            raise ConfigError(f"target {name!r}: config must be a mapping")
        level = spec.get("security_level")
        if level is not None and level not in SECURITY_LEVELS:
            raise ConfigError(
                f"target {name!r}: invalid security_level {level!r} "
                f"(choose from {', '.join(SECURITY_LEVELS)})"
            )
        cfg.targets[name] = Target(
            name=name,
            security_level=level,
            seed_user=spec.get("seed_user"),
            seed_pass=spec.get("seed_pass"),
            port=int(spec.get("port") or TARGET_PORTS.get(name, 0)),
            tool=spec.get("tool"),
            tool_args=spec.get("tool_args"),
        )

    brute = raw.get("brute") or {}
    cfg.brute = BruteConfig(
        default_wordlist=brute.get("default_wordlist", "./wordlists/common.txt"),
        tool=brute.get("tool"),
        usernames=brute.get("usernames", "./wordlists/usernames.txt"),
        python=brute.get("python"),
    )

    if raw.get("boot_timeout_seconds") is not None:
        cfg.boot_timeout_seconds = int(raw["boot_timeout_seconds"])

    if cfg.network != "labnet" and cfg.network not in ("labnet",):
        # Custom networks are allowed (e.g. for a named Docker network), but the
        # compose file hardcodes the network; changing it here has no effect
        # until docker-compose.yml is edited too.
        pass

    if not cfg.targets:
        raise ConfigError("no targets defined in lab.yaml")

    return cfg
