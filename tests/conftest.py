import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(APP_DIR))
