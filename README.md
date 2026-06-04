# youhooalert API

FastAPI backend for [street-angels-ui](../street-angels-ui) (youhooalert web app). Mirrors the UI’s `/api` routes.

## Quick start

```bash
cd c:/nextsree/street-angels-api
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

- API docs: http://localhost:8000/docs
- Health: http://localhost:8000/health
- DB health: http://localhost:8000/health/db

## Connect Vercel Postgres

1. In the [Vercel dashboard](https://vercel.com), open your project → **Storage** → your Postgres database.
2. Open the **`.env.local`** tab (or connect the DB to the project so variables are injected).
3. Copy **`DATABASE_URL`** (pooled) and **`DATABASE_URL_UNPOOLED`** (direct) into `street-angels-api/.env`:

```env
DATABASE_URL=postgresql://...@host-pooler.../neondb?sslmode=require
DATABASE_URL_UNPOOLED=postgresql://...@host.../neondb?sslmode=require
```

4. Run migrations: `alembic upgrade head`
5. Restart the API. `/health` should show `"storage": "postgres"`.
6. Hit `/health/db` to confirm the connection.

## Database migrations (Alembic)

Schema is managed with Alembic — not `create_all` on startup.

| Command | Purpose |
|---------|---------|
| `alembic upgrade head` | Apply all pending migrations |
| `alembic revision --autogenerate -m "describe change"` | Generate migration from model changes |
| `alembic current` | Show current revision |
| `alembic history` | List migrations |

Use **`DATABASE_URL_UNPOOLED`** in `.env` when running Alembic (Neon direct connection). The API runtime still uses pooled **`DATABASE_URL`**.

**Existing database** (tables already created before Alembic):

```bash
# If schema matches migration 002 (includes suspended column)
alembic stamp head

# If tables exist but users.suspended is missing
alembic stamp 001
alembic upgrade head
```

**Check / create tables** (uses `.env` URLs):

```bash
python scripts/db_setup.py
```

**Tables missing in Neon console?** The API uses whatever `DATABASE_URL` is set in Vercel — often database name `neondb`, not the project display name. In Neon → your project → **Branches** → **production** → **SQL Editor**, run:

```sql
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public' ORDER BY 1;
```

Pull production env and migrate that database:

```bash
npx vercel link
npx vercel env pull .env.production
# Copy DATABASE_URL and DATABASE_URL_UNPOOLED into .env, then:
alembic upgrade head
```

### Pull env from Vercel CLI (optional)

```bash
cd c:/nextsree/street-angels-api
npx vercel env pull .env
```

Keep only `DATABASE_URL`, `DATABASE_URL_UNPOOLED`, and `CORS_ORIGINS` (ignore duplicate `POSTGRES_*` / `PG*` vars from the template).

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/auth/register` | Register (sets `sa_session` cookie) |
| POST | `/api/auth/login` | Login or auto-register |
| POST | `/api/auth/logout` | Clear session |
| GET | `/api/auth/me` | Current user |
| PATCH | `/api/users/me` | Update profile |
| GET/POST | `/api/contacts` | List / add contacts |
| PATCH/DELETE | `/api/contacts/{id}` | Update / delete contact |
| POST | `/api/emergencies` | Start SOS emergency |
| GET | `/api/emergencies/active` | Active emergency |
| PATCH | `/api/emergencies/{id}` | Resolve or cancel |

Session auth uses the `sa_session` HTTP-only cookie (same as the UI mock).

## Storage modes

| Env | Behavior |
|-----|----------|
| `DATABASE_URL` set | PostgreSQL (persistent) |
| Neither set | In-memory (resets on restart) |

## Connect the UI

The Next.js app proxies `/api/*` to this server when `API_URL` is set in the UI project.

**Local dev** — in `street-angels-ui/.env.local`:

```env
API_URL=http://localhost:8000
```

Run both servers (API on `:8000`, UI on `:3000`), then open http://localhost:3000.

**Vercel** — set `API_URL=https://api.youhooalert.com` on the UI project. Set `CORS_ORIGINS=https://youhooalert.com,http://localhost:3000` on this API project.

Set `ADMIN_EMAILS` to comma-separated emails that can access `/api/admin/*` and see `isAdmin: true` on `/api/auth/me`.

New users no longer receive sample contacts — they add their own via the UI.

Default CORS allows `http://localhost:3000` and `http://127.0.0.1:3000`. Override in `.env`:

```
CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000,https://youhooalert.com
```

## Deploy on Vercel

1. Import this repo as a Vercel project.
2. Connect your Neon database (Storage) so `DATABASE_URL` and `DATABASE_URL_UNPOOLED` are injected.
3. Add `CORS_ORIGINS` with your UI production URL.
4. Run migrations before or after first deploy: `alembic upgrade head` (locally or in CI with unpooled URL).
5. Deploy — Vercel auto-detects FastAPI via `app.main:app` (`pyproject.toml`).

Health checks after deploy:

- `GET /health` → `"storage": "postgres"`
- `GET /health/db` → `"status": "ok"`

## Notes

- Password fields are accepted but not validated yet (matches the UI mock behavior).
- Use the **pooled** `DATABASE_URL` from Vercel for the running API.
