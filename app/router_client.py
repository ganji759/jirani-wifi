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
        resp = self._http.post(
            "/cgi-bin/ajax",
            params={"ajaxmethod": method},
            data=data,
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

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "RouterClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
