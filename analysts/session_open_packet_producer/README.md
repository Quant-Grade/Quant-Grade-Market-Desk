# Session Open Packet Producer v0.1

An analyst module that generates valid `"v": 1` Discord webhook egress packets for session open analysis (Asia, London, NY).

## Mission
To process context about approaching trading sessions and format it deterministically for downstream execution by the Discord Webhook Egress Adapter.

## Rules
- **No Direct Sending:** Only writes JSON files; does not trigger the webhook natively.
- **Strict Validations:** `session` must be one of `Asia, London, NY`. `session_phase` must be one of `pre_open, open_window, post_open, mid_session`.
- **Open-Window Override:** Packets marked as `open_window` will default to a `watch` severity.
- **Volatility Rule:** Automatically overrides risk mode if elevated volatility is detected.
- **Sweep Injection:** Detects sweeps of the prior session's high/low and logs them into evidence.
- **Fail Closed Language Guard:** Throws an exception if any predictive or promotional "buy/sell" language is detected in the input payload.

## Usage

Produce from a sample file:
```bash
python -m analysts.session_open_packet_producer.cli produce --sample session_open_input
```

Produce from an absolute path:
```bash
python -m analysts.session_open_packet_producer.cli produce --file path/to/input.json
```

Outputs are written to `outputs/packets/latest_session_open_packet.json` and logged to `logs/session_open_packet_producer.jsonl`.
