# Multi-Role Market Read Combiner v0.1

An analyst combiner module that safely aggregates deterministic packets from the `vwap`, `session_open`, and `liquidity_bands` producers into a single, comprehensive `multi_role_market_read` payload.

## Mission
To condense multiple operational contexts into one highly-readable Discord egress packet while safely merging evidence, elevating severities, and resolving risk mode conflicts deterministically.

## Rules
- **Schema Dependent:** It relies entirely on the frozen egress adapter schema to validate its three input files before reading them.
- **Fail Closed Consistency:** 
  - Assets must match across all 3 inputs.
  - No missing packets are allowed.
  - Aggressive forbidden language sanitation forces a crash if promotional terms (e.g. "guaranteed", "100%") sneak in.
- **Severity Ranking:** Iterates and chooses the highest severity (`urgent` > `important` > `watch` > `info`).
- **Conflict Handling:** Automatically flags "Mixed evidence. Watch only. Confirmation required." if risk modes across the three packets do not match.

## Usage

Run default combine (reads latest outputs from outputs/packets):
```bash
python -m analysts.multi_role_market_read_combiner.cli combine
```

Outputs are written to `outputs/packets/latest_multi_role_market_read_packet.json` and logged to `logs/multi_role_market_read_combiner.jsonl`.
