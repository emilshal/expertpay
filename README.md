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
