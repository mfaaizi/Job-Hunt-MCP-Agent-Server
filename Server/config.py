"""
Central configuration for the job-agent MCP server.
Loads from .env (see .env.example for required keys).
"""
from pathlib import Path
from dotenv import load_dotenv
import os

# Project root = parent of server/
ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")


class Settings:
    # JSearch (OpenWeb Ninja)
    JSEARCH_API_KEY: str = os.getenv("JSEARCH_API_KEY", "")
    JSEARCH_BASE_URL: str = os.getenv("JSEARCH_BASE_URL", "https://api.openwebninja.com/jsearch")

    # Ollama
    OLLAMA_HOST: str = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3.1")

    # Storage
    DATABASE_PATH: Path = ROOT_DIR / os.getenv("DATABASE_PATH", "./data/db/job_agent.db").lstrip("./")
    RESUME_STORAGE_DIR: Path = ROOT_DIR / os.getenv("RESUME_STORAGE_DIR", "./data/resumes").lstrip("./")
    APPLICATIONS_DIR: Path = ROOT_DIR / os.getenv("APPLICATIONS_DIR", "./data/applications").lstrip("./")

    # Persistent browser profile for the application-assist tool. Two modes:
    #   "dedicated" (default) — a separate, Playwright-managed profile. Log in
    #     once via scripts/setup_browser_login.py; doesn't touch your real Chrome.
    #   "real_chrome" — reuses your actual, already-logged-in Chrome profile.
    #     No separate login needed, but Chrome must be FULLY CLOSED (including
    #     any lingering background process) every time before start_application
    #     runs — Chrome locks its profile folder while open. See README for how
    #     to find REAL_CHROME_USER_DATA_DIR / REAL_CHROME_PROFILE_DIRECTORY.
    BROWSER_PROFILE_MODE: str = os.getenv("BROWSER_PROFILE_MODE", "dedicated")
    BROWSER_PROFILE_DIR: Path = ROOT_DIR / os.getenv("BROWSER_PROFILE_DIR", "./data/browser_profile").lstrip("./")
    REAL_CHROME_USER_DATA_DIR: str = os.getenv("REAL_CHROME_USER_DATA_DIR", "")
    REAL_CHROME_PROFILE_DIRECTORY: str = os.getenv("REAL_CHROME_PROFILE_DIRECTORY", "Default")

    # Embeddings (via Ollama — no separate ML library needed)
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")


settings = Settings()

# Ensure storage directories exist at import time
settings.DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
settings.RESUME_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
settings.APPLICATIONS_DIR.mkdir(parents=True, exist_ok=True)
settings.BROWSER_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
