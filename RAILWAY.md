# Deploy youhooalert API to Railway

## 1. Push code to GitHub

Repo: https://github.com/SreekanthDomalapally/street-angels-api

```bash
git add .
git commit -m "Prepare Railway deployment"
git push origin main
```

## 2. Create Railway project

1. [railway.app](https://railway.app) → **New Project**
2. **Deploy from GitHub repo** → select `street-angels-api`
3. Railway detects **`Dockerfile`** and builds automatically

## 3. Add PostgreSQL (if not already)

1. In the project → **+ New** → **Database** → **PostgreSQL**
2. Or use your existing Postgres service

## 4. Link Postgres to the API service

On the **API service** → **Variables** → **Add variable reference**:

| Variable | Value |
|----------|--------|
| `DATABASE_URL` | `${{ Postgres.DATABASE_URL }}` |

Railway uses the **private** network URL inside the project.

## 5. Required environment variables (API service)

Set these on the **API** service (not Postgres):

| Variable | Example / notes |
|----------|-----------------|
| `DATABASE_URL` | `${{ Postgres.DATABASE_URL }}` (reference) |
| `JWT_SECRET_KEY` | **Required** — random 32+ char secret (`openssl rand -hex 32`). API will start without it but `/health` reports `degraded` and auth is insecure |
| `ENVIRONMENT` | Optional — auto-detected from Railway's `RAILWAY_ENVIRONMENT_NAME` when unset |
| `CORS_ORIGINS` | `https://youhooalert.com,http://localhost:3000` |
| `REDIS_URL` | `${{ Redis.REDIS_URL }}` — required for SOS push |
| `PUSH_ENABLED` | `true` |
| `DEV_OTP_ENABLED` | `true` during internal testing — shows login code in app (no SMS). **Set `false` before public launch** |

Remove unused vars: `FCM_ENABLED` (not read by this API).

Optional: `GOOGLE_OAUTH_CLIENT_ID`, `STRIPE_SECRET_KEY`, `FIREBASE_CREDENTIALS_JSON`

**Do not** commit `.env` — set vars in Railway dashboard only.

## 6. Migrations

Run once against Railway Postgres (from your machine with **public** URL):

```bash
# .env uses DATABASE_PUBLIC_URL locally
alembic upgrade head
python scripts/seed.py   # optional demo data
```

Already done if you migrated `acela.proxy.rlwy.net`.

## 7. Verify deploy

Railway gives a URL like `https://street-angels-api-production.up.railway.app`

```bash
curl https://YOUR-RAILWAY-URL/health
curl https://YOUR-RAILWAY-URL/health/db
curl https://YOUR-RAILWAY-URL/health/notifications
```

- `/health` → `{"status":"ok","environment":"production"}`
- `/health/db` → `{"status":"ok","storage":"postgres"}`
- `/health/notifications` → Redis, worker, push tokens, queue depth, and actionable `issues` (503 if critical failures)
- `/docs` → Swagger UI

## 8. Custom domain (optional)

API service → **Settings** → **Networking** → **Generate domain** or add `api.youhooalert.com`

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Build fails | Check Railway build logs; ensure `requirements.txt` is valid |
| DB connection error | Link Postgres; use `${{ Postgres.DATABASE_URL }}` on API service |
| App crashes on start (502) | Set `JWT_SECRET_KEY` (32+ chars); check Railway deploy logs |
| `/health` shows `degraded` | Set `JWT_SECRET_KEY` — see issues array in response |
| Push notifications fail | Add `REDIS_URL` + Redis service |
| CORS errors from mobile/web | Add origin to `CORS_ORIGINS` |
