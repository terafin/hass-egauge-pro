# Migration: `egauge` (abandoned) → `egauge_pro`

Goal: cut over from the old `neggert/hass-egauge` custom integration (domain
`egauge`) to `egauge_pro` **without changing any `sensor.egauge_*` entity_id**, so
recorder history and Energy-dashboard wiring carry over untouched.

## Sensor model (v0.2.0): cumulative energy counters, no period buckets

`egauge_pro` **no longer reproduces** per-register `todays/daily/weekly/monthly/yearly`
kWh bucket sensors. Those were ~1,700 redundant sensors with reset-ambiguity bugs.
Instead, each **power** register exposes one **lifetime cumulative energy counter**:

| | entity_id pattern | class / state_class / unit |
|---|---|---|
| New energy counter | **`sensor.egauge_<register>_energy`** | `energy` / `total_increasing` / `kWh` |
| Instantaneous power (unchanged) | `sensor.egauge_<register>` | `power` / `measurement` / `W` |

`<register>` is the HA-slugified register name (lowercase; spaces and non-alphanumerics
→ `_`), matching how the instantaneous sensors already slug. Configured sign inversion
is applied to the counter too (it flips a generation register's negative-counting total
into a positive, increasing one). Only POWER registers get a counter.

### Directional Energy-dashboard flows

The HA Energy panel's grid/solar/battery sources bind to these flows. They are
ordinary POWER registers on the device (Justin's eGauge defines them), so they get
counters automatically under the same pattern — **no special-case code**. The
old→new statistic-id remap:

| Energy panel source | old (v0.1.0 bucket) | new counter |
|---|---|---|
| Grid consumed | `sensor.egauge_todays_from_grid` | `sensor.egauge_from_grid_energy` |
| Grid returned | `sensor.egauge_todays_to_grid` | `sensor.egauge_to_grid_energy` |
| Solar production | `sensor.egauge_todays_solar` | `sensor.egauge_solar_energy` |
| Battery out | `sensor.egauge_todays_from_batteries` | `sensor.egauge_from_batteries_energy` |
| Battery in | `sensor.egauge_todays_to_batteries` | `sensor.egauge_to_batteries_energy` |

These are the sign-sensitive ones — whichever read negative raw must be in the
inverted-registers option so their counters increase positively (the Energy panel
requires `total_increasing`). PR #2's auto-detect surfaces the candidates.
(If any register's display name differs from the slug above — e.g. "From Grid" vs
`from_grid` — the slug is identical either way; confirm at smoke that all five
`sensor.egauge_*_energy` appear.)

HA long-term statistics + the Energy dashboard derive daily/monthly/yearly natively from
a `total_increasing` counter, and `utility_meter` helpers cover any explicit "today's X"
cycle sensor an automation still needs.

**Cutover for this model change (handled by Frigg, post-release):**
1. Point the ~12 Energy-dashboard inputs at the new `sensor.egauge_<register>_energy`
   counters (was the old `sensor.egauge_todays_*` buckets).
2. Migrate long-term statistics: rename the old bucket `statistic_id`s → the new counter
   ids so history stays continuous.
3. Add `utility_meter` helpers for the few automations that need a resetting "today's X".

> The old `egauge` → `egauge_pro` cutover below is unchanged for the instantaneous
> sensors; the bucket rows in its snapshot/verify steps no longer apply under v0.2.0.

## v0.2.6: virtual-register entity_id auto-canonicalization

The virtual/formula registers added in v0.2.5 (`Air Conditioning`, `Kitchen &
Cooking`, `Washer & Dryer`, …) can land on a **stale entity_id** on cutover: the
old `egauge` integration used the same `serial-register` unique_id scheme, so HA's
registry still holds an entry for that unique_id with the old integration's
device-prefixed entity_id (e.g. `sensor.garage_egauge_egauge_air_conditioning`), and
HA reuses it instead of `sensor.egauge_air_conditioning` (`suggested_object_id` only
applies to a *fresh* registration). Physicals carried over in an earlier run were
unaffected; the new virtuals were not.

v0.2.6 **auto-canonicalizes** on setup: for each of our registers (matched by
unique_id under the `egauge_pro` domain), a non-canonical entity_id is renamed to
`egauge_<slug>[_energy]` — **only when that canonical id is free** (never clobbering
an existing entity), preserving state history (rename is keyed by unique_id).
Idempotent; a no-op once everything is canonical.

> ⚠️ **Duplicate / orphaned entities.** If the old integration's entities weren't
> fully removed at cutover, a leftover (e.g. `sensor.garage_egauge_egauge_air_conditioning_energy`)
> can still hold the canonical id — the rename then **skips with a warning** rather
> than clobber it. Remove the stale entity (Developer Tools → registry, or delete the
> old integration's leftovers) and restart; the canonical id frees up and the rename
> completes. This is also the cleanup for any duplicate `..._energy` pair reading the
> same value.

## Why entity_ids survive

Entity_ids are derived from the **device name** (`eGauge`) + the **register name**,
**not** the integration domain. `egauge_pro` reuses the same device name and the same
register names, so it regenerates the identical entity_ids — *provided the old
integration's entities are removed first* (so the slugs are free and no `_2` suffix is
appended). Recorder history is keyed by `entity_id` in the database, so an identical
entity_id ⇒ continuous history.

> ⚠️ **Validate on a throwaway/test HA instance first.** The one failure mode is a
> register whose slug collides and lands as `sensor.egauge_<x>_2`. Spot-check after
> cutover (step 6) and remap if needed.

## Pre-flight

1. Snapshot the current `egauge` entity_ids (instantaneous `sensor.egauge_<reg>` +
   buckets `sensor.egauge_<todays|daily|weekly|monthly|yearly>_<reg>`).
2. Back up: `.storage/core.entity_registry`, `.storage/core.config_entries`,
   `.storage/energy`, `.storage/lovelace.lovelace`.

## Cutover

1. **Remove** the old integration: Settings → Devices & Services → *eGauge* → Delete
   (removes its 342 registry entities; recorder history stays keyed by entity_id).
2. Delete `/config/custom_components/egauge/`.
3. Install **eGauge Pro** (HACS), restart HA.
4. **Add Integration → eGauge Pro** with the existing connection details:
   - Host `<your-eGauge-IP>`, **HTTPS off**, Verify SSL off, Username `<your-username>`, password
     (from the old config / 1Password).
5. Open the integration's **Configure** and re-select the inverted registers
   (preserved from the old `invert_sensors` option):
   `Ovens, Stovetop, Register 3 + 4, AC Compressor, Rack + Furnace, Pool, Entrance
   Side Outlets, Entrance Lamp, Register 21 Pair - low watt, Register 22 Pair - low
   watt, Kitchen Lights & GFCI, Kitchen Island Outlets, Register 25 Pair - low watt,
   Register 26 - 800 watt, Speed Oven, Warmer, Kitchen Counter & Soda, Fridge, Attic &
   Garage Outlets & Lights, Garage & Entry Lights & Outlets, Water Heater, EV Charger,
   Living Room Lights, Jacuzzi, Living Room Outlets, Washer, Study & Bedroom Outlets,
   Sub Panel, Guest Bathroom Lights, Bathroom Shelves & Bidet, Rear Attic & Loft
   Bathroom, Loft AC, Hall & Outside Lights, Loft Outlets & Lights, Bathroom Lights &
   Outlets, Steam Shower, Guest Bathroom Bidet, Rear Outdoor Outlets, Guest Bath &
   Outdoor Outlets, Atrium Lights & Garage Outlets, Dryer, Total Usage, Air
   Conditioning, Washer & Dryer, Kitchen & Cooking`
6. **Verify**: all `sensor.egauge_*` entity_ids match the snapshot (none ended `_2`);
   the Energy dashboard is still populated; history is continuous on a few sensors.

## Rollback

Restore the four `.storage` backups and re-add `/config/custom_components/egauge/`,
then restart.
