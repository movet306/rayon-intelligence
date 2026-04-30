"""
add_dotenv_to_server.py - Make dashboard server auto-load .env on startup.

Problem:
  Every time uvicorn is started, you must remember to set $env:DATABASE_URL
  first. Forgetting it gives "connection to localhost:5432 refused" because
  psycopg2 falls back to default. This has happened multiple times today.

Fix:
  Add load_dotenv() at the very top of dashboard/server.py, before any
  module that reads DATABASE_URL. Idempotent.

After this:
  python -m uvicorn dashboard.server:app --reload --port 8000

  ...just works. No need to set $env:DATABASE_URL anymore.
"""
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parent.parent
SERVER = REPO / "dashboard" / "server.py"

DOTENV_BLOCK = """# Auto-load .env from repo root so DATABASE_URL etc. work without manual export.
# Added by scripts/add_dotenv_to_server.py.
try:
    from dotenv import load_dotenv
    from pathlib import Path as _Path
    load_dotenv(_Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

"""

src = SERVER.read_text(encoding="utf-8")

if "Auto-load .env from repo root" in src:
    print("[skip] dotenv autoload already present in server.py")
    sys.exit(0)

# Insert after the very first line (could be a docstring or first import)
# Strategy: insert before the first `import` or `from` statement.
import re

# Find first import/from line
m = re.search(r"^(import |from )", src, flags=re.MULTILINE)
if not m:
    print("[X] Could not locate first import statement in server.py")
    sys.exit(1)

insert_at = m.start()
new_src = src[:insert_at] + DOTENV_BLOCK + src[insert_at:]

SERVER.write_text(new_src, encoding="utf-8")
print(f"[OK] dotenv autoload inserted at position {insert_at}")
print()
print("Restart uvicorn (no need to $env:DATABASE_URL anymore):")
print("  python -m uvicorn dashboard.server:app --reload --port 8000")
