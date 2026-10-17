"""Tests for the router password encryption.

The known values come from the real router page. The browser ran the page
code and made these outputs. The test checks that our Python makes the same
output.
"""

from app.router_client import _extract_key, encrypt_password

# This is the key the router page uses, wrapped in random padding.
SAMPLE_ACS = "0lTMIf6HTT4VVE5k24kLVL0lTMIfj"
KEY = b"6HTT4VVE5k24kLVL"


def test_extract_key():
    assert _extract_key(SAMPLE_ACS) == KEY


def test_encrypt_matches_router():
    assert encrypt_password("abc", KEY) == "B96DFB580A727F8F23A984530021531A"
    assert (
        encrypt_password("abcdefghijklmnop", KEY)
        == "0E6E406E9BBD3066B7CE520177E92D47519CAE706BC2B91B1B67A4B2F4548887"
    )
