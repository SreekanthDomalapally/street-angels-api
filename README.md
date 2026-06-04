# Street Angels API

FastAPI backend for [street-angels-ui](../street-angels-ui). Mirrors the Next.js mock API routes under `/api`.

## Quick start

```bash
cd c:/nextsree/street-angels-api
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload --port 8000
```

- API docs: http://localhost:8000/docs
- Health: http://localhost:8000/health
- DB health: http://localhost:8000/health/db

## Connect Vercel Postgres

1. In the [Vercel dashboard](https://vercel.com), open your project → **Storage** → your Postgres database.
2. Open the **`.env.local`** tab (or connect the DB to the project so variables are injected).
3. Copy **`POSTGRES_URL`** (or `DATABASE_URL`).
4. Paste into `street-angels-api/.env`:

```env
POSTGRES_URL=postgresql://...
```

5. Restart the API. `/health` should show `"storage": "postgres"`.
6. Hit `/health/db` to confirm the connection.

Tables (`users`, `sessions`, `contacts`, `emergencies`) are created automatically on startup.

### Pull env from Vercel CLI (optional)

```bash
cd c:/nextsree/street-angels-api
npx vercel env pull .env
```

Then keep only the `POSTGRES_URL` line you need (and add `CORS_ORIGINS` if missing).

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
| `POSTGRES_URL` or `DATABASE_URL` set | PostgreSQL (persistent) |
| Neither set | In-memory (resets on restart) |

## Connect the UI

Point the Next.js app at this server (e.g. proxy `/api` to `http://localhost:8000/api` in `next.config` or set `NEXT_PUBLIC_API_URL` if you add a fetch base URL).

Default CORS allows `http://localhost:3000`. Override in `.env`:

```
CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
```

## Notes

- Password fields are accepted but not validated yet (matches the UI mock behavior).
- Use the **pooled** `POSTGRES_URL` from Vercel for the running API.
