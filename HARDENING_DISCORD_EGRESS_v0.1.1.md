# Hardening Record: Discord Egress v0.1.1

- **Message Length Guard:** Added. Fail closed if rendered message > 1900 chars on send. Warnings emitted on dry-run.
- **Title Formatting:** Replaced em dash with plain hyphen to avoid Windows terminal encoding weirdness (`ASSET - EVENT_TYPE`).
- **Secret Safety Tests:** 
  - Verified webhook URL is never printed or logged.
  - Exception traces automatically sanitize out the webhook URL if it's somehow caught in the traceback string.
- **Tests Passed:** All 11 unit tests passed, including `test_oversized_message_blocks_send` and `test_webhook_url_not_present_in_log_output`.
- **Boundaries Check:** `boundaries_ok` (no core files touched).
