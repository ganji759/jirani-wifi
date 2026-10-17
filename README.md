# jirani-wifi

Share your home Wi-Fi with a neighbor. The neighbor pays for time with a token.

The project uses only your home router and your computer. No extra hardware is necessary. Your own Wi-Fi does not change.

## How it works

The router has 4 Wi-Fi slots. Slot 1 is your main Wi-Fi. This app uses one spare slot (slot 2) as the guest Wi-Fi "Jirani-1".

1. The neighbor pays you. You give the neighbor a token, for example `K7M3-PQ2X`.
2. The app logs in to the router and turns on Jirani-1 with a new random password.
3. The neighbor sees the Wi-Fi name, the password and a QR code.
4. When the time ends, the app turns Jirani-1 off. It also changes the password.

Another token during an open session adds time. The password stays the same.

## Limits

- One household at a time. Billing is per household, not per device.
- Your computer must stay on. The app turns the Wi-Fi off. The router does not do it alone.
- Each change restarts the router Wi-Fi for a few seconds. All Wi-Fi devices drop for that time, also yours.
- The guest Wi-Fi is on the same network as your devices. The router account cannot isolate it.
- The router allows one admin login at a time. If you log in to the router web page, the app logs you out, and the other way around.
- There is no speed limit per guest. The router account has no QoS setting.

## Supported router

FiberHome HG6543C7 with the `user` account. Tested with Savanna firmware. Other FiberHome models with the same web pages can work, but they are not tested.

## Setup

You need Python 3.12 or later.

```sh
git clone https://github.com/ganji759/jirani-wifi.git
cd jirani-wifi
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
```

Edit `.env`. Set the router password and an admin password for the website.

## Run

```sh
.venv/bin/python -m app
```

- Neighbor page: `http://<your-computer-ip>:8000/`
- Admin page: `http://localhost:8000/admin` (any user name, the password is `ADMIN_PASS`)

On the admin page:

1. Add plans, for example "1 day", 1440 minutes, 3000 UGX.
2. Make tokens and give them to neighbors after they pay.
3. Or use "Turn on" to start a plan directly.

The neighbor cannot open the website before the guest Wi-Fi is on. For the first time, use "Turn on" on the admin page and send the password or the QR code to the neighbor. When the neighbor is on Jirani-1, the neighbor can add time with a token on the neighbor page.

## Remove the guest Wi-Fi

Before the first change, the app saves the original slot settings in `data/slot2_original.json`. Do not delete this file.

To put the router back to how it was:

- Admin page: "Restore original settings", or
- Command line: `.venv/bin/python -m app.cli restore`

Other commands: `.venv/bin/python -m app.cli status` and `.venv/bin/python -m app.cli off`.

## Tests

```sh
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest
```

The tests use a fake router. They do not change your Wi-Fi.

## Router notes

The router has no API. The app sends the same requests as the router web page:

- `GET /cgi-bin/ajax?ajaxmethod=get_acs_random` gives a random string. The 16 characters after the first 6 characters (without the last 7) are the AES key.
- Passwords and Wi-Fi names are AES-CBC encrypted. The key is also the IV. The output is upper case hex.
- `POST /cgi-bin/ajax` with `ajaxmethod=do_login` logs in.
- `GET get_wifi_status` reads the 4 slots. `POST setWlanAdvancedCfg` writes one slot.

## Next steps

- Mobile money payment from the neighbor page.
- Host the website online, with a small agent on the home computer.
