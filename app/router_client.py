"""Client for the FiberHome HG6543C7 home gateway web admin.

The router has no API. This module drives the same ajax endpoints that the
router web page uses. It logs in, lists connected devices, and will later
add or remove devices from the access control list.

Login flow (seen in the router page scripts):
  1. GET get_acs_random. The reply holds a random string.
  2. The 16 character key sits in the middle of that string. The page cuts
     the first 6 characters and the last 7 characters.
  3. The password is encrypted with AES CBC. The key is also the IV. The
     output is upper case hex.
  4. POST do_login with the username, the encrypted password, and the
     session id from step 1.
"""

from __future__ import annotations

import httpx
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

KEY_PREFIX_LEN = 6
KEY_SUFFIX_LEN = 7


def _extract_key(acs_random: str) -> bytes:
    """Cut the 16 character key out of the acs_random string."""
    key = acs_random[KEY_PREFIX_LEN:-KEY_SUFFIX_LEN]
    if len(key) != 16:
        raise ValueError(f"unexpected key length {len(key)} from router")
    return key.encode()


def encrypt_password(plain: str, key: bytes) -> str:
    """Encrypt a password the same way the router page does."""
    padder = padding.PKCS7(128).padder()
    data = padder.update(plain.encode()) + padder.finalize()
    cipher = Cipher(algorithms.AES(key), modes.CBC(key))
    enc = cipher.encryptor()
    out = enc.update(data) + enc.finalize()
    return out.hex().upper()


def decrypt_value(hex_text: str, key: bytes) -> str:
    """Decrypt a value that the router sends back, such as an SSID name."""
    cipher = Cipher(algorithms.AES(key), modes.CBC(key))
    dec = cipher.decryptor()
    data = dec.update(bytes.fromhex(hex_text)) + dec.finalize()
    unpadder = padding.PKCS7(128).unpadder()
    return (unpadder.update(data) + unpadder.finalize()).decode()


class RouterError(Exception):
    pass


class RouterClient:
    """A logged in session with the router."""

    def __init__(self, host: str = "192.168.1.1", timeout: float = 10.0) -> None:
        self.base = f"http://{host}"
        self._http = httpx.Client(base_url=self.base, timeout=timeout)

    def _ajax_get(self, method: str) -> dict:
        resp = self._http.get("/cgi-bin/ajax", params={"ajaxmethod": method, "_": "1"})
        resp.raise_for_status()
        return resp.json()

    def _ajax_post(self, method: str, data: dict) -> dict:
        # The router wants the method name in the body, not in the query.
        body = dict(data)
        if "sessionid" not in body:
            body["sessionid"] = self._ajax_get("get_refresh_sessionid")["sessionid"]
        body["ajaxmethod"] = method
        resp = self._http.post(
            "/cgi-bin/ajax",
            data=body,
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        resp.raise_for_status()
        return resp.json()

    def login(self, username: str, password: str) -> None:
        info = self._ajax_get("get_acs_random")
        acs = info.get("acsRandom") or info.get("acs_random")
        if not acs:
            raise RouterError("router did not return acs_random")
        key = _extract_key(acs)
        self._key = key
        session_id = info.get("sessionid", "")
        result = self._ajax_post(
            "do_login",
            {
                "username": username,
                "loginpd": encrypt_password(password, key),
                "port": 0,
                "sessionid": session_id,
            },
        )
        if result.get("login_result") != 0:
            raise RouterError(f"login failed, code {result.get('login_result')}")

    def get_slot(self, index: int) -> dict:
        """Read one Wi-Fi slot. Index 1 is the main Wi-Fi, 2 to 4 are spare."""
        slots = self._ajax_get("get_wifi_status")["wifi_status"]
        raw = slots[index - 1]
        return {
            "index": index,
            "enable": raw["Enable"] == "1",
            "ssid": decrypt_value(raw["SSID"], self._key),
            "password": decrypt_value(raw["PreSharedKey"], self._key),
            "beacon_type": raw["BeaconType"],
            "encryption": raw["WPAEncryptionModes"],
            "rekey_interval": raw["X_FH_WPARekeyInterval"],
            "visible": raw["X_FH_SSIDHide"] == "1",
            "duration": int(raw.get("duration") or 0),
        }

    def set_slot(
        self,
        index: int,
        enable: bool,
        ssid: str,
        password: str,
        duration_minutes: int = 0,
        beacon_type: str = "11i",
        encryption: str = "AESEncryption",
        rekey_interval: str = "86400",
        visible: bool = True,
    ) -> None:
        """Write one Wi-Fi slot. The router turns the slot off itself after
        duration_minutes. Zero means no time limit."""
        if index == 1:
            raise RouterError("refusing to change the main Wi-Fi")
        data = {
            "wifiIndex": index,
            "Enable": 1 if enable else 0,
            "SSID": encrypt_password(ssid, self._key),
            # The router names this field "hide", but 1 means visible.
            "X_FH_SSIDHide": 1 if visible else 0,
            "BeaconType": beacon_type,
            "X_FH_WPARekeyInterval": rekey_interval,
            "WPAEncryptionModes": encryption,
            "PreSharedKey": encrypt_password(password, self._key),
            "device_type": "HG6543C7",
        }
        if duration_minutes:
            data["duration"] = duration_minutes
        else:
            data["Duration"] = 0
        result = self._ajax_post("setWlanAdvancedCfg", data)
        if str(result.get("result", "0")) not in ("0", "success"):
            raise RouterError(f"router refused the change: {result}")

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "RouterClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
