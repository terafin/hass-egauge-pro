# Migration: `egauge` (abandoned) → `egauge_pro`

Goal: cut over from the old `neggert/hass-egauge` custom integration (domain
`egauge`) to `egauge_pro` **without changing any `sensor.egauge_*` entity_id**, so
recorder history and Energy-dashboard wiring carry over untouched.

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
