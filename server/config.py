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

    # Embeddings (via Ollama — no separate ML library needed)
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")


settings = Settings()

# Ensure storage directories exist at import time
settings.DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
settings.RESUME_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
settings.APPLICATIONS_DIR.mkdir(parents=True, exist_ok=True)
