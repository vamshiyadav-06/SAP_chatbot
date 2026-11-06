# Ubuntu staging operations

These scripts are deliberately scoped to the `sap_brim_staging` Compose project. They never run `down -v`, drop a database, or alter the production project. See [STAGING_DEPLOYMENT.md](../../docs/STAGING_DEPLOYMENT.md) before using them.

- `init-env.sh`: creates `.env` only when absent, with fresh random secrets and mode `0600`; it does not print secret values.
- `deploy.sh`: validates the private staging settings, builds, runs non-network preflight, deploys with `WEB_BIND=127.0.0.1`, and checks health.
- `with-public-bind.sh`: optional exposure after the operator separately opens the intended firewall rules; basic auth and disabled registration remain required.
- `test-load.py`: bounded authenticated GET load smoke (up to 1,000 requests and 25 workers); accepts HTTPS only and prints status/latency, never bodies or tokens.
- `test-recovery.sh`: takes a custom-format backup of staging, restores into a separate timestamped database, and retains both artifacts for inspection.

To run browser tests, set `COMPOSE_PROJECT_NAME=sap_brim_e2e` and use `docker-compose.e2e.yml` as an overlay on a separate, disposable E2E `.env`. That overlay points OpenRouter at `e2e/stub_llm/server.py`; it blanks all real provider keys and disables web fallback. The E2E project must not use the staging project name or volume. Install the Playwright Chromium browser with `npx playwright install chromium`.
