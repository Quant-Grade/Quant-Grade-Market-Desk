# Project Status

**Current Status:** v0.1 local pipeline frozen

## Accepted Capabilities
The following modules and architectures have been built, thoroughly tested against structural boundaries, and marked **FROZEN**:

- `latest parquet resolver`
- `real ingestion snapshot loader`
- `generated producer inputs`
- `VWAP packet producer`
- `Session Open packet producer`
- `Liquidity Bands packet producer`
- `multi-role combiner`
- `local LLM report writer`
- `alert policy gate`
- `Discord egress`
- `pipeline runner latest mode`
- `operator profiles`
- `controlled foreground supervisor`

## Known Limitations
For structural transparency, the following scopes are explicitly deferred or limited in the v0.1 release:

- Qualitative market-structure fields inside packets still rely on safe pass-through defaults.
- No CVD, BBO, or order book topography modules have been integrated yet.
- No visual dashboard or UI.
- No user accounts or database dependencies inside this repo.
- No exchange API connectors inside this repo (data comes from offline external `.parquet` files).
- No trade execution or live routing layers.
- No background Windows service daemon logic (looping is handled purely foreground via the supervisor).
