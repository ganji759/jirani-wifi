"""Router commands that work without the website.

  python -m app.cli status    show the guest slot
  python -m app.cli off       turn the guest Wi-Fi off
  python -m app.cli restore   put the slot back to its original settings
"""

from __future__ import annotations

import sys

from app.config import load_settings
from app.slot import SlotManager


def main(argv: list[str]) -> int:
    if len(argv) != 1 or argv[0] not in ("status", "off", "restore"):
        print(__doc__)
        return 2
    slot = SlotManager(load_settings())
    if argv[0] == "off":
        slot.turn_off()
    elif argv[0] == "restore":
        slot.restore()
    info = slot.read()
    print(f"slot {info['index']}: {'ON' if info['enable'] else 'off'}, name {info['ssid']!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
