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

### API Endpoints
- `POST /api/auth/register/`
- `POST /api/auth/login/`
- `POST /api/auth/refresh/`
- `GET /api/auth/me/`
- `GET /api/auth/fleets/`
- `POST /api/auth/request-code/`
- `POST /api/auth/verify-code/`
- `GET /api/wallet/balance/`
- `GET /api/wallet/bank-accounts/`
- `POST /api/wallet/bank-accounts/`
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
- `GET /api/integrations/yandex/sync-runs/` (list Yandex sync history runs)
- `GET /api/integrations/yandex/events/`
- `POST /api/integrations/yandex/simulate-events/`
- `POST /api/integrations/yandex/import/`
- `GET /api/integrations/yandex/reconcile/`
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
```

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
