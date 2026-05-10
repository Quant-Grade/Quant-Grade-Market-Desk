# Liquidity Bands Packet Producer v0.1

An analyst module that generates valid `"v": 1` Discord webhook egress packets for liquidity band and sweep analysis.

## Mission
To securely format deterministic observations about price interactions with critical liquidity zones into an `AlertPacket` structure for downstream execution by the Discord Webhook Egress Adapter.

## Rules
- **No Direct Sending:** Only writes JSON files; does not trigger webhooks natively.
- **Strict Logic Rules:** Validates `liquidity_type`, `sweep_status`, and `reaction_status` against strict enumerations.
- **Severity Overrides:** Elevates severity if a sweep is actively occurring.
- **Language Guards:** Operates a "Fail Closed" sanitizer. If any predictive ("buy here") or promotional ("guaranteed") language is fed to the producer, it immediately crashes and logs an `InputValidationError` to prevent downstream breaches.

## Usage

Produce from a sample file:
```bash
python -m analysts.liquidity_bands_packet_producer.cli produce --sample liquidity_bands_input
```

Produce from an absolute path:
```bash
python -m analysts.liquidity_bands_packet_producer.cli produce --file path/to/input.json
```

Outputs are written to `outputs/packets/latest_liquidity_bands_packet.json` and logged to `logs/liquidity_bands_packet_producer.jsonl`.
