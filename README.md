# Personal Flight Tracker

A private flight-price tracker: save as many searches as you want, each
with its own filters, and get a push notification + email the moment
one is worth booking. No third-party account, no ads, no data broker
in the loop.

## How it works

```
config/searches.json  →  src/main.py  →  fast-flights (Google Flights)  →  compare vs data/state.json  →  ntfy + email
```

Every run:
1. Loads your saved searches from `config/searches.json`
2. Queries Google Flights for each one via `fast-flights` (an
   open-source, no-API-key client — see "About the data source" below)
3. Applies your filters (stops, airlines, times, price ceiling)
4. Compares the cheapest matching fare against what it saw last time
5. Sends a push notification (ntfy) and/or email — only when the
   result actually changed enough to matter, not every single hour

State lives in one small JSON file (`data/state.json`); no database
needed at this scale.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env        # fill in your ntfy topic + SMTP creds
cp config/searches.example.json config/searches.json   # edit to your real searches

python -m src.main           # run a check by hand to confirm it works
```

### Saved search fields (`config/searches.json`)

Each entry is one tracked search. See `config/searches.example.json`
for two full examples. Key fields:

| Field | Meaning |
|---|---|
| `origin` / `destination` | IATA airport codes |
| `depart_date` / `return_date` | `YYYY-MM-DD`; omit `return_date` for one-way |
| `max_stops` | `0` = nonstop only, `1` = up to one stop, etc. |
| `airlines_exclude` | IATA airline codes to filter out (e.g. `["NK","F9"]`) |
| `earliest_departure_hour` / `latest_departure_hour` | 24-hour clock, filters red-eyes etc. |
| `max_price` | Your target price ceiling |
| `notify_on` | `"under_max_price"`, `"price_drop"`, or `"both"` |
| `min_drop_amount` | Smallest price change worth re-notifying about |
| `channels` | `["ntfy"]`, `["email"]`, or both |

Add or remove searches any time — no code changes needed.

## Notifications

**Push (ntfy):** free. Install the [ntfy app](https://ntfy.sh/) on
your phone, subscribe to the topic name you put in `.env`, and you're
done. Treat the topic name like a password — anyone who knows it can
publish to it on the public server. Self-host later if you want full
privacy (see ntfy's docs); the code doesn't change, just `NTFY_SERVER`.

**Email:** works with any SMTP provider. For Gmail, generate an
[App Password](https://myaccount.google.com/apppasswords) — your
normal password won't work over SMTP.

## Running it hourly

Two options, in order of how much you want to deal with:

**Cron (simplest):**
```
0 * * * *  cd /opt/flight-tracker && .venv/bin/python -m src.main >> logs/cron.log 2>&1
```

**systemd timer (better logging/retries):** copy
`scripts/flight-tracker.service` and `scripts/flight-tracker.timer`
into `/etc/systemd/system/`, adjust the paths, then:
```
sudo systemctl enable --now flight-tracker.timer
```

## About the data source

This uses [`fast-flights`](https://github.com/AWeirdDev/flights), an
open-source library that queries Google Flights directly (it decodes
Google's own protobuf URL format — no API key, no account, no per-request
fee). That's what makes hourly checks across many saved searches free.

The tradeoff: it's unofficial, so a Google-side change could break it
without warning. If that happens and it's not fixed upstream yet, the
fallback is swapping `src/flights.py`'s internals for a paid API like
SerpApi's Google Flights endpoint (same interface, ~$25/mo for 1,000
searches) — everything else in this project stays the same.

## Privacy / avoiding fare-manipulation fingerprinting

The concern this addresses: repeatedly searching the same route from
the same IP is one of the signals sites can use to raise the price on
you. Two things help:

1. **No persistent session or cookies.** Every check here is a fresh,
   stateless HTTP request — nothing carries over between runs.
2. **Rotating exit IP.** `scripts/rotate_mullvad.sh` switches your
   Mullvad VPN's exit location right before each check, so consecutive
   hourly scans don't all come from the same address. Wire it in as
   `ExecStartPre` (see `flight-tracker.service`) or call it at the top
   of your cron line.

This needs a VPN client running on the same machine as the script —
that's why a small VPS (see below) works better here than a serverless
platform: you can't run a VPN daemon on Cloudflare Workers.

## Free deployment (GitHub Actions + cron-job.org)

This is the $0/month version: GitHub Actions runs the check, commits
`data/state.json` back to the repo (no database needed), and
cron-job.org triggers it every 4-6 hours so you're not at the mercy of
GitHub's own scheduler, which is best-effort and can lag for hours.

**1. Push this repo to GitHub** (private is fine — free minutes apply
either way).

**2. Add your secrets and variables** — repo Settings → Secrets and
variables → Actions:
   - *Secrets* (sensitive): `NTFY_TOPIC`, `SMTP_USER`, `SMTP_PASS`, `EMAIL_TO`
   - *Variables* (not sensitive): `NTFY_SERVER` (e.g. `https://ntfy.sh`), `SMTP_HOST`, `SMTP_PORT`

**3. Create a GitHub Personal Access Token** to let cron-job.org trigger
your workflow:
   - Settings → Developer settings → Personal access tokens → Fine-grained tokens
   - Repository access: only this repo
   - Permissions: **Actions → Read and write**
   - Copy the token now — you won't see it again

**4. Sign up at [cron-job.org](https://cron-job.org)** (free, no card)
and create a job:
   - **URL:** `https://api.github.com/repos/<you>/<repo>/actions/workflows/check-flights.yml/dispatches`
   - **Method:** POST
   - **Headers:**
     - `Authorization: Bearer <your PAT>`
     - `Accept: application/vnd.github+json`
   - **Body (raw JSON):** `{"ref": "main"}`
   - **Schedule:** every 4 or 6 hours (cron-job.org has a preset for this,
     or use custom cron like `0 */4 * * *`)

**5. Test it:** hit cron-job.org's "Test run" button, then check your
repo's Actions tab — you should see a run start within a few seconds.
If it doesn't, double check the token's permissions and the workflow
filename in the URL.

That's it — the `schedule:` entry left in the workflow file is just a
once-a-day backup in case cron-job.org itself ever goes down; the real
cadence is driven by cron-job.org.

## Where to run this + rough cost

Two viable paths, depending on how much you want to spend:

| Piece | Free path | Paid path (~$10/mo) |
|---|---|---|
| Compute + schedule | GitHub Actions + cron-job.org | Small VPS (e.g. Hetzner CX22) |
| IP diversity | GitHub's shared runner pool (free, not controllable) | Mullvad VPN, rotated per check |
| State storage | Committed to the repo | Local file on the VPS |
| Flight data | `fast-flights` (free either way) | `fast-flights` |
| Notifications | ntfy + SMTP (free either way) | ntfy + SMTP |
| **Total** | **$0/mo** | **~$10/mo** |

The tradeoff: the free path has no VPN-style IP rotation — you're
relying on GitHub's shared runner IPs for diversity, which isn't
something you control. At a 4-6x/day cadence that's a reasonable
tradeoff. The paid path buys you actual control over exit IPs and no
dependency on GitHub Actions' scheduling quirks at all — worth
revisiting if you ever want to push toward hourly.

## Limitations / known gaps (v1)

- Multi-city itineraries aren't implemented yet (round-trip and
  one-way are).
- No web UI — searches are edited by hand in `config/searches.json`.
  Very doable to add a small local form later if that'd help.
- If `fast-flights` breaks upstream, checks will start failing loudly
  in the logs (they don't fail silently) until it's patched or swapped.
