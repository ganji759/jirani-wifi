"""Background loop that ends sessions when their time is up."""

from __future__ import annotations

import logging
import threading

from app.billing import Billing

log = logging.getLogger("jirani.scheduler")

CHECK_SECONDS = 30


def start(billing: Billing) -> threading.Event:
    """Start the loop in a thread. Set the returned event to stop it."""
    stop = threading.Event()

    def run() -> None:
        while not stop.wait(CHECK_SECONDS):
            try:
                if billing.tick():
                    log.info("time is up, guest Wi-Fi is off")
            except Exception:
                # Router or network problem. Try again at the next check.
                log.exception("could not end the session, will retry")

    threading.Thread(target=run, name="jirani-scheduler", daemon=True).start()
    return stop
