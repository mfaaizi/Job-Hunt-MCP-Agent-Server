"""
job-agent MCP server
Entry point. Run with: python -m server.main
"""
from server.app import mcp
from server.config import settings
from server.db.session import init_db

# Ensure SQLite tables exist before any tool runs
init_db()


@mcp.tool()
def ping() -> str:
    """Health check tool — confirms the MCP server is running and reachable."""
    return "job-agent MCP server is alive."


# --- Tool modules register themselves here as we build them ---
from server.tools import resume_parser  # noqa: E402,F401  (adds parse_resume, get_parsed_resume, list_resumes)
from server.tools import job_search  # noqa: E402,F401  (adds search_jobs, get_job_details, list_saved_jobs)
from server.tools import matcher_tool  # noqa: E402,F401  (adds match_job_to_profile, rank_jobs)
from server.tools import writer_tool  # noqa: E402,F401  (adds tailor_resume, generate_cover_letter)
from server.tools import pipeline_tool  # noqa: E402,F401  (adds log_application, get_application_status, list_pipeline)
from server.tools import apply_tool  # noqa: E402,F401  (adds start_application)


if __name__ == "__main__":
    mcp.run()
