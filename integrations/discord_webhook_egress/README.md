# Discord Webhook Egress Adapter

A deterministic adapter that takes an approved alert packet from the existing local LLM loop, formats it into a Discord-ready message, sends it through a webhook, and logs the result append-only.

## Mission

This adapter treats the LLM/orchestrator as upstream. It does not perform market analysis itself. It strictly formats and sends payloads, validating the structure using a `"v": 1` envelope discipline.

## Usage

### Environment Variables
- `DISCORD_WEBHOOK_URL`: The URL of the Discord webhook. Must not be logged or printed.

### CLI Commands

```bash
# Dry-run with a sample packet
python -m integrations.discord_webhook_egress.cli dry-run --sample vwap_watch
python -m integrations.discord_webhook_egress.cli dry-run --sample session_open_brief

# Dry-run with a custom file
python -m integrations.discord_webhook_egress.cli dry-run --file path/to/packet.json

# Send a sample packet
python -m integrations.discord_webhook_egress.cli send --sample vwap_watch

# Send a custom file
python -m integrations.discord_webhook_egress.cli send --file path/to/packet.json
```

### Logging & Output
- **Logs:** Appends to `logs/discord_webhook_egress.jsonl`
- **Output:** Writes the latest rendered markdown message to `outputs/latest_discord_webhook_message.md`
