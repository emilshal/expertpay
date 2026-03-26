# ExpertPay (skeleton)

React app skeleton for an ExpertPay-style product (Yandex taxi fleet owners → ExpertPay → bank payouts).

## Prereqs
- Node.js 18+

## Start
```bash
npm install
npm run dev
```

Optional frontend API base:
```bash
VITE_API_BASE_URL=http://127.0.0.1:8000 npm run dev
```

## Build
```bash
npm run build
npm run preview
```

## Backend (Django API)
First backend slice includes JWT auth and wallet balance endpoint.

### Setup
```bash
python3 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements.txt
cd backend
../backend/.venv/bin/python manage.py migrate
../backend/.venv/bin/python manage.py runserver
```

### PostgreSQL (recommended local setup)
```bash
cp backend/.env.example backend/.env
docker compose up -d postgres
cd backend
../backend/.venv/bin/pip install -r requirements.txt
../backend/.venv/bin/python manage.py migrate
../backend/.venv/bin/python manage.py runserver
```

This uses PostgreSQL on `localhost:5433` with:
- DB: `expertpay`
- User: `expertpay`
- Password: `expertpay`

`DJANGO_SECRET_KEY` should be a long random value. In local dev, the example file uses a long placeholder to avoid weak-key JWT warnings. When `DJANGO_DEBUG=false`, the backend now refuses to start if `DJANGO_SECRET_KEY` is missing, left on the default placeholder, or shorter than 32 characters.

### API Endpoints
- `POST /api/auth/register/`
- `POST /api/auth/login/`
- `POST /api/auth/refresh/`
- `GET /api/auth/me/`
- `GET /api/auth/fleets/`
- `POST /api/auth/request-code/`
- `POST /api/auth/verify-code/`
- `GET /api/auth/fleet-members/?fleet_name=<name>` (admin/owner only)
- `PATCH /api/auth/fleet-members/role/` (admin/owner only)
- `GET /api/auth/driver-mappings/?fleet_name=<name>` (admin/owner only)
- `PATCH /api/auth/driver-mappings/<binding_id>/` (admin/owner only)
- `GET /api/wallet/balance/`
- `GET /api/wallet/bank-accounts/`
- `POST /api/wallet/bank-accounts/`
- `GET /api/wallet/deposit-instructions/`
- `GET /api/wallet/deposits/`
- `POST /api/wallet/deposits/sync/`
- `GET /api/wallet/transactions/`
- `POST /api/wallet/top-up/` (sandbox testing credit)
- `POST /api/wallet/withdrawals/`
- `GET /api/wallet/withdrawals/list/`
- `PATCH /api/wallet/withdrawals/<id>/status/` (staff/admin flow)
- `POST /api/transfers/internal/`
- `POST /api/transfers/internal/by-bank/`
- `POST /api/integrations/yandex/connect/`
- `POST /api/integrations/yandex/test-connection/` (live credential health check)
- `POST /api/integrations/yandex/sync-live/` (live driver + transaction sync into external events + ledger; supports incremental cursor sync)
- `POST /api/integrations/yandex/sync-categories/` (sync transaction categories from Yandex)
- `GET /api/integrations/yandex/categories/` (list synced categories)
- `GET /api/integrations/yandex/drivers/` (list normalized synced driver profiles)
- `GET /api/integrations/yandex/transactions/` (list normalized synced transaction records)
- `GET /api/integrations/yandex/sync-runs/` (list Yandex sync history runs)
- `GET /api/integrations/yandex/events/`
- `POST /api/integrations/yandex/simulate-events/`
- `POST /api/integrations/yandex/import/`
- `GET /api/integrations/yandex/reconcile/`
- `POST /api/integrations/yandex/purge-simulated/`
- `POST /api/integrations/bog/test-token/` (Bank of Georgia client-credentials token health check)
- `GET /api/integrations/bog/payouts/`
- `POST /api/integrations/bog/payouts/submit/`
- `POST /api/integrations/bog/payouts/sync-all/`
- `POST /api/integrations/bog/payouts/<id>/status/`
- `POST /api/integrations/bank-sim/connect/`
- `GET /api/integrations/bank-sim/payouts/`
- `POST /api/integrations/bank-sim/payouts/submit/`
- `POST /api/integrations/bank-sim/payouts/<id>/status/`
- `GET /api/integrations/reconciliation/summary/`

### Idempotency (money endpoints)
For money-changing requests, include:
- `Idempotency-Key: <unique-value-per-request>`
- `X-Request-ID: <optional-trace-id>`

Applied to:
- `POST /api/wallet/withdrawals/`
- `POST /api/transfers/internal/`
- `POST /api/integrations/yandex/simulate-events/`
- `POST /api/integrations/yandex/import/`

### Fleet login demo data (seeded)
- Fleet name: `New Tech`
- Phone number: `+995598950001`
- OTP code (dev): `123456`

### Fleet role model
Fleet membership is phone-binding based, and role is fleet-scoped on each binding:
- `driver`
- `operator`
- `admin`
- `owner`

Notes:
- Phone in DB + active binding allows login for that fleet.
- `admin`/`owner` can view fleet members and update member roles.
- `admin` cannot assign or modify `owner` role.
- Money write guards:
  - transfers + withdrawals + bank-account create: `operator` or higher
  - wallet top-up (sandbox credit): `admin` or higher
  - Yandex write actions (test/sync/categories): `admin` or higher

### Yandex data persisted locally
Live sync stores:
- normalized driver profiles (`YandexDriverProfile`)
- normalized transaction records (`YandexTransactionRecord`)
- transaction categories (`YandexTransactionCategory`)
- sync run history (`YandexSyncRun`)
- raw source payloads for audit/debug

Core normalized transaction fields:
- `external_transaction_id`
- `driver_external_id`
- `event_at`
- `amount`
- `currency`
- `category`
- `direction`

### Yandex live connection env
Set these in `backend/.env` before running a live credential check:

```env
YANDEX_ENABLED=true
YANDEX_MODE=live
YANDEX_BASE_URL=https://fleet-api.taxi.yandex.net
YANDEX_PARK_ID=...
YANDEX_CLIENT_ID=...
YANDEX_API_KEY=...
YANDEX_REQUEST_TIMEOUT_SECONDS=20
YANDEX_MAX_RETRIES=3
YANDEX_RETRY_BASE_SECONDS=0.5

THROTTLE_ANON=120/hour
THROTTLE_USER=1200/hour
THROTTLE_AUTH_OTP_REQUEST=30/hour
THROTTLE_AUTH_OTP_VERIFY=60/hour
THROTTLE_MONEY_WRITE=240/hour
THROTTLE_MONEY_STATUS_WRITE=120/hour
THROTTLE_YANDEX_WRITE=180/hour
THROTTLE_YANDEX_READ=600/hour

LOG_LEVEL=INFO
SENTRY_DSN=
SENTRY_TRACES_SAMPLE_RATE=0.0
```

### Bank of Georgia token test env
Set these in `backend/.env` before running the BoG token health check:

```env
BOG_ENABLED=true
BOG_TOKEN_URL=https://account.bog.ge/auth/realms/bog/protocol/openid-connect/token
BOG_BASE_URL=https://api.businessonline.ge/api
BOG_CLIENT_ID=...
BOG_CLIENT_SECRET=...
BOG_SCOPE=
BOG_REQUEST_TIMEOUT_SECONDS=20
```

The token test endpoint only verifies that BoG returns an access token. It does not store the raw token.

BoG payout submission additionally needs:

```env
BOG_SOURCE_ACCOUNT_NUMBER=...
BOG_PAYER_INN=...
BOG_PAYER_NAME=
BOG_DOCUMENT_PREFIX=EXP
BOG_DEPOSIT_REFERENCE_PREFIX=EXP
```

Saved beneficiary bank accounts also need a `beneficiary_inn` value for domestic transfer submission.
Users making deposits should include the exact generated reference code from the app in their bank transfer comment/nomination.

### Incremental live sync scheduler
Manual run:

```bash
cd backend
../backend/.venv/bin/python manage.py sync_yandex_live --limit 100
```

Full backfill window run:

```bash
cd backend
../backend/.venv/bin/python manage.py sync_yandex_live --limit 200 --full-sync
```

Cron example (every 10 minutes):

```bash
*/10 * * * * cd /Users/emilshalamberidze/Desktop/expertpay/backend && /Users/emilshalamberidze/Desktop/expertpay/backend/.venv/bin/python manage.py sync_yandex_live --limit 100 >> /tmp/expertpay-sync.log 2>&1
```

### Automatic background sync jobs
The backend now has a single production-friendly scheduler entry point that reuses the existing sync services:

```bash
cd backend
../backend/.venv/bin/python manage.py run_integration_sync_jobs
```

This runs:
- Yandex live earnings sync
- BoG incoming deposit sync
- BoG payout status sync

Useful scopes:

```bash
../backend/.venv/bin/python manage.py run_integration_sync_jobs --job yandex
../backend/.venv/bin/python manage.py run_integration_sync_jobs --job bog_deposits
../backend/.venv/bin/python manage.py run_integration_sync_jobs --job bog_payouts
../backend/.venv/bin/python manage.py run_integration_sync_jobs --user-id 1
../backend/.venv/bin/python manage.py run_integration_sync_jobs --fleet-name "New Tech"
../backend/.venv/bin/python manage.py run_integration_sync_jobs --connection-id 12
../backend/.venv/bin/python manage.py run_integration_sync_jobs --include-inactive
```

Yandex-specific options:

```bash
../backend/.venv/bin/python manage.py run_integration_sync_jobs --job yandex --limit 200 --full-sync
../backend/.venv/bin/python manage.py run_integration_sync_jobs --job yandex --dry-run
```

Each run is safe to repeat because it reuses the existing idempotent sync services and records last-run details into each provider connection config:
- `last_live_sync`
- `last_deposit_sync`
- `last_payout_sync`

Cron example for automatic production polling (every 5 minutes):

```bash
*/5 * * * * cd /Users/emilshalamberidze/Desktop/expertpay/backend && /Users/emilshalamberidze/Desktop/expertpay/backend/.venv/bin/python manage.py run_integration_sync_jobs >> /tmp/expertpay-background-sync.log 2>&1
```

### BoG payout status polling
Manual run:

```bash
cd backend
../backend/.venv/bin/python manage.py sync_bog_payouts
```

### BoG incoming-transfer deposits
Manual deposit sync:

```bash
cd backend
../backend/.venv/bin/python manage.py sync_bog_deposits --user-id 1
```

Date-range recovery backfill for missed or delayed transfers:

```bash
cd backend
../backend/.venv/bin/python manage.py sync_bog_deposits --user-id 1 --start-date 2026-03-01 --end-date 2026-03-05
```

Notes:
- normal sync uses BoG today-activity polling
- backfill uses the BoG statement/date-range endpoint
- rerunning a backfill is safe because deposit completion stays idempotent by `provider_transaction_id`
- unmatched recovered transfers still go to the normal deposit review queue for manual matching

### Live money smoke test checklist
Use this runbook when you want to validate one real small fleet funding and one real small driver payout end to end.

Recommended safety rules:
- use one active fleet and one mapped driver only
- use small GEL amounts
- wait for each state change before moving to the next step
- keep `Idempotency-Key` values unique if you call money APIs directly

Operator sequence:

1. Confirm the fleet and driver setup
   - Owner login: open `Dashboard`, `Deposits`, and `Payouts`
   - Driver login: open `My Wallet`
   - Owner/admin only: confirm the driver exists in `Team Access`
   - Owner/admin only: open `Driver Mappings` and verify the driver has the correct Yandex external driver ID

2. Fund the fleet with a small BoG transfer
   - In `Deposits`, copy the exact fleet reference code
   - Send a small transfer into the company BoG account with that exact reference in the transfer comment
   - Expected state:
     - transfer appears after BoG sync
     - if matched automatically, fleet reserve increases
     - if reference is missing or stale, it appears in `Deposit Review`

3. Sync deposits
   - Normal polling:

   ```bash
   cd backend
   ../backend/.venv/bin/python manage.py sync_bog_deposits --user-id <owner_user_id>
   ```

   - Fleet-scoped smoke sequence:

   ```bash
   cd backend
   ../backend/.venv/bin/python manage.py run_money_smoke_sync --fleet-name "<fleet_name>" --skip-yandex --skip-payouts
   ```

   - Recovery backfill if the transfer was older or missed:

   ```bash
   cd backend
   ../backend/.venv/bin/python manage.py sync_bog_deposits --user-id <owner_user_id> --start-date YYYY-MM-DD --end-date YYYY-MM-DD
   ```

   - If still unmatched, open `Deposit Review` and assign it to the same fleet

4. Import Yandex earnings for the mapped driver
   - Owner/admin only: open `Yandex Overview` and run `Sync Latest Data`
   - CLI alternative:

   ```bash
   cd backend
   ../backend/.venv/bin/python manage.py sync_yandex_live --user-id <owner_user_id> --limit 100
   ```

   - Fleet-scoped smoke sequence:

   ```bash
   cd backend
   ../backend/.venv/bin/python manage.py run_money_smoke_sync --fleet-name "<fleet_name>" --skip-deposits --skip-payouts
   ```

   - Expected state:
     - the mapped driver’s `My Wallet` balance increases
     - the owner `Dashboard` still shows the same fleet reserve unless a payout happens
     - unmapped Yandex events stay stored for audit/debug and do not credit a driver

5. Submit one small driver withdrawal
   - Driver login: make sure a bank account is saved
   - In `My Wallet`, request a small withdrawal less than or equal to:
     - driver available balance
     - fleet reserve minus fleet-paid fee
   - Expected state immediately after submit:
     - withdrawal appears as `Requested` or `Processing`
     - driver available balance drops by principal only
     - fleet reserve is held for principal plus fee

6. Send or poll the BoG payout
   - Owner/admin only: open `Payouts`
   - Use `Send to BoG` if the payout has not been submitted yet
   - Use `Refresh all open BoG payouts` to poll live status
   - CLI alternative:

   ```bash
   cd backend
   ../backend/.venv/bin/python manage.py sync_bog_payouts --user-id <owner_user_id>
   ```

   - Fleet-scoped smoke sequence:

   ```bash
   cd backend
   ../backend/.venv/bin/python manage.py run_money_smoke_sync --fleet-name "<fleet_name>" --skip-deposits --skip-yandex
   ```

   - Expected state:
     - `Requested` or `Processing` while BoG is still open
     - `Completed` when BoG settles
     - `Failed` with a visible reason if BoG rejects or returns the payout

7. Confirm reconciliation
   - Owner/admin only: open `Reconciliation`
   - Verify:
     - treasury status is `OK`
     - fleet reserve reflects deposit minus payout minus fleet fee
     - driver available reflects earnings minus successful/pending withdrawal principal
     - payout clearing is zero after final settlement, or equals pending payouts if still open
     - platform fees reflect the fleet-paid withdrawal fee

8. If something looks wrong
   - Re-run the fleet-scoped smoke sync:

   ```bash
   cd backend
   ../backend/.venv/bin/python manage.py run_money_smoke_sync --fleet-name "<fleet_name>"
   ```

   - Check `Deposit Review` for unmatched incoming transfers
   - Check `Driver Mappings` if Yandex earnings did not land on the expected driver
   - Check `Payouts` for BoG failure reason or pending open payout
   - Check `Reconciliation` for which balance family is out of line

### CI
GitHub Actions workflow runs on push/PR:
- Django `check`
- integrations tests (SQLite)
- frontend build

### Simulator tests
Run integration tests (requires DB connection). If Postgres is not running locally, run tests with SQLite override:

```bash
cd backend
DB_ENGINE=django.db.backends.sqlite3 DB_NAME=db.sqlite3 DB_USER='' DB_PASSWORD='' DB_HOST='' DB_PORT='' ../backend/.venv/bin/python manage.py test integrations -v 2
```

### Remove old simulated Yandex data
If you want the app to reflect only live Yandex imports for a user:

```bash
cd backend
../backend/.venv/bin/python manage.py purge_yandex_simulated --user-id 1
```
