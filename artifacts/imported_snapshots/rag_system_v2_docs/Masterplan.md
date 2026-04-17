# masterplan.md

## 1. Canonical objective
Create a portable, local-first AI RAG trading system for OKX that learns from market data, account state, execution outcomes, and stored memory. Use cloud resources only to bootstrap evaluation, prompt design, and experimentation. Production memory, retrieval, orchestration, and routine generation must remain exportable and locally runnable.

## 2. Canonical architecture

### Layer A — Exchange interface
Responsibilities:
- REST and WebSocket connectivity
- public market data ingestion
- private account/order/position ingestion
- idempotent order routing
- environment isolation: demo vs live
- account-mode/order-parameter preflight checks
- retry/throttle policy
- heartbeat/status monitoring

Outputs:
- normalized event stream
- canonical order/fill ledger
- exchange capability registry
- execution telemetry

### Layer B — Event store
Append-only storage for:
- market events
- snapshots
- order intents
- order acknowledgements
- fills
- account snapshots
- evaluator outputs
- operator overrides

Recommended storage:
- Parquet for large append-only facts
- SQLite/Postgres for indexed metadata and ledgers
- file-based manifests for portability

### Layer C — Feature and state builder
Builds:
- multi-timescale candle features
- microstructure features from books/trades
- volatility/funding/open-interest features where used
- account/risk features
- execution-quality features
- regime labels
- drift metrics

Output object:
`state_snapshot`

Minimum fields:
- timestamp
- environment
- account_mode
- instrument
- feature vector
- open exposure
- risk budget
- current policy set
- detected regime
- drift score
- data quality flags

### Layer D — Memory system
#### D1 Raw memory
Immutable logs and snapshots.

#### D2 Distilled memory
Promotion pipeline turns raw episodes into durable cards:
- regime_card
- trade_card
- execution_incident_card
- experiment_card
- risk_event_card
- session_summary_card
- policy_change_card

#### D3 Retrieval index
Hybrid retrieval:
- metadata filters first
- embedding similarity second
- recency/risk weighting third
- evaluator rerank fourth

Portable default:
- local embeddings
- local vector store or SQLite FTS + embedding sidecar
- all artifacts serializable to files

### Layer E — Reasoning and planning
Submodules:
- market interpreter
- retrieval orchestrator
- action planner
- risk governor
- execution planner
- post-trade analyst

Contract:
The reasoning layer never sends an order directly. It emits structured action proposals which must pass the risk governor and exchange preflight layer.

### Layer F — Evaluation and governance
Tracks:
- decision quality
- policy compliance
- slippage
- fill quality
- drawdown
- calibration
- drift
- retrieval usefulness
- experiment lineage

Mandatory gates:
- Gate 0: data integrity
- Gate 1: replay correctness
- Gate 2: paper execution stability
- Gate 3: strategy validity under walk-forward
- Gate 4: limited live eligibility

## 3. Canonical data model

### Fact tables
- market_candles
- market_trades
- market_books
- account_snapshots
- positions
- order_intents
- order_events
- fills
- risk_events
- evaluator_scores
- drift_events
- session_notes

### Memory cards
- regime_cards
- trade_cards
- incident_cards
- experiment_cards
- policy_cards

### Core IDs
- event_id
- snapshot_id
- order_intent_id
- exchange_order_id
- cl_ord_id
- episode_id
- instrument_id
- strategy_id
- experiment_id

## 4. Retrieval contract
Given `state_snapshot`, retrieval must return:
1. comparable historical regimes,
2. recent similar trade setups,
3. relevant execution incidents,
4. active policy constraints,
5. latest instrument/account constraints.

Returned bundle:
- top_k_cards
- exclusion reasons
- freshness stats
- retrieval confidence
- stale-memory flags

## 5. Strategy policy for v1
Use a constrained policy stack:
- regime classification
- candidate setup scoring
- risk-adjusted action proposal
- hard no-trade conditions
- fixed max position and loss limits
- strict cooldowns after incidents

No v1 support for:
- self-modifying strategy logic in live mode
- unconstrained leverage expansion
- autonomous derivative trading

## 6. Memory promotion policy
Promote to distilled memory only if one of:
- trade closed
- major PnL excursion
- execution anomaly
- drift threshold crossed
- manual operator note
- experiment completed
- policy changed

Each card must include:
- purpose
- evidence sources
- time bounds
- regime tags
- instrument tags
- confidence
- outcome label
- retention/decay policy

## 7. Evaluation framework
### Retrieval metrics
- hit@k on relevant prior cases
- policy-card recall
- stale-card rate
- contradiction rate

### Trading metrics
- net return
- drawdown
- turnover
- slippage
- fill rate
- cancel/amend ratio
- latency distribution
- profit factor
- deflated/permuted significance checks where feasible

### Model metrics
- calibration
- directional accuracy by regime
- error by volatility bucket
- stability over walk-forward windows
- drift response lag

### Safety metrics
- policy violations
- environment mismatches caught
- rejected-order diagnosis coverage
- recovery time after disconnects

## 8. Weaknesses and required additions
### Weakness: raw RAG alone is too shallow
Add:
- regime detector
- drift detector
- execution state machine
- evaluator-reranked retrieval

### Weakness: market data and account state are heterogeneous
Add:
- canonical normalization layer
- feature provenance tags
- exchange capability registry

### Weakness: memory may become stale or self-reinforcing
Add:
- stale-memory penalties
- decay functions
- contradiction tracking
- negative memory retrieval (prior failures)

### Weakness: exchange ops can fail before strategy quality matters
Add:
- preflight guardrails
- throttle budgeter
- idempotent order keys
- status-aware router

## 9. Build order
1. exchange and event capture
2. canonical schema and storage
3. replay + backfill pipeline
4. state snapshot builder
5. raw memory and promotion rules
6. retrieval layer
7. evaluator + paper execution loop
8. constrained strategy logic
9. drift and regime modules
10. live-readiness gates

## 10. Freeze / kill ledger
### Killed
- live-first architecture
- giant multi-agent swarm
- cloud-locked memory
- PnL-only evaluator
- derivatives-first scope

### Frozen
- options/futures live execution
- RL policy training
- autonomous strategy generation
- cross-venue execution
- online self-editing policies

## 11. Artifact map to produce next
- rag_schema.txt
- chunking_policy.txt
- metadata_schema.txt
- storage_model.txt
- routing_graph.txt
- eval_rubric.txt
- migration_guide.txt
- system_prompt.txt
- leader_prompt.txt
- red_team_prompt.txt

## 12. Acceptance standard
The plan survives only if:
- every important component is file-portable,
- paper trading is fully auditable,
- retrieval improves decisions rather than merely describing history,
- live promotion requires passing explicit gates,
- a local runtime can replace cloud bootstrap functions.
