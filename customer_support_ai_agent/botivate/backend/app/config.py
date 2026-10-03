import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
# On Vercel the project directory is read-only; only /tmp is writable.
_default_db = Path("/tmp/support.db") if os.getenv("VERCEL") else BASE_DIR / "support.db"
DB_PATH = Path(os.getenv("DB_PATH", _default_db))

# Optional: if set, agents use Groq for intent routing + reply writing.
# If empty, a deterministic rule-based fallback is used (app still works fully).
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "openai/gpt-oss-20b")

# The dataset is synthetic (orders run up to Oct 2026), so we pin "today"
# to keep delay detection deterministic. Set AS_OF_DATE="" to use the real date.
AS_OF_DATE = os.getenv("AS_OF_DATE", "2026-09-29")

# Store policy assumptions (not in the dataset - adjust freely)
RETURN_WINDOW_DAYS = int(os.getenv("RETURN_WINDOW_DAYS", "10"))
LOW_STOCK_THRESHOLD = 30
SLA_DAYS = {"urgent": 1, "high": 2, "medium": 3, "low": 5}
HUMAN_AGENTS = ["SUPPORT_001", "SUPPORT_002"]
