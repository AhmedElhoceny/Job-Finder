import argparse
import json
import sys
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from config.settings import get_settings
from core.database import JobDatabase
from scrapers.wuzzuf_applier import WuzzufApplier
from scrapers.wuzzuf_scraper import WuzzufScraper

console = Console()


def render_manual_jobs_table(jobs: list[dict], title: str):
    """Renders formatted table of jobs that require manual candidate action."""
    table = Table(title=title, border_style="bold red")
    table.add_column("#", width=3, style="dim")
    table.add_column("Category", style="bold red", width=18)
    table.add_column("Job Title", style="bold yellow", max_width=32)
    table.add_column("Company", style="white", max_width=20)
    table.add_column("Specific Requirement / Reason", style="red", max_width=35)
    table.add_column("Direct Apply Link", style="cyan underline", max_width=45)

    for idx, item in enumerate(jobs, 1):
        cat = item.get("manual_category") or "MANUAL"
        badge = (
            "🔴 Audio Input" if cat == "AUDIO_INPUT"
            else ("🟠 Video Interview" if cat == "VIDEO_INPUT"
            else ("🔵 External ATS" if cat == "EXTERNAL_ATS"
            else "🟡 Assessment"))
        )
        url = item.get("redirect_url") or item.get("url")

        table.add_row(
            str(idx),
            badge,
            item.get("title", ""),
            item.get("company", ""),
            item.get("manual_reason", ""),
            url,
        )
    console.print(table)


def render_auto_eligible_table(jobs: list[dict], title: str):
    """Renders formatted table of jobs eligible for automated application."""
    table = Table(title=title, border_style="bold green")
    table.add_column("#", width=3, style="dim")
    table.add_column("Status", style="bold green", width=14)
    table.add_column("Job Title", style="bold green", max_width=35)
    table.add_column("Company", style="white", max_width=22)
    table.add_column("Process Type", style="cyan", max_width=25)
    table.add_column("URL", style="dim underline", max_width=45)

    for idx, item in enumerate(jobs, 1):
        table.add_row(
            str(idx),
            "✓ Auto-Apply",
            item.get("title", ""),
            item.get("company", ""),
            item.get("action_instructions", ""),
            item.get("url", ""),
        )
    console.print(table)


def main():
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = argparse.ArgumentParser(description="Wuzzuf Automated Job Applier & Manual Requirement Detector")
    parser.add_argument(
        "--url",
        type=str,
        default=None,
        help="Apply or inspect a specific single Wuzzuf job URL",
    )
    parser.add_argument(
        "--keyword",
        type=str,
        default=None,
        help="Live search Wuzzuf for a keyword and process vacancies (e.g. 'Python')",
    )
    parser.add_argument(
        "--max-jobs",
        type=int,
        default=10,
        help="Max number of Wuzzuf jobs to process (default: 10)",
    )
    parser.add_argument(
        "--auto-submit",
        action="store_true",
        help="Actually submit applications for eligible jobs (requires Wuzzuf credentials in .env)",
    )
    parser.add_argument(
        "--manual-out",
        type=str,
        default="data/wuzzuf_manual_applications.json",
        help="Path to save manual applications JSON (default: data/wuzzuf_manual_applications.json)",
    )
    args = parser.parse_args()

    settings = get_settings()
    has_creds = bool(
        settings.wuzzuf_email
        and settings.wuzzuf_password
        and "example.com" not in settings.wuzzuf_email
    )

    masked_email = (
        f"{settings.wuzzuf_email[:3]}***@{settings.wuzzuf_email.split('@')[-1]}"
        if has_creds
        else "[bold yellow]NOT CONFIGURED in .env (Running in Analysis & Detection Mode)[/bold yellow]"
    )

    console.print(
        Panel.fit(
            "[bold cyan]Wuzzuf Job Application Manager[/bold cyan]\n"
            f"Wuzzuf Account: {masked_email}\n"
            f"Execution Mode: {'[bold green]Live Auto-Submit[/bold green]' if args.auto_submit else '[bold cyan]Requirements Inspection & Dry-Run[/bold cyan]'}\n"
            "Non-Automatable Policy: [bold red]Strict Manual Segregation (Audio, Video, External ATS)[/bold red]\n"
            "Audio/Video Policy: [bold yellow]Employer-required voice or video interviews will be listed for manual apply.[/bold yellow]",
            border_style="cyan",
        )
    )

    applier = WuzzufApplier()

    # Attempt login if credentials are set
    if has_creds:
        with console.status("[bold cyan]Connecting and logging in to Wuzzuf...[/bold cyan]"):
            logged_in = applier.login()
        if logged_in:
            console.print("[bold green]✓ Successfully authenticated with Wuzzuf account![/bold green]\n")
        else:
            console.print("[bold yellow]! Wuzzuf login failed. Continuing in requirements analysis mode.[/bold yellow]\n")
    else:
        console.print(
            "[dim yellow]ℹ Set WUZZUF_EMAIL and WUZZUF_PASSWORD in .env to enable direct account application.\n"
            "Proceeding to inspect requirements and detect audio/video/external inputs...[/dim yellow]\n"
        )

    jobs_to_process = []

    # 1. Single URL target
    if args.url:
        jobs_to_process = [{"url": args.url, "title": "Specified Job", "company": "Wuzzuf"}]

    # 2. Live Keyword search
    elif args.keyword:
        console.print(f"[cyan]Scraping live Wuzzuf vacancies for keyword:[/cyan] [bold yellow]{args.keyword}[/bold yellow]...")
        scraper = WuzzufScraper()
        scraped = scraper.scrape_keyword(args.keyword, max_pages=2)
        jobs_to_process = [j.model_dump() for j in scraped[:args.max_jobs]]

    # 3. Pull discovered Wuzzuf jobs from database
    else:
        db = JobDatabase()
        db_jobs = db.get_all_jobs(source="Wuzzuf")
        if not db_jobs:
            console.print("[yellow]No Wuzzuf jobs in database. Scraping latest Python vacancies from Wuzzuf...[/yellow]")
            scraper = WuzzufScraper()
            scraped = scraper.scrape_keyword("Python", max_pages=1)
            jobs_to_process = [j.model_dump() for j in scraped[:args.max_jobs]]
        else:
            console.print(f"[cyan]Loaded [bold green]{len(db_jobs)}[/bold green] Wuzzuf vacancies from database (data/jobs.db)...[/cyan]")
            jobs_to_process = db_jobs[:args.max_jobs]

    if not jobs_to_process:
        console.print("[bold red]No Wuzzuf jobs found to process.[/bold red]")
        sys.exit(0)

    # Process all jobs
    with console.status(f"[bold cyan]Inspecting requirements for {len(jobs_to_process)} Wuzzuf jobs...[/bold cyan]"):
        summary = applier.process_jobs(
            jobs=jobs_to_process,
            auto_submit=args.auto_submit,
            manual_output_json=args.manual_out,
        )

    manual_jobs = summary["manual_jobs"]
    auto_eligible = summary["auto_eligible"]

    # 1. Display Jobs Requiring Manual Application (Audio, Video, External ATS)
    if manual_jobs:
        render_manual_jobs_table(
            manual_jobs,
            f"⚠️ Jobs Requiring MANUAL Application ({len(manual_jobs)} jobs with Audio/Video/External inputs)",
        )
        console.print(
            Panel(
                f"The {len(manual_jobs)} jobs above require inputs that cannot be automated (such as Voice/Audio recording, Video interview, or External ATS).\n\n"
                f"All direct links and exact requirements have been exported to:\n"
                f"📁 [bold cyan]{summary['manual_json_path']}[/bold cyan]\n\n"
                "Please open the provided links in your browser to complete your audio recording or external application manually.",
                title="[bold yellow]Manual Action Required for Candidate[/bold yellow]",
                border_style="yellow",
            )
        )
    else:
        console.print("[bold green]✓ None of the processed jobs required manual audio or video inputs![/bold green]")

    # 2. Display Auto-Eligible Jobs
    if auto_eligible:
        render_auto_eligible_table(
            auto_eligible,
            f"★ Jobs Eligible for Automated Application ({len(auto_eligible)} jobs)",
        )

    # 3. Overall Execution Summary
    console.print(
        f"\n[bold green]✓ Wuzzuf Processing Complete![/bold green]\n"
        f"• Total Processed: [bold cyan]{summary['total_processed']}[/bold cyan]\n"
        f"• 🔴 Requires Manual Apply (Audio/Video/External): [bold red]{summary['manual_count']}[/bold red]\n"
        f"• 🟢 Auto-Apply Eligible: [bold green]{summary['auto_eligible_count']}[/bold green]\n"
        f"• 📁 Manual Jobs Saved To: [bold cyan]{summary['manual_json_path']}[/bold cyan]\n"
        f"• SQLite Database: [bold cyan]data/jobs.db[/bold cyan] (status updated to REQUIRES_MANUAL / ELIGIBLE_AUTO)\n"
    )


if __name__ == "__main__":
    main()
