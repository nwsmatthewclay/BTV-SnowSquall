# NOAA NEXRAD event-driven live bridge

This integration makes KCXX the trigger for a synchronized BTV Snow Squall processing cycle.

## Flow

NOAA NEXRAD Level-II SNS -> Google Apps Script -> GitHub `repository_dispatch` -> synchronized KCXX/KTYX processing -> live-data branch.

The NOAA real-time notification contains `SiteID`, `DateTime`, `VolumeID`, and chunk metadata. The bridge filters to KCXX and de-duplicates by radar/date/time/volume. GitHub then waits for the completed archive volume, selects KTYX at or before the KCXX scan time, runs the existing object processor, builds the radar mosaic from those exact source volumes, validates synchronization, and publishes the cycle.

## Google Apps Script setup

1. Open Google Apps Script and create a standalone project.
2. Copy `Code.gs` from this directory into the project.
3. In **Project Settings -> Script properties**, add:
   - Name: `GITHUB_TOKEN`
   - Value: a GitHub token that can dispatch workflows for `nwsmatthewclay/BTV-SnowSquall`.
4. Deploy the script as a web app:
   - Execute as: **Me**
   - Who has access: **Anyone**
5. Copy the deployed web-app URL.
6. Subscribe that HTTPS URL to the NOAA topic:
   `arn:aws:sns:us-east-1:684042711724:NewNEXRADLevel2ObjectFilterable`
7. The first SNS `SubscriptionConfirmation` is handled automatically by `doPost`.

### GitHub token

Use a dedicated fine-grained token with the minimum repository permission required to create a repository dispatch event. Do not commit the token to the repository. The Apps Script bridge reads it only from Script Properties.

## Event payload

The bridge sends:

```json
{
  "event_type": "kcxx_scan",
  "client_payload": {
    "radar": "KCXX",
    "scan_time": "2026-10-08T14:35:08Z",
    "volume_id": "602",
    "chunk_id": "28",
    "chunk_type": "I",
    "source": "NOAA_NEXRAD_AWS_SNS"
  }
}
```

GitHub's `repository_dispatch` workflow must exist on the default branch. The live event workflow therefore lives under `.github/workflows/` on `main`, while the science implementation is checked out from `snow-squall-model-foundation`.

## Operational behavior

- KCXX is the master/reference radar.
- KCXX source must be within 3 minutes of the event timestamp.
- KTYX must be no newer than KCXX and normally within 8 minutes.
- RAP remains selected at or before the actual radar scan time.
- Existing 5-minute polling workflows remain in place during validation.
- The event workflow shares the live-publisher concurrency lock so event and polling cycles cannot publish simultaneously.
- `viewer/data/live/event_cycle.json` records the exact source timestamps used for each synchronized publication.
