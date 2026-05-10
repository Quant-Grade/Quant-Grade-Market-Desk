# Controlled Run Supervisor

This module serves as a strictly-bounded foreground daemon designed to execute the `Operator Run Profiles` across a repeated interval.

### Core Behaviors:
- **Foreground Only:** It is NOT a background service or Windows daemon. It runs natively in the active terminal context.
- **Strict Bounds:** Requires a `--max-runs` parameter to avoid infinite loops and unintentional spam.
- **Fail-Closed by Default:** By default, any execution failure in the downstream operator layers causes the supervisor to safely halt its loop instantly, ensuring the system does not cascade errors.
- **Decoupled Security:** Never interacts with the lower-level pipeline mechanisms or variables directly. It purely acts as an automated trigger for the safe `ops.operator_run_profiles` CLI layer.
