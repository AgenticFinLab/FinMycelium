# Suggested PR description

Person Event v2 separates evidence claims from source-specific citations and
supports cross-source evidence consolidation. Long model runs preserve usable
results across partial failures and resumes.

- Model calls run through a FIFO coordinator with isolated, killable transports.
- Saved responses, reading progress and budgets survive interruption.
- Errors expose provider codes and request IDs; a read-only status command shows
  effective budgets, current failures and previously rendered artifacts.
- Execution and rendering fingerprints are separated. The engineering cleanup
  retains extraction, adoption, merge and conflict decisions.

Validation: `python scripts/check_person_event.py` runs offline regression checks.
For a real run, follow [operations](person-event-operations.md): build from the
original `input.json`, inspect status, resume incomplete work and render a saved
graph independently. Model-backed commands require `.env` credentials and incur
provider charges; status and saved-JSON rendering are offline.
