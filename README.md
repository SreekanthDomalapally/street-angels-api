# youhooalert API

Production backend for the youhooalert mobile emergency assistance platform.

## Stack

- **FastAPI** — async REST API + OpenAPI docs
- **PostgreSQL** — primary data store
- **SQLAlchemy 2** — async ORM
- **Alembic** — schema migrations
- **Redis** — notification queue with retry/DLQ
- **WebSockets** — live alert location updates
- **FCM** — push notifications (optional)
- **JWT** — access + refresh tokens
- **Google OAuth** — mobile sign-in
- **Stripe** — optional donations (never blocks core features)
- **Docker** — local full stack

## Quick start (Docker)

```bash
cp .env.example .env
docker compose up -d postgres redis
alembic upgrade head
python scripts/seed.py
uvicorn app.main:app --reload --port 8000
```

Or all services:

```bash
docker compose up --build
```

- API docs: http://localhost:8000/docs
- Health: http://localhost:8000/health

## Project structure

```
app/
  api/v1/          # HTTP routers (controllers)
  core/            # config, security, logging, errors, dependencies
  db/              # async session
  models/          # SQLAlchemy models
  repositories/    # data access
  services/        # business logic
  schemas/         # Pydantic DTOs
  websocket/       # live alert channels
  workers/         # Redis notification consumer
alembic/           # migrations
scripts/           # seed, db setup
```

## API overview (`/api/v1`)

| Area | Endpoints |
|------|-----------|
| **Auth** | `POST /auth/register`, `/login`, `/google`, `/refresh`, `GET /me`, `POST /devices` |
| **Users** | `GET/PATCH /users/me` |
| **Groups** | `POST/GET /groups`, members, invites |
| **Alerts** | `POST /alerts` (rate limited), responses, location, resolve |
| **Donations** | `POST /donations/checkout` |
| **WebSocket** | `WS /ws/alerts/{alert_id}?token=<jwt>` |

## Example: create SOS alert

```bash
# Login
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"demo@youhooalert.com","password":"demo12345"}' | jq -r .access_token)

# List groups
GROUP=$(curl -s http://localhost:8000/api/v1/groups -H "Authorization: Bearer $TOKEN" | jq -r '.[0].id')

# Trigger SOS
curl -X POST http://localhost:8000/api/v1/alerts \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"group_id\":\"$GROUP\",\"alert_type\":\"unsafe_situation\",\"latitude\":40.7128,\"longitude\":-74.0060}"
```

## Environment variables

See `.env.example`. Required for production:

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | Pooled Postgres (API runtime) |
| `DATABASE_URL_UNPOOLED` | Direct Postgres (Alembic) |
| `REDIS_URL` | Notification queue |
| `JWT_SECRET_KEY` | Token signing |
| `CORS_ORIGINS` | Allowed origins |

Optional: `GOOGLE_OAUTH_CLIENT_ID`, `FCM_ENABLED`, `FIREBASE_CREDENTIALS_PATH`, `STRIPE_SECRET_KEY`

## Migrations

```bash
alembic upgrade head          # apply
alembic revision --autogenerate -m "describe change"
python scripts/db_setup.py    # verify tables
```

**Note:** Migration `003` rebuilds the schema for the mobile platform (drops legacy web tables).

## Neon / Vercel

1. Set `DATABASE_URL` + `DATABASE_URL_UNPOOLED` on the API project
2. Add Redis (Upstash) → `REDIS_URL`
3. Run `alembic upgrade head` before deploy
4. Set `JWT_SECRET_KEY`, `CORS_ORIGINS`, optional FCM/Stripe/Google vars

## Reliability

- Alert notifications enqueued to Redis; worker retries failures to DLQ
- All alert lifecycle events logged in `alert_events`
- Audit trail in `audit_logs`
- Location updates throttled (configurable) to save battery
- Coordinates validated (rejects 0,0 and low accuracy)
- Rate limit on `POST /alerts` (default 5/minute per IP)
