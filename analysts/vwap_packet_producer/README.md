# VWAP Packet Producer v0.1

An analyst module that generates valid `"v": 1` Discord webhook egress packets for VWAP-related conditions.

## Mission
To securely and deterministically map incoming analytical data about VWAP interactions into a compliant `AlertPacket` structure for downstream execution by the Discord Webhook Egress Adapter.

## Rules
- **No Direct Sending:** It only writes JSON files. It does not send webhook calls itself.
- **Strict Logic Rules:** Validates distance to VWAP, applies risk mode overrides for choppy behavior, and infers severity based on the presence of microstructure confirmation.
- **Language Guards:** Automatically redacts forbidden prediction language.

## Usage

Produce from a sample file:
```bash
python -m analysts.vwap_packet_producer.cli produce --sample vwap_input
```

Produce from an absolute path:
```bash
python -m analysts.vwap_packet_producer.cli produce --file path/to/input.json
```

Outputs are written to `outputs/packets/latest_vwap_packet.json` and logged to `logs/vwap_packet_producer.jsonl`.
