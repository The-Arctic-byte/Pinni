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
    # Seed the database from contract/mock on first start (empty database only).
    seed_mock: bool
    # Give the mock users sign-in credentials (see seed.DEV_PASSWORD). Never enable in production.
    dev_accounts: bool

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            db_path=Path(os.environ.get("PINNI_DB_PATH", BACKEND / "data" / "pinni.db")),
            contract_dir=Path(os.environ.get("PINNI_CONTRACT_DIR", BACKEND.parent / "contract")),
            seed_mock=_flag("PINNI_SEED_MOCK", True),
            dev_accounts=_flag("PINNI_DEV_ACCOUNTS", True),
        )
