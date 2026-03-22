"""CLI entry point — open_intern init/start/status/logs/costs."""

from __future__ import annotations

import asyncio
import json
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
def init():
    """Initialize environment. Checks .env exists with required variables."""
    env_file = Path(".env")
    if env_file.exists():
        console.print("[green].env file already exists.[/green]")
    else:
        example = Path(".env.example")
        if example.exists():
            import shutil

            shutil.copy(example, env_file)
            console.print("[green].env created from .env.example[/green]")
        else:
            console.print("[red].env.example not found. Create a .env file manually.[/red]")
            raise typer.Exit(1)

    console.print()
    console.print("[bold]Next steps:[/bold]")
    console.print("  1. Edit .env with your DATABASE_URL and ENCRYPTION_KEY")
    console.print("  2. Run: alembic upgrade head")
    console.print("  3. Run: open_intern start")
    console.print()
    console.print("[dim]Generate an encryption key with:[/dim]")
    console.print(
        "  python -c 'from cryptography.fernet "
        "import Fernet; print(Fernet.generate_key().decode())'"
    )


@app.command()
def start(
    platform: str = typer.Option(
        "web", "--platform", "-p", help="Platform to run: web|telegram|discord|lark"
    ),
):
    """Start the open_intern agent."""
    console.print(
        Panel.fit(
            f"[bold green]Starting open_intern[/bold green] (platform: {platform})",
            subtitle="Dashboard: localhost:3000 | API: localhost:8000 | Ctrl+C to stop",
        )
    )

    from server import run_agent

    try:
        asyncio.run(run_agent(platform))
    except KeyboardInterrupt:
        console.print("\n[yellow]Shutting down...[/yellow]")


@app.command()
def status():
    """Show agent status and memory statistics."""
    from core.config import get_config

    config = get_config()

    table = Table(title="open_intern — Status")
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="white")

    db_url = config.database_url
    db_display = db_url.split("@")[-1] if "@" in db_url else db_url
    table.add_row("Database", db_display)
    table.add_row("Port", str(config.port))
    table.add_row("Encryption Key", "set" if config.encryption_key else "[red]NOT SET[/red]")
    table.add_row("E2B API Key", "set" if config.e2b_api_key else "not set")

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
def chat():
    """Interactive chat with the default agent (no platform needed)."""
    from core.agent import OpenInternAgent
    from core.config import get_config

    config = get_config()
    console.print(
        Panel.fit(
            f"[bold]Chatting with {config.identity.name}[/bold]\nType 'quit' to exit",
        )
    )

    agent = OpenInternAgent(config)
    agent.initialize()

    while True:
        try:
            user_input = console.input("[bold cyan]You:[/bold cyan] ")
        except (EOFError, KeyboardInterrupt):
            break

        if user_input.strip().lower() in ("quit", "exit", "q"):
            break

        response, _token_usage = asyncio.run(
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
