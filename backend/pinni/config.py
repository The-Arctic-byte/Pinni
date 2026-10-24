"""Settings from environment variables. Defaults suit local development."""

import os
from dataclasses import dataclass
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent


def _flag(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Settings:
    db_path: Path
    contract_dir: Path
    # Static files of the admin web page (C4), served at /admin.
    admin_dir: Path
    # Seed the database from contract/mock on first start (empty database only).
    seed_mock: bool
    # Give the mock users sign-in credentials (see seed.DEV_PASSWORD). Never enable in production.
    dev_accounts: bool
    # Knowledge graph. Empty URI = in-memory graph rebuilt from SQLite at startup.
    neo4j_uri: str
    neo4j_user: str
    neo4j_password: str
    # Vector store: a directory (embedded Chroma), an http(s):// Chroma server, or "memory".
    chroma: str
    # Embeddings. Empty URL = hashing embedder (no model needed).
    ollama_url: str
    embed_model: str
    # Seed the mock stories, reports, posts, notifications and events too; otherwise only places,
    # channels and users, and the news is what the agent publishes.
    seed_content: bool = True
    # The Track B agent (pinni/newsroom.py): a round at startup and every N minutes (0 = only from
    # the admin page; tests use 0), and whether it may use Ollama (otherwise its offline heuristics).
    agent_every_minutes: float = 0
    agent_llm: bool = False

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            db_path=Path(os.environ.get("PINNI_DB_PATH", BACKEND / "data" / "pinni.db")),
            contract_dir=Path(os.environ.get("PINNI_CONTRACT_DIR", BACKEND.parent / "contract")),
            admin_dir=Path(os.environ.get("PINNI_ADMIN_DIR", BACKEND.parent / "admin")),
            seed_mock=_flag("PINNI_SEED_MOCK", True),
            dev_accounts=_flag("PINNI_DEV_ACCOUNTS", True),
            neo4j_uri=os.environ.get("PINNI_NEO4J_URI", ""),
            neo4j_user=os.environ.get("PINNI_NEO4J_USER", "neo4j"),
            neo4j_password=os.environ.get("PINNI_NEO4J_PASSWORD", ""),
            chroma=os.environ.get("PINNI_CHROMA", str(BACKEND / "data" / "chroma")),
            ollama_url=os.environ.get("PINNI_OLLAMA_URL", ""),
            embed_model=os.environ.get("PINNI_EMBED_MODEL", "bge-m3"),
            seed_content=_flag("PINNI_SEED_CONTENT", True),
            agent_every_minutes=float(os.environ.get("PINNI_AGENT_EVERY_MINUTES", "30")),
            agent_llm=_flag("PINNI_AGENT_LLM", False),
        )
