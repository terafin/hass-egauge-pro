# eGauge Pro

A maintained Home Assistant custom integration for [eGauge](https://www.egauge.net/)
energy monitors, on the modern **JSON API** (`egauge-async` 0.4.0+).

It runs under its own domain (`egauge_pro`) — **deliberately not** overriding the
built-in `egauge` integration — and provides the two things the built-in does **not**:

- **Per-register energy buckets** — `today / daily / weekly / monthly / yearly` kWh
  for every power register (computed from cumulative-counter diffs). The built-in
  only exposes a single cumulative counter and leans on the Energy dashboard for
  period totals.
- **Per-register sign inversion** — flip the sign of selected registers (e.g. a CT
  wired backwards, or generation-vs-consumption), via the integration's **Options**.

It also exposes instantaneous values per register (power, and voltage/current/
temperature/humidity/pressure where present).

## Why this exists

The original `neggert/hass-egauge` was archived (2026) and pinned to the **XML API**
(`egauge-async` 0.1.2), which eGauge firmware ≥ 4.7 has dropped — a time bomb. This is
a clean rewrite onto the JSON API and current Home Assistant entity patterns, keeping
the buckets + inversion that make it worth running in lieu of the core integration.

## Install (HACS)

1. HACS → Integrations → ⋮ → Custom repositories → add this repo as an *Integration*.
2. Install **eGauge Pro**, restart Home Assistant.
3. Settings → Devices & Services → **Add Integration** → *eGauge Pro*.
   Enter host/IP (bare — no `http://`), username, password, and whether to use HTTPS.
4. Configure inverted registers under the integration's **Configure** (Options).

## Entity naming

Entities are named `sensor.egauge_<register>` (instantaneous) and
`sensor.egauge_<window>_<register>` (energy buckets, e.g.
`sensor.egauge_todays_solar`), under a single **eGauge** device.

## Migrating from the abandoned `egauge` integration

See [MIGRATION.md](MIGRATION.md) — a cutover runbook that preserves your existing
entity_ids (and therefore recorder history + Energy dashboard wiring).

## Credit

Rewrite of [`neggert/hass-egauge`](https://github.com/neggert/hass-egauge) and built on
[`neggert/egauge-async`](https://github.com/neggert/egauge-async). MIT licensed.
