# ExpertPay (skeleton)

React app skeleton for an ExpertPay-style product (Yandex taxi fleet owners → ExpertPay → bank payouts).

## Prereqs
- Node.js 18+

## Start
```bash
npm install
npm run dev
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
- `GET /api/wallet/balance/`
- `GET /api/wallet/bank-accounts/`
- `POST /api/wallet/bank-accounts/`
- `GET /api/wallet/transactions/`
- `POST /api/wallet/withdrawals/`
- `GET /api/wallet/withdrawals/list/`
- `PATCH /api/wallet/withdrawals/<id>/status/` (staff/admin flow)
- `POST /api/transfers/internal/`

### Idempotency (money endpoints)
For money-changing requests, include:
- `Idempotency-Key: <unique-value-per-request>`
- `X-Request-ID: <optional-trace-id>`

Applied to:
- `POST /api/wallet/withdrawals/`
- `POST /api/transfers/internal/`
