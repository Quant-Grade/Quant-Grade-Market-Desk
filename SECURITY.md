# Security Policy

The Quant-Grade Market Desk treats local integrity and network safety as its highest priorities.

## Core Tenets

1. **Local-First Processing:** 
   No market data, pipeline outputs, or analytic packets are transmitted outside of your machine unless explicitly commanded by you, to your own secure webhooks.
2. **Credential Management:**
   - **DO NOT** commit `.env` files.
   - **DO NOT** commit your `DISCORD_WEBHOOK_URL`.
   - **DO NOT** commit API tokens or secret keys.
3. **LLM Privacy:**
   - The system utilizes a *local* LLM server model endpoint specifically to guarantee that your trading logic, market reads, and structural intelligence never leak to third-party corporate APIs. 
4. **Boundary Guarantees:**
   - Analysts operate strictly offline. They do not hold network access privileges.
   - Egress adapters do not dictate logic. They are dumb endpoints that only pipe schema-approved, policy-gated outputs.
   - All modules "Fail-Closed" and will halt system executions entirely rather than leaking undefined schema parameters.

## Reporting a Vulnerability

If you discover a structural vulnerability or leak within the pipeline, do not execute the pipeline live. Submit an issue on the GitHub repository, maintaining strict obfuscation of your personal endpoints or data.
