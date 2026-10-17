"""Control of the one guest Wi-Fi slot.

Each change makes the router restart its Wi-Fi for a few seconds. All Wi-Fi
devices drop for that time, also the computer that runs this app. So after
each change we wait for the router, log in again, and read the slot back.
"""

from __future__ import annotations

import json
import secrets
import time

import httpx

from app.config import Settings
from app.router_client import RouterClient, RouterError

WAIT_SECONDS = 120


def new_password() -> str:
    # 10 characters, easy to type on a phone.
    alphabet = "abcdefghjkmnpqrstuvwxyz23456789"
    return "".join(secrets.choice(alphabet) for _ in range(10))


class SlotManager:
    def __init__(self, settings: Settings) -> None:
        self.s = settings

    def _client(self) -> RouterClient:
        client = RouterClient(self.s.router_host)
        client.login(self.s.router_user, self.s.router_pass)
        return client

    def _wait_for_router(self) -> None:
        deadline = time.monotonic() + WAIT_SECONDS
        while time.monotonic() < deadline:
            try:
                httpx.get(f"http://{self.s.router_host}/", timeout=2)
                return
            except httpx.TransportError:
                time.sleep(3)
        raise RouterError("router did not come back after the change")

    def read(self) -> dict:
        with self._client() as client:
            return client.get_slot(self.s.slot_index)

    def _apply(self, wanted: dict) -> None:
        with self._client() as client:
            try:
                client.set_slot(
                    self.s.slot_index,
                    wanted["enable"],
                    wanted["ssid"],
                    wanted["password"],
                    wanted.get("duration", 0),
                    wanted.get("beacon_type", "11i"),
                    wanted.get("encryption", "AESEncryption"),
                    wanted.get("rekey_interval", "86400"),
                    wanted.get("visible", True),
                )
            except httpx.TransportError:
                # The Wi-Fi restart can cut the reply. We check below.
                pass
        time.sleep(2)
        self._wait_for_router()
        got = self.read()
        for name in ("enable", "ssid", "password"):
            if got[name] != wanted[name]:
                raise RouterError(f"slot {name} is {got[name]!r}, expected {wanted[name]!r}")

    def backup(self) -> dict:
        """Save the original slot settings once. Never overwrite them."""
        if self.s.backup_file.exists():
            return json.loads(self.s.backup_file.read_text())
        original = self.read()
        self.s.backup_file.write_text(json.dumps(original, indent=2))
        return original

    def turn_on(self, password: str) -> None:
        self.backup()
        self._apply({"enable": True, "ssid": self.s.slot_ssid, "password": password})

    def turn_off(self) -> None:
        self.backup()
        # A new random password, so an old password stops working.
        self._apply({"enable": False, "ssid": self.s.slot_ssid, "password": new_password()})

    def restore(self) -> None:
        """Put the slot back to the settings from before this app."""
        if not self.s.backup_file.exists():
            raise RouterError("no backup file, nothing to restore")
        self._apply(json.loads(self.s.backup_file.read_text()))
