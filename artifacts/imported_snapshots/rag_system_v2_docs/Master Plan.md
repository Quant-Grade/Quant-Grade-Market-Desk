# Master Plan

High-level plan and checkpoints for the RAVEBEAR Monolith shipping path.

---

## Good stopping point (current state)

**Use this as the formal “pause here” checkpoint.** The system is runnable, testable, and documented. No half-finished features; CI and replay behavior are well-defined.

### What’s done

| Area | State |
|------|--------|
| **Monolith CLI** | Single pipeline: collect (dry/live) → events → 1s bars → SQLite. Modes: `live`, `replay`, `live-with-processing`. Replay runs once and exits. |
| **Replay** | Cursor-based resume; `db_max_ts_ms` vs cursor for “up to date”; exit 0 with `replay_up_to_date` when caught up. Flags: `--cursor-name`, `--cursor-reset`, `--from-start`. |
| **Heartbeat** | Structured log includes `collected_events_total`, `processed_bars_total`, `last_event_ts`, `last_bar_ts`, `db_path`. |
| **Config** | `config/settings.yaml` (default dry); `config/settings_live.yaml.example` for live OKX; `rb run-live` prefers live yaml or prints copy instructions. |
| **Tooling** | `rb` CLI (run-dry, run-live, replay, test, db-check); repo root by walking up to `pyproject.toml`; bootstrap.ps1 for Windows (py -3.12, Poetry, in-project venv). |
| **CI** | `.github/workflows/ci.yml`: ubuntu-latest + windows-latest, Python 3.12, `python -m poetry` throughout, cache `.venv`, `poetry install --no-interaction` and `poetry run pytest -q`. |
| **Docs** | MONOLITH_RUNBOOK (quickstart, verify DB, replay, cursor reset, Windows Python one-liner for DELETE cursor); SETUP; db_check hints; `replay_cursors` primary key `name` documented. |
| **Tests** | Orchestrator (heartbeat keys, kill switch, cancellation); replay runner (up-to-date exit, cursor_reset); CLI cursor_reset passed to runner. |

### Why this is a good stop

- **No open loops:** Replay is “run once and exit”; the only polling loop is in `live-with-processing`.
- **Clear contract:** Heartbeat and replay_up_to_date logs give a single health signal; cursor semantics and schema (`name` column) are documented.
- **Reproducible:** CI on two OSes; bootstrap and `rb` give a single way to run without PATH/venv guesswork.
- **Safe defaults:** Dry-run default; live requires explicit config copy; cursor reset is opt-in.

### Definition of done at this stop

- [ ] ACCEPTANCE.md checklist passes (run from clean clone, DB populated, Ctrl+C/kill switch, replay, tests).
- [ ] CI green on push/PR for `main`/`master`.
- [ ] MONOLITH_RUNBOOK and SETUP are the source of truth for “how to run” and “what to do when replay shows 0 events.”

### Next increments (after this stop)

- Optional: `replay-follow` mode (dedicated loop that re-invokes replay on an interval) if you want continuous catch-up without `live-with-processing`.
- Optional: More collectors or processors; extend config and CLI as needed.
- Optional: Observability (metrics/alerting) on heartbeat and replay_up_to_date.

---

*Last updated: checkpoint after replay cursor reset, heartbeat health keys, CI hardening, and runbook/Windows notes.*
