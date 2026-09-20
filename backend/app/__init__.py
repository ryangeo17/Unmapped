"""UnMapped backend application."""

from pathlib import Path

from dotenv import load_dotenv

# The README tells you to `cp .env.example .env`, so the file has to be read
# whichever directory uvicorn was started from. Real environment variables win:
# the tests and every deployment set theirs before this module is imported.
BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
load_dotenv(ROOT / ".env", override=False)
load_dotenv(BACKEND / ".env", override=False)
