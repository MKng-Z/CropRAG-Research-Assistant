import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
STORAGE_DIR = PROJECT_ROOT / "storage"
STATIC_DIR = PROJECT_ROOT / "static"

DEFAULT_SOURCE_DIR = Path(
    os.getenv("SOURCE_PDF_DIR", r"E:\crop_paper\农作物分类论文")
)

KIMI_BASE_URL = os.getenv("ANTHROPIC_BASE_URL", "https://api.kimi.com/coding/")
KIMI_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
KIMI_AUTH_TOKEN = os.getenv("ANTHROPIC_AUTH_TOKEN", "")
KIMI_MODEL = os.getenv("KIMI_MODEL", "kimi-k2-0905-preview")

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_AUTH_ENABLED = os.getenv("NEO4J_AUTH_ENABLED", "true").lower() == "true"
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "research2025")
GRAPH_BUILD_METADATA = STORAGE_DIR / "graph_build.json"
