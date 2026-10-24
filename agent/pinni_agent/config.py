"""Pinni Track B agent configuration and environment settings."""
import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Settings:
    # LLM & Embedding (Ollama)
    ollama_url: str = field(
        default_factory=lambda: os.getenv("PINNI_OLLAMA_URL", "http://localhost:11434")
    )
    llm_model: str = field(
        default_factory=lambda: os.getenv("PINNI_LLM_MODEL", "qwen3.5:2b-q4_K_M")
    )
    embed_model: str = field(
        default_factory=lambda: os.getenv("PINNI_EMBED_MODEL", "nomic-embed-text:latest")
    )
    llm_enabled: bool = field(
        default_factory=lambda: os.getenv("PINNI_LLM_ENABLED", "1").lower() not in ("0", "false", "no")
    )

    # Directories (pointing cleanly to contract/ and agent/data/)
    root_dir: Path = field(
        default_factory=lambda: Path(__file__).resolve().parent.parent.parent
    )
    contract_dir: Path = field(
        default_factory=lambda: Path(__file__).resolve().parent.parent.parent / "contract"
    )
    data_dir: Path = field(
        default_factory=lambda: Path(__file__).resolve().parent.parent / "data"
    )
    sqlite_path: str = field(
        default_factory=lambda: os.getenv(
            "PINNI_SQLITE_PATH",
            str(Path(__file__).resolve().parent.parent / "data" / "pinni.db"),
        )
    )

    # Neo4j (optional; falls back to in-memory graph)
    neo4j_uri: str = field(
        default_factory=lambda: os.getenv("PINNI_NEO4J_URI", "bolt://localhost:7687")
    )
    neo4j_user: str = field(
        default_factory=lambda: os.getenv("PINNI_NEO4J_USER", "neo4j")
    )
    neo4j_password: str = field(
        default_factory=lambda: os.getenv("PINNI_NEO4J_PASSWORD", "secret")
    )

    # MCP server configuration
    mcp_host: str = field(
        default_factory=lambda: os.getenv("PINNI_MCP_HOST", "127.0.0.1")
    )
    mcp_port: int = field(
        default_factory=lambda: int(os.getenv("PINNI_MCP_PORT", "8765"))
    )

    # Recommender parameters
    exploration_rate: float = 0.15
    cold_start_threshold: int = 5
    time_decay_half_life_hours: float = 48.0
    max_feed_items: int = 30


default_settings = Settings()
