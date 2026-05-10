# Local LLM Market Report Writer v0.1

An analyst wrapper module that queries a Local LLM (OpenAI Chat Completions schema over REST) to translate complex, deterministic packet arrays into clean, retail-readable `AlertPacket` egress payloads.

## Mission
To leverage generative AI specifically for readability, tone matching, and retail translations without allowing the LLM to invent facts, hallucinate schema properties, or inject dangerous promotional phrasing.

## Configuration
Requires an active Local LLM instance. Defaults to:
- `LOCAL_LLM_BASE_URL`: `http://localhost:1234/v1`
- `LOCAL_LLM_MODEL`: `local-model`

If no LLM is running, CLI execution will fail closed due to a connection timeout/refusal.

## Rules
- **No Exchange Endpoints:** Only runs purely on local REST endpoints.
- **Fail Closed Hallucination Guard:** If the LLM generates a key not natively supported by the frozen `AlertPacket` egress schema, it triggers a `HallucinationError` and crashes safely.
- **Fail Closed Sanitizer:** If the LLM attempts to output "buy here" or similar financial-advice phrases, it crashes via `InputValidationError`.
- **Inherited Fields:** Bypasses LLM output for system deterministic variables (e.g., `not_financial_advice`, `leader_decision`, `event_type`).

## Usage

Run default write (reads latest `multi_role_market_read_packet`):
```bash
python -m analysts.local_llm_market_report_writer.cli write
```

Outputs are written to `outputs/packets/latest_llm_market_report_packet.json` and logged to `logs/local_llm_market_report_writer.jsonl`.
