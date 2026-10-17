"""Settings from the .env file in the project root."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        os.environ.setdefault(name.strip(), value.strip())


@dataclass(frozen=True)
class Settings:
    router_host: str
    router_user: str
    router_pass: str
    slot_index: int
    slot_ssid: str
    admin_pass: str
    data_dir: Path

    @property
    def db_url(self) -> str:
        return f"sqlite:///{self.data_dir / 'jirani.db'}"

    @property
    def backup_file(self) -> Path:
        return self.data_dir / f"slot{self.slot_index}_original.json"


def load_settings() -> Settings:
    _load_env_file(ROOT / ".env")
    data_dir = Path(os.environ.get("DATA_DIR", ROOT / "data"))
    data_dir.mkdir(parents=True, exist_ok=True)
    return Settings(
        router_host=os.environ.get("ROUTER_HOST", "192.168.1.1"),
        router_user=os.environ["ROUTER_USER"],
        router_pass=os.environ["ROUTER_PASS"],
        slot_index=int(os.environ.get("SLOT_INDEX", "2")),
        slot_ssid=os.environ.get("SLOT_SSID", "Jirani-1"),
        admin_pass=os.environ["ADMIN_PASS"],
        data_dir=data_dir,
    )
