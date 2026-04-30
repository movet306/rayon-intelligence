"""
remove_duplicate_dotenv.py - Remove the redundant dotenv block.

Background:
  add_dotenv_to_server.py added a dotenv-load block at the top of server.py
  (lines 9-15), but server.py already had `load_dotenv()` at line 31. This
  produced a duplicate. Functionally harmless, but cleaner to remove the
  redundant top block. The original line 31 call is sufficient.

Idempotent.
"""
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parent.parent
SERVER = REPO / "dashboard" / "server.py"

DUPLICATE_BLOCK = """# Auto-load .env from repo root so DATABASE_URL etc. work without manual export.
# Added by scripts/add_dotenv_to_server.py.
try:
    from dotenv import load_dotenv
    from pathlib import Path as _Path
    load_dotenv(_Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

"""

src = SERVER.read_text(encoding="utf-8")

if DUPLICATE_BLOCK not in src:
    print("[skip] duplicate dotenv block not found (already removed?)")
    sys.exit(0)

src = src.replace(DUPLICATE_BLOCK, "", 1)
SERVER.write_text(src, encoding="utf-8")
print("[OK] duplicate dotenv block removed; server.py now relies on existing load_dotenv() at line 31")
