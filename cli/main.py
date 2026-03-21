"""CLI entry point — open_intern init/start/status/logs/costs."""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

app = typer.Typer(
    name="open_intern",
    help="open_intern — your open-source AI employee",
    no_args_is_help=True,
)
console = Console()


@app.command()
def init(
    config_path: str = typer.Option(
        "config/agent.yaml", "--config", "-c", help="Path to create config file"
    ),
):
    """Initialize a new open_intern agent configuration."""
    target = Path(config_path)
    example = Path("config/agent.example.yaml")

    if target.exists():
        overwrite = typer.confirm(f"{target} already exists. Overwrite?", default=False)
        if not overwrite:
            console.print("[yellow]Aborted.[/yellow]")
            raise typer.Exit()

    if example.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(example, target)
        console.print(f"[green]Config created at {target}[/green]")
    else:
        console.print("[red]Example config not found. Creating default...[/red]")
        target.parent.mkdir(parents=True, exist_ok=True)
        import yaml

        from core.config import AppConfig

        target.write_text(yaml.dump(AppConfig().model_dump(), default_flow_style=False))
        console.print(f"[green]Default config created at {target}[/green]")

    console.print()
    console.print("[bold]Next steps:[/bold]")
    console.print(f"  1. Edit {target} with your credentials")
    console.print("  2. Run: open_intern start")
    console.print()
    console.print("[dim]Required credentials:[/dim]")
    console.print("  - LLM API key (set ANTHROPIC_API_KEY or OPENAI_API_KEY env var)")
    console.print("  - Lark App ID/Secret or Discord Bot Token")


@app.command()
def start(
    config_path: str = typer.Option(
        "config/agent.yaml", "--config", "-c", help="Path to config file"
    ),
    web: bool = typer.Option(
        False, "--web", "-w", help="Run in web-only mode (dashboard on port 8000)"
    ),
):
    """Start the open_intern agent."""
    config_file = Path(config_path)
    if not config_file.exists():
        console.print(f"[red]Config file not found: {config_path}[/red]")
        console.print("Run 'open_intern init' first.")
        raise typer.Exit(1)

    if web:
        # Override platform to web-only mode
        import yaml

        raw = yaml.safe_load(config_file.read_text()) or {}
        raw.setdefault("platform", {})["primary"] = "web"
        config_file.write_text(
            yaml.dump(raw, default_flow_style=False, sort_keys=False, allow_unicode=True)
        )

    console.print(
        Panel.fit(
            "[bold green]Starting open_intern[/bold green]",
            subtitle="Dashboard: localhost:3000 | API: localhost:8000 | Ctrl+C to stop",
        )
    )

    from server import run_agent

    try:
        asyncio.run(run_agent(config_path))
    except KeyboardInterrupt:
        console.print("\n[yellow]Shutting down...[/yellow]")


@app.command()
def status(
    config_path: str = typer.Option(
        "config/agent.yaml", "--config", "-c", help="Path to config file"
    ),
):
    """Show agent status and memory statistics."""
    from core.config import load_config

    config_file = Path(config_path)
    if not config_file.exists():
        console.print(f"[red]Config not found: {config_path}[/red]")
        raise typer.Exit(1)

    config = load_config(config_path)

    table = Table(title=f"open_intern — {config.identity.name}")
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="white")

    table.add_row("Name", config.identity.name)
    table.add_row("Role", config.identity.role)
    table.add_row("Platform", config.active_platform)
    table.add_row("LLM", f"{config.llm.provider}:{config.llm.model}")
    table.add_row("Daily Budget", f"${config.llm.daily_cost_budget_usd:.2f}")
    table.add_row("Proactivity", "Enabled" if config.behavior.proactivity.enabled else "Disabled")
    db_url = config.database_url
    db_display = db_url.split("@")[-1] if "@" in db_url else db_url
    table.add_row("Database", db_display)

    console.print(table)

    # Try to connect to memory store and show stats
    try:
        from memory.store import MemoryScope, MemoryStore

        store = MemoryStore(config.database_url)
        mem_table = Table(title="Memory Statistics")
        mem_table.add_column("Scope", style="cyan")
        mem_table.add_column("Count", style="green")
        mem_table.add_row("Shared", str(store.count(MemoryScope.SHARED)))
        mem_table.add_row("Channel", str(store.count(MemoryScope.CHANNEL)))
        mem_table.add_row("Personal", str(store.count(MemoryScope.PERSONAL)))
        mem_table.add_row("Total", str(store.count()))
        console.print(mem_table)
    except Exception as e:
        console.print(f"[yellow]Could not connect to memory store: {e}[/yellow]")


@app.command()
def logs(
    lines: int = typer.Option(20, "--lines", "-n", help="Number of audit log lines"),
):
    """Show recent audit logs."""
    audit_file = Path("logs/audit.jsonl")
    if not audit_file.exists():
        console.print("[yellow]No audit logs found yet.[/yellow]")
        raise typer.Exit()

    import json

    all_lines = audit_file.read_text().strip().split("\n")
    recent = all_lines[-lines:]

    table = Table(title="Recent Audit Log")
    table.add_column("Time", style="dim")
    table.add_column("Action", style="cyan")
    table.add_column("Level", style="yellow")
    table.add_column("Verdict", style="green")
    table.add_column("Description")

    for line in recent:
        try:
            entry = json.loads(line)
            ts = entry.get("timestamp", "")[:19]
            table.add_row(
                ts,
                entry.get("action_type", ""),
                entry.get("action_level", ""),
                entry.get("verdict", ""),
                entry.get("description", ""),
            )
        except json.JSONDecodeError:
            continue

    console.print(table)


@app.command()
def chat(
    config_path: str = typer.Option(
        "config/agent.yaml", "--config", "-c", help="Path to config file"
    ),
):
    """Interactive chat with the agent (no platform needed)."""
    from core.agent import OpenInternAgent
    from core.config import load_config

    config = load_config(config_path)
    console.print(
        Panel.fit(
            f"[bold]Chatting with {config.identity.name}[/bold]\nType 'quit' to exit",
        )
    )

    agent = OpenInternAgent(config)
    agent.initialize()

    import asyncio

    while True:
        try:
            user_input = console.input("[bold cyan]You:[/bold cyan] ")
        except (EOFError, KeyboardInterrupt):
            break

        if user_input.strip().lower() in ("quit", "exit", "q"):
            break

        response = asyncio.run(
            agent.chat(
                user_input,
                context={
                    "platform": "cli",
                    "channel_id": "cli",
                    "user_name": "user",
                    "is_dm": True,
                },
            )
        )

        console.print(f"[bold green]{config.identity.name}:[/bold green] {response}")
        console.print()


if __name__ == "__main__":
    app()
