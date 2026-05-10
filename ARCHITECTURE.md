# Architecture: Quant-Grade Market Desk

This document outlines the architectural philosophy and flow of the Quant-Grade Market Desk ecosystem.

## Core Philosophy

1. **Local-First Design:** 
   The ecosystem runs locally, entirely self-contained. It requires no SaaS subscriptions outside of standard webhook delivery endpoints.
2. **Deterministic Precedence:**
   LLMs are strictly confined to narrative translation roles. All market structure variables (prices, ranges, logic) are mathematically generated and schema-locked *before* they ever reach the LLM. The LLM Writer does not invent facts; it formats them.
3. **Fail-Closed Isolation:**
   Each module acts as a strict firewall. If the ingress parser fails to validate market data, the system stops. If the webhook schema drift is detected, the system stops. Error cascading is explicitly forbidden.
4. **Separation of Concerns:**
   - Egress logic has absolutely zero knowledge of market mechanics.
   - Market data ingestion has zero knowledge of Discord.

## High-Level Packet Flow

```text
[External Parquet File] --> [Latest Parquet Resolver]
                                |
                           (Validation)
                                |
                         [Market Snapshot]
                                |
              +-----------------+-----------------+
              |                 |                 |
       [VWAP Analyst]    [Session Analyst]  [Liquidity Analyst]
              |                 |                 |
              +-----------------+-----------------+
                                |
                       [Multi-Role Combiner]
                         (Constraint Checks)
                                |
                         [Local LLM Writer]
                       (Narrative Translation)
                                |
                        [Alert Policy Gate]
                     (Frequency & Risk Checks)
                                |
                         [Discord Egress]
```

## Storage & Output Philosophy

- **`outputs/`**: Contains short-lived JSON states overriding previous runs (e.g. `latest_pipeline_result.json`, `latest_alert_policy_decision.json`).
- **`logs/`**: Contains append-only telemetry matrices enabling offline post-analysis and auditing (`operator_run_profiles.jsonl`).
- **`inputs/`**: Standardizes sample and generated testing bounds decoupled from production data routes.

## Operational Boundaries

The highest level of control is defined at `ops/controlled_run_supervisor`. It dictates timing loops and orchestrates `ops/operator_run_profiles`. Neither layer touches or tweaks internal analyst metrics or API keys directly; they simply relay explicit constraints (`--dry-run`, `--send`) downward to the `Pipeline Runner`.
