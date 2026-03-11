"""Configuration loader."""
import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).parent.parent


def load_config() -> dict[str, Any]:
    config_path = ROOT / "config.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"config.yaml not found at {config_path}")
    with open(config_path) as f:
        return yaml.safe_load(f)


def get_cv_path() -> Path:
    cfg = load_config()
    return ROOT / cfg["cv"]["path"]


def get_anthropic_key() -> str:
    key = os.getenv("ANTHROPIC_API_KEY", "")
    if not key:
        raise EnvironmentError(
            "ANTHROPIC_API_KEY not set. Copy .env.example to .env and add your key."
        )
    return key


def get_browser_profile_dir() -> Path:
    d = ROOT / "browser_profile"
    d.mkdir(exist_ok=True)
    return d


def get_output_dir(subdir: str) -> Path:
    d = ROOT / "output" / subdir
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_db_path() -> Path:
    d = ROOT / "data"
    d.mkdir(exist_ok=True)
    return d / "jobs.db"
