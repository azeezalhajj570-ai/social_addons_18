from __future__ import annotations

import sys
from pathlib import Path

# Allow running as: python user_client_app/pyrogram_user_client.py
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from user_client_app.main import main


if __name__ == "__main__":
    main()
