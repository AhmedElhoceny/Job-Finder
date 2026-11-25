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
from scrapers.linkedin_scraper import LinkedInScraper

console = Console()


def render_jobs_table(jobs: list, title: str):
    """Renders a formatted Rich table of discovered LinkedIn items."""
    table = Table(title=title, border_style="bold green")
    table.add_column("#", width=3, style="dim")
    table.add_column("Type", style="magenta", width=14)
    table.add_column("Title / Role", style="bold green", max_width=32)
    table.add_column("Company / Author", style="white", max_width=24)
    table.add_column("Location", style="cyan", max_width=22)
    table.add_column("Posted", style="yellow", width=12)
    table.add_column("URL", style="dim underline", max_width=45)

    for idx, item in enumerate(jobs, 1):
        table.add_row(
            str(idx),
            item.source,
            item.title,
            item.company,
            item.location,
            item.date_posted or "Recent",
            item.url,
        )
    console.print(table)


def main():
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = argparse.ArgumentParser(description="Standalone LinkedIn Scraper Tester (Jobs & Hiring Posts)")
    parser.add_argument(
        "--keywords",
        type=str,
        nargs="+",
        default=["Python Developer", "FastAPI"],
        help="Search keywords or roles (default: 'Python Developer' 'FastAPI')",
    )
    parser.add_argument(
        "--location",
        type=str,
        default="Worldwide",
        help="Target location for formal job listings (default: 'Worldwide')",
    )
    parser.add_argument(
        "--max-days",
        type=int,
        default=30,
        help="Strict date limitation in days (default: 30). Collects ALL items posted <= max-days.",
    )
    parser.add_argument(
        "--max-jobs",
        type=int,
        default=None,
        help="Optional upper bound on formal jobs (default: None = unlimited within date window)",
    )
    parser.add_argument(
        "--max-posts",
        type=int,
        default=None,
        help="Optional upper bound on hiring posts (default: None = unlimited within date window)",
    )
    parser.add_argument(
        "--jobs-only",
        action="store_true",
        help="Only test LinkedIn Jobs scraper",
    )
    parser.add_argument(
        "--posts-only",
        action="store_true",
        help="Only test LinkedIn Posts scraper",
    )
    parser.add_argument(
        "--output",
        "--out",
        type=str,
        default="data/linkedin_results.json",
        help="Path to output JSON file (default: data/linkedin_results.json)",
    )
    parser.add_argument(
        "--no-db",
        action="store_true",
        help="Skip inserting discovered LinkedIn items into SQLite database (data/jobs.db)",
    )
    parser.add_argument(
        "--no-merge",
        action="store_true",
        help="Skip merging discovered LinkedIn items into cumulative data/discovered_jobs.json",
    )
    args = parser.parse_args()

    settings = get_settings()
    has_li_at = bool(settings.linkedin_li_at)

    auth_mode_badge = (
        "[bold green]✓ Authenticated Mode (li_at detected)[/bold green]"
        if has_li_at
        else "[bold yellow]✓ Zero-Account Public Mode (No Login Required)[/bold yellow]"
    )

    cap_desc = (
        "[bold green]No Count Limits (Collect ALL fresh matching items)[/bold green]"
        if args.max_jobs is None and args.max_posts is None
        else f"[yellow]Optional count cap: jobs={args.max_jobs}, posts={args.max_posts}[/yellow]"
    )

    console.print(
        Panel.fit(
            "[bold cyan]LinkedIn Scraper Standalone Verification[/bold cyan]\n"
            f"Mode: {auth_mode_badge}\n"
            f"Target Keywords: [bold green]{', '.join(args.keywords)}[/bold green]\n"
            f"Target Location: [bold cyan]{args.location}[/bold cyan]\n"
            f"Limitation Rule: [bold yellow]Strictly <= {args.max_days} Days Old (Date-Based Window)[/bold yellow]\n"
            f"Count Restriction: {cap_desc}\n\n"
            "[dim]Paginates and collects all jobs and recruiter hiring posts within the 30-day window.[/dim]",
            border_style="cyan",
        )
    )

    scraper = LinkedInScraper(request_delay=1.2)
    all_jobs = []
    all_posts = []

    # 1. Test LinkedIn Jobs Scraper
    if not args.posts_only:
        with console.status(f"[bold cyan]Scraping LinkedIn Jobs (<= {args.max_days} days) for {args.keywords[:2]} ({args.location})...[/bold cyan]"):
            all_jobs = scraper.scrape_jobs(
                keywords=args.keywords[:2],
                locations=[args.location],
                max_days=args.max_days,
                max_jobs=args.max_jobs,
            )

        if all_jobs:
            render_jobs_table(all_jobs, f"★ Discovered LinkedIn Jobs ({len(all_jobs)} vacancies within <= {args.max_days} days)")
        else:
            console.print("[yellow]No formal LinkedIn jobs matched the criteria within the date window.[/yellow]")

    # 2. Test LinkedIn Hiring Posts Scraper
    if not args.jobs_only:
        with console.status(f"[bold cyan]Scraping LinkedIn Hiring Posts (<= {args.max_days} days) for {args.keywords[:2]}...[/bold cyan]"):
            all_posts = scraper.scrape_posts(
                keywords=args.keywords[:2],
                max_days=args.max_days,
                max_posts=args.max_posts,
            )

        if all_posts:
            render_jobs_table(all_posts, f"★ Discovered LinkedIn Hiring Posts ({len(all_posts)} posts within <= {args.max_days} days)")
        else:
            console.print("[yellow]No LinkedIn hiring posts matched the criteria within the date window.[/yellow]")

    # 3. Save Scraped Items to JSON & Database
    all_items = all_jobs + all_posts
    serialized_results = [item.model_dump() for item in all_items]

    # Save to standalone LinkedIn JSON
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(serialized_results, indent=2, ensure_ascii=False), encoding="utf-8")

    # Save to SQLite Database (jobs.db)
    db = JobDatabase()
    new_db_count = 0
    total_db_count = 0
    if not args.no_db:
        new_db_count = db.save_jobs(all_items)
        total_db_count = len(db.get_all_jobs())

    # Merge into cumulative discovered_jobs.json alongside all other resources
    merged_count = 0
    total_discovered = 0
    if not args.no_merge:
        discovered_path = Path("data/discovered_jobs.json")
        existing_by_url: dict[str, dict] = {}

        # 1. Load existing from discovered_jobs.json if present and valid
        if discovered_path.exists():
            try:
                content = discovered_path.read_text(encoding="utf-8").strip()
                if content:
                    old = json.loads(content)
                    if isinstance(old, list):
                        for it in old:
                            if isinstance(it, dict) and "url" in it:
                                existing_by_url[it["url"]] = it
            except Exception:
                pass

        # 2. If discovered_jobs.json was empty, seed with all existing jobs from DB
        if not existing_by_url:
            for it in db.get_all_jobs():
                if "url" in it:
                    existing_by_url[it["url"]] = it

        # 3. Merge new LinkedIn items
        for it in serialized_results:
            u = it.get("url")
            if u:
                if u not in existing_by_url:
                    merged_count += 1
                existing_by_url[u] = it

        discovered_path.write_text(
            json.dumps(list(existing_by_url.values()), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        total_discovered = len(existing_by_url)

    # 4. Overall Summary
    total_count = len(all_items)
    db_info = f"\n• SQLite Database (data/jobs.db): [bold green]+{new_db_count} new records[/bold green] ({total_db_count} total stored across all resources)" if not args.no_db else ""
    merge_info = f"\n• Cumulative Feed (data/discovered_jobs.json): [bold yellow]+{merged_count} new[/bold yellow] ({total_discovered} total merged across all platforms)" if not args.no_merge else ""

    console.print(
        f"\n[bold green]✓ LinkedIn Verification Complete![/bold green]\n"
        f"• Total Opportunities Found: [bold cyan]{total_count}[/bold cyan] "
        f"([green]{len(all_jobs)} formal listings[/green], [yellow]{len(all_posts)} recruiter hiring posts[/yellow])\n"
        f"• Filter Applied: [bold green]Strictly <= {args.max_days} days old (Date limitation, no count limits)[/bold green]\n"
        f"• Standalone LinkedIn JSON: [bold cyan]{output_path}[/bold cyan] ([bold green]{len(serialized_results)}[/bold green] items written)"
        f"{db_info}"
        f"{merge_info}\n"
        f"• Account Required: [bold green]No (100% public, bypasses auth walls)[/bold green]\n"
    )


if __name__ == "__main__":
    main()
