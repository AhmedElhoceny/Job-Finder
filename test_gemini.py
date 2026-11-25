import sys
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from pydantic import BaseModel, Field

from config.settings import get_settings
from core.gemini_client import GeminiClient

console = Console()


class JobSnippetEvaluation(BaseModel):
    title: str = Field(description="Normalized job title")
    primary_tech: list[str] = Field(description="Top 3 primary technologies required")
    remote_friendly: bool = Field(description="Whether the job allows remote work")
    seniority: str = Field(description="Seniority level e.g. Junior, Mid, Senior, Lead")
    summary: str = Field(description="One-sentence overview of the role")


def main():
    console.print(
        Panel.fit(
            "[bold cyan]Job Finder Agent - Phase 1 Verification[/bold cyan]\n"
            "Testing Environment, Configuration, and Gemini Free LLM Integration",
            border_style="cyan",
        )
    )

    settings = get_settings()

    # 1. Configuration Check
    config_table = Table(title="Loaded Settings")
    config_table.add_column("Setting", style="bold")
    config_table.add_column("Value")

    config_table.add_row("Base Dir", str(settings.base_dir))
    config_table.add_row("Gemini Model (Primary)", settings.gemini_model)
    config_table.add_row("Gemini Model (Fallback)", settings.gemini_fallback_model)
    config_table.add_row("Max RPM (Rate Limit)", str(settings.gemini_max_rpm))
    config_table.add_row("Delay Between Calls", f"{settings.gemini_request_delay_seconds}s")
    config_table.add_row("Database Path", str(settings.absolute_db_path))

    masked_key = (
        f"{settings.gemini_api_key[:6]}...{settings.gemini_api_key[-4:]}"
        if len(settings.gemini_api_key) > 10
        else ("[red]NOT CONFIGURED[/red]" if not settings.gemini_api_key else "[yellow]PLACEHOLDER[/yellow]")
    )
    config_table.add_row("API Key Status", masked_key)
    console.print(config_table)

    client = GeminiClient(settings)

    if not client.is_configured:
        console.print(
            Panel(
                "[bold yellow]Next Step to Complete Verification:[/bold yellow]\n\n"
                "1. Go to Google AI Studio to get your [bold green]Free API Key[/bold green]:\n"
                "   [link=https://aistudio.google.com/app/apikey]https://aistudio.google.com/app/apikey[/link]\n\n"
                "2. Open the [bold cyan].env[/bold cyan] file in this directory:\n"
                "   Set [bold green]GEMINI_API_KEY=your_actual_api_key[/bold green]\n\n"
                "3. Re-run this test:\n"
                "   [bold white].venv\\Scripts\\python.exe test_gemini.py[/bold white]",
                title="[yellow]Gemini API Key Required[/yellow]",
                border_style="yellow",
            )
        )
        sys.exit(0)

    # 2. Live API Test
    console.print("\n[bold green]Connecting to Gemini Free API...[/bold green]")

    with console.status("[bold cyan]Testing text generation...[/bold cyan]"):
        text_resp = client.generate_text(
            prompt="Reply with a short one-sentence motivational quote for a software developer searching for jobs.",
            temperature=0.7,
        )
    console.print(f"[bold]Text Output:[/bold] {text_resp.strip()}")

    # 3. Live Structured Output Test
    sample_job = """
    Senior Python Backend Engineer at FinTech Innovations
    Location: Remote (US / EMEA)
    We are looking for a Senior Engineer with 5+ years experience in Python, FastAPI, and PostgreSQL.
    Experience with Docker and Kubernetes is a plus.
    """

    with console.status("[bold cyan]Testing structured JSON schema parsing...[/bold cyan]"):
        structured_resp: JobSnippetEvaluation = client.generate_structured(
            prompt=f"Analyze this job snippet and extract structured fields:\n\n{sample_job}",
            schema=JobSnippetEvaluation,
            temperature=0.1,
        )

    eval_table = Table(title="Structured Output Extraction Test")
    eval_table.add_column("Field", style="bold cyan")
    eval_table.add_column("Value", style="green")

    eval_table.add_row("Job Title", structured_resp.title)
    eval_table.add_row("Seniority", structured_resp.seniority)
    eval_table.add_row("Remote Friendly", str(structured_resp.remote_friendly))
    eval_table.add_row("Primary Tech Stack", ", ".join(structured_resp.primary_tech))
    eval_table.add_row("Summary", structured_resp.summary)
    console.print(eval_table)

    # 4. Usage Statistics
    usage_table = Table(title="Token & Request Usage")
    usage_table.add_column("Metric", style="bold")
    usage_table.add_column("Count")
    usage_table.add_row("Total Calls", str(client.usage.total_calls))
    usage_table.add_row("Successful Calls", str(client.usage.successful_calls))
    usage_table.add_row("Prompt Tokens", str(client.usage.total_prompt_tokens))
    usage_table.add_row("Candidate Tokens", str(client.usage.total_candidates_tokens))
    console.print(usage_table)

    console.print("\n[bold green][PASSED] Phase 1 Gemini Integration Test Succeeded![/bold green]\n")


if __name__ == "__main__":
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    main()
