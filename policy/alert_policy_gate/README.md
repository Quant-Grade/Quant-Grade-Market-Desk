# Alert Policy Gate v0.1

A deterministic policy layer designed to filter generated packet payloads before they hit the Discord webhook egress. It enforces cooldown limits, traps duplicates, drops low-severity (`info`) noise, and strictly validates structural integrity.

## Mission
To separate content generation (LLM/Analysts) from spam control and egress logic. It does not send messages and does not augment evidence. It simply reads, judges, and outputs a `PolicyDecision` dictionary.

## Rule Matrix
1. **BLOCK_UNSAFE**: Original packet fails the frozen egress schema validation logic.
2. **BLOCK_DUPLICATE**: The exact `packet_id` has already been authorized.
3. **BLOCK_LOW_SEVERITY**: Packet severity is `info`.
4. **DOWNGRADE_DRY_RUN_ONLY**: Packet severity is `watch`. 
5. **BLOCK_COOLDOWN**: Packet severity is `important` and an alert for the same `asset` + `event_type` was sent within the 3600-second window.
6. **ALLOW_SEND**: Packet severity is `urgent`, or it's an `important` packet that bypassed cooldown thresholds.

## Usage

Run default evaluation (reads `latest_llm_market_report_packet.json`):
```bash
python -m policy.alert_policy_gate.cli evaluate
```

Outputs are written to `outputs/policy/latest_alert_policy_decision.json` and logged to `logs/alert_policy_gate.jsonl`.
State/memory of past sends is kept in `logs/alert_policy_state.json`.
