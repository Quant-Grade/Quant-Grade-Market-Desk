# OKX Collector — Master Plan

**PLAN VERSION:** v2

## GOAL

Reliable ingestion and persistence of OKX market data (candles, trades, BBO, order book). Post–v0: as-built audit, Windows UTC fix, doc deliverables, and forward design for analytics layer (trade→candle rebuild, validators, session/level/wick engines, TUI) without changing ingestion behavior.

## DONE

- Project scaffold: pyproject.toml, package layout, config (Pydantic), logging.
- CLI: load YAML, Resolved Settings, root_dir writability; subcommands: backfill-candles, ws-candles, ws-market, ws-book, run, dashboard.
- Storage layout: path helpers and atomic writes for candles (merge/dedupe), trades/BBO JSONL, book L2 delta/snapshot; checkpoints per ticker/namespace; health + history; book auto-select caches (per-ticker + global).
- REST candle backfill: chunked fetch, partition-grouped, checkpoint resume; see docs/runbook.md, docs/done_audit.md.
- Live collection: WS candles, market (trades/BBO), book (delta with gap detection + REST reseed; snapshot fallback); reconnect/backoff; rate limiting; atomic writes.
- Validators and quarantine: candles schema validation; invalid or validation-failed writes go to root_dir/_quarantine/candles (see tests/test_storage_writer_candles.py).
- Book: gap detection + reseed for seq-capable channels; snapshot fallback for public books/books5; probe, auto-select, cache TTL/force-probe; opt-in run default and persist last-good on first data per ticker.
- Health heartbeat + history (meta/health.json, meta/health_history); runbook and DONE audit docs.
- **Audit + docs:** AUDIT_REPORT.md, ARCHITECTURE.md, ROADMAP.md, TASKS.md; docs/runbook.md, docs/done_audit.md updated. MASTER_PLAN and COPILOT_LOG updated.
- **Windows UTC fix:** `_session_tz_object("UTC")` returns `datetime.timezone.utc` in storage/layout.py; health and backfill use it; no `ZoneInfo("UTC")` on Windows. Regression test: tests/test_session_tz_utc_windows.py.
- **ws/market skip logging:** Validation skip logged at most on first and every 100th (count + last reason); no per-line spam (okx_collector/ws/market.py).

## Known limitations

- Book delta stream (e.g. books50-l2-tbt on business) may be gated (VIP/auth). Snapshot fallback (--endpoint public --channel books5), probe (--probe), and auto-select/caches are available; see docs/runbook.md.

## Next tasks (aligned to ROADMAP)

1. **Phase 1 — Rebuild core (done):** Analytics package: `okx_collector/analytics/` (RebuiltCandle1m, rebuild_1m_candles); replay test `tests/test_rebuild_1m_from_trades.py`; fixture `tests/fixtures/trades_sample.jsonl` + `expected_candles_1m.json`. Remaining: derived storage layout; optional CLI thin IO.
2. **Phase 2 — Validators (done):** `okx_collector/analytics/validators.py`: ValidationSeverity, ValidationIssue, ValidationReport, validate_rebuilt_1m_candles (monotonic, duplicate, GAP, OHLC, volume), cross_check_against_ingested_candles. Tests: `tests/test_validators_rebuilt_1m.py` (ok fixture, gap, ohlc, duplicate, empty, RebuiltCandle1m sequence).
3. **Phase 3 — Session/level/wick engines (done):** `session_engine.py`: SessionConfig, Session, PoorExtreme, SessionEngine (update/current_session/finalize), poor_extremes_for_session (no_upper_wick, double_top, no_lower_wick, double_print). `wicks.py`: Wick, UntouchedWickTracker (observe, active_untouched, all_wicks). Tests: `tests/test_session_engine.py`, `tests/test_untouched_wicks.py`.
4. **Phase 4 — TUI (in progress):** Rich-based TUI: `okx_collector/analytics/snapshot.py` (DashboardSnapshot, build_snapshot), `okx_collector/analytics/tui.py` (render_snapshot, run_tui_from_candles, demo main). Tests: `tests/test_tui_render.py`. Demo: `python -m okx_collector.analytics.tui`. Windows-stable fixed-tick refresh; no ingestion/CLI changes.
5. **Phase B — Alert config + state store (done):** Env-based config: `okx_collector/alerts/config.py` (AlertsConfig, from_env, redacted webhook). Persisted state: `okx_collector/analytics/state_store.py` (AlertState, WickStateItem, PoorLevelStateItem, SessionStateItem, merge_from_snapshot, load/save_alert_state, active_items); `okx_collector/storage/layout.py` path_alert_state. Tests: `tests/test_alert_state_store.py`. No ingestion/CLI/ws/rest changes.
6. **Phase C — Discord formatter + scheduler (done):** `okx_collector/alerts/format.py` (format_discord_message, _age_str), `discord.py` (send_discord_webhook, send_with_retry), `scheduler.py` (should_send, scheduler_tick, run_alert_scheduler). Entrypoint: `python -m okx_collector.alerts.scheduler`. Tests: `tests/test_alert_format.py`, `tests/test_alert_scheduler_gating.py`. Runbook §2a (env), §2b (Discord Alerts). No ingestion/CLI/ws/rest changes.
7. **Phase D — State writer (done):** `okx_collector/alerts/state_writer.py`: reads stored candles via `path_candles` + latest partition, `writer_tick` builds snapshot, merges, saves `meta/alert_state.json`. Entrypoint: `python -m okx_collector.alerts.state_writer`. Test: `tests/test_state_writer_tick.py`. Runbook: State Writer section. No ingestion/CLI/ws/rest changes.
8. **Terminal Alert Dashboard (Option 1, done):** `okx_collector/alerts/dashboard_tui.py`: read-only Rich TUI; `render_alert_dashboard`, `load_state_for_dashboard`, `run_dashboard_tui`; fixed-tick Live loop; .env in __main__. Test: `tests/test_alert_dashboard_tui_render.py`. Runbook: "Terminal Alert Dashboard (read-only)". No writes; no ingestion/CLI/ws/rest changes.
9. **Terminal Alert Dashboard (Option 2, done):** Health panel: `load_health_for_dashboard`, `render_health_panel` (Rich Table: service, status, msg_count, last_msg_age, last_error); `HEALTH_PATH_REL` env; dashboard loads and displays `meta/health.json` when present. Test: `tests/test_alert_dashboard_health_panel.py`. Runbook updated. Read-only.
10. **Terminal Alert Dashboard (Option 3, done):** Live snapshot panel: env `DASH_LIVE_SNAPSHOT` (default 0), `DASH_LIVE_TICKER`, `DASH_LIVE_TIMEFRAME`, `DASH_LIVE_MAX_CANDLES`; `load_latest_candles_for_dashboard` (candles dir + latest partition, CandlesFile); `render_live_snapshot_panel` (disabled / missing / content); `build_snapshot` when enabled; single redraw per tick. Test: `tests/test_alert_dashboard_live_snapshot_panel.py`. Runbook: Option 3 subsection. Read-only.
11. **Pro dashboard summary + Discord status (done):** Top summary line `[INGEST] [STATE] [DISCORD]` and header line `Discord: configured` or `not configured`; stale threshold `max(3×refresh_s, 90)s`; no webhook URL ever shown. Test: `tests/test_alert_dashboard_tui_render.py`. See `docs/PLAN_STARTUP_AND_DASHBOARD.md`. Read-only.
12. **Phase 5 — CI + replay + docs:** Lint + pytest in CI; replay test in CI; runbook sections for analytics and TUI.

## NOT DOING

- Changing ingestion behavior, CLI contract, or storage paths for existing candles/trades/BBO/book/meta.
- Backfilling beyond configurable start_date (single run scope for now).

---

**Claims↔Evidence:** Plan and next tasks align to ROADMAP.md and AUDIT_REPORT.md.  
**Gaps:** TUI not yet implemented.  
**Next Step:** Phase 4 — TUI dashboard (snapshot: current session, untouched wicks, poor extremes, validator summary); Windows-stable refresh.
