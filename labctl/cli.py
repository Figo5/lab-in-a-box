"""labctl — Lab-in-a-Box command line.

Pipeline:  labctl up -> labctl set-level -> labctl seed -> labctl run-brute
           -> labctl report -> labctl down
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import click

from . import brute as brute_mod
from . import compose
from . import config as cfg_mod
from . import report as report_mod
from . import security_level
from . import seed as seed_mod
from .report import mask


@click.group()
@click.pass_context
def cli(ctx):
    """labctl — spin up and manage your local authorized security lab."""
    ctx.ensure_object(dict)
    ctx.obj["config"] = cfg_mod.load()


def main() -> None:
    try:
        cli(prog_name="labctl")
    except cfg_mod.ConfigError as e:
        raise click.ClickException(str(e)) from e


# --- run-dir helpers --------------------------------------------------------
def _new_run_dir() -> Path:
    ts = time.strftime("%Y%m%d-%H%M%S")
    d = cfg_mod.PROJECT_ROOT / "runs" / ts
    d.mkdir(parents=True, exist_ok=True)
    return d


def _latest_run_dir() -> Path | None:
    runs = cfg_mod.PROJECT_ROOT / "runs"
    if not runs.exists():
        return None
    dirs = sorted(d for d in runs.iterdir() if d.is_dir())
    return dirs[-1] if dirs else None


def _active_run_dir(ctx) -> Path:
    d = ctx.obj.get("run_dir")
    if d and Path(d).exists():
        return Path(d)
    latest = _latest_run_dir()
    return latest if latest else _new_run_dir()


def _write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2, default=str))


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


# --- commands ---------------------------------------------------------------
@cli.command()
@click.pass_context
def up(ctx):
    """Bring the lab up and wait until every target is healthy and reachable."""
    cfg = ctx.obj["config"]
    click.echo("Starting lab (docker compose up -d)...")
    compose.up()
    run_dir = _new_run_dir()
    ctx.obj["run_dir"] = str(run_dir)
    _write_json(run_dir / "meta.json", {
        "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "network": cfg.network,
        "targets": {name: {"port": t.port} for name, t in cfg.targets.items()},
    })
    click.echo("Waiting for healthchecks (first boot pulls images and can take a minute)...")
    statuses = compose.wait_until_ready(cfg)
    _print_status(cfg, statuses)
    ready = all(
        statuses.get(t.name, {}).get("health") == "healthy"
        and compose.reachable(t.host, t.port)
        for t in cfg.targets.values()
    )
    if not ready:
        click.secho("\nSome targets are not ready yet — run `labctl status` to re-check.", fg="yellow")
        raise SystemExit(1)
    click.echo(f"\nAll targets ready. Run dir: runs/{run_dir.name}")


@cli.command()
@click.option("--purge", is_flag=True, help="Also remove named volumes (seeded data).")
def down(purge):
    """Tear the lab down. --purge also wipes seeded-data volumes."""
    compose.down(purge=purge)
    click.echo("Lab stopped." + (" Volumes purged." if purge else ""))


@cli.command()
@click.pass_context
def status(ctx):
    """Show per-target Docker health and host reachability."""
    _print_status(ctx.obj["config"], compose.ps())


@cli.command()
@click.argument("target")
@click.argument("level", type=click.Choice(cfg_mod.SECURITY_LEVELS))
@click.pass_context
def set_level(ctx, target, level):
    """Apply a security level (low/medium/high/impossible) to a target."""
    cfg = ctx.obj["config"]
    cfg.get(target)  # validates the target name
    result = security_level.apply(cfg, target, level)
    if not result["ok"]:
        click.secho(f"{target}: {result['reason']}", fg="yellow")
        return
    click.secho(f"{target}: security level set to {level}", fg="green")
    run_dir = _active_run_dir(ctx)
    levels = _read_json(run_dir / "levels.json")
    levels[target] = {"level": level, "at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    _write_json(run_dir / "levels.json", levels)


@cli.command()
@click.pass_context
def seed(ctx):
    """Idempotently create the placeholder accounts from lab.yaml."""
    cfg = ctx.obj["config"]
    run_dir = _active_run_dir(ctx)
    results = seed_mod.seed_all(cfg)
    _write_json(run_dir / "seeds.json", results)
    rows = [("Target", "Username", "Status", "Detail")]
    for name, r in results.items():
        rows.append((name, r.get("user", "-"), r.get("status", "?"), r.get("detail", "")))
    _table(rows)


@cli.command()
@click.option("--target", required=True, help="Target name from lab.yaml (e.g. ssh-lab).")
@click.option("--wordlist", default=None, help="Override the wordlist (default: lab.yaml).")
@click.option("--timeout", default=600, show_default=True, help="Max seconds for the real tool run (mock ignores it).")
@click.pass_context
def run_brute(ctx, target, wordlist, timeout):
    """Run the brute-forcer against a target.

    Uses the real tool when lab.yaml `brute.tool` is set; otherwise a
    deterministic mock runs so the pipeline works end-to-end.
    """
    cfg = ctx.obj["config"]
    cfg.get(target)  # validates the target name
    wl = cfg.resolve_wordlist(wordlist)
    if not wl.exists():
        raise click.ClickException(f"wordlist not found: {wl}")
    run_dir = _active_run_dir(ctx)
    real = bool(cfg.brute.tool)
    click.echo(f"Running brute-force against {target} ({'real tool' if real else 'mock'})...")
    result = brute_mod.run(cfg, target, wl, cfg.resolve_usernames(), timeout=timeout)
    out = run_dir / f"{target}-brute.json"
    _write_json(out, result)
    click.echo(f"attempts={result['attempts']}  successes={len(result['successes'])}")
    for s in result["successes"]:
        click.secho(f"  [+] {s['username']}:{mask(s['password'])}", fg="green")
    if result["mock"]:
        click.echo("  (mock — set brute.tool in lab.yaml to run your real brute-forcer)")
    click.echo(f"results -> runs/{run_dir.name}/{out.name}")


@cli.command()
@click.option("--run", default=None, help="Run timestamp dir under runs/ (default: latest).")
@click.option("--html", is_flag=True, help="Also write a self-contained report.html.")
@click.pass_context
def report(ctx, run, html):
    """Aggregate a run dir into report.md (+ optional report.html)."""
    cfg = ctx.obj["config"]
    run_dir = Path(cfg_mod.PROJECT_ROOT / "runs" / run) if run else _latest_run_dir()
    if not run_dir or not run_dir.exists():
        raise click.ClickException("no run to report — run `labctl up` first")
    path = report_mod.render(cfg, run_dir, html=html)
    click.echo(f"Report written: {path}")
    if html:
        click.echo(f"HTML written:   {run_dir / 'report.html'}")


# --- output helpers ---------------------------------------------------------
def _print_status(cfg, statuses):
    rows = [("Target", "Port", "Docker", "Reachable")]
    for t in cfg.targets.values():
        info = statuses.get(t.name, {})
        state = info.get("health") or info.get("state") or "down"
        rows.append((
            t.name,
            str(t.port),
            state,
            "yes" if compose.reachable(t.host, t.port) else "no",
        ))
    _table(rows)


def _table(rows):
    widths = [max(len(str(r[i])) for r in rows) for i in range(len(rows[0]))]
    for row in rows:
        click.echo("  ".join(str(c).ljust(widths[i]) for i, c in enumerate(row)).rstrip())
