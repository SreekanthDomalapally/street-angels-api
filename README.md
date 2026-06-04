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

## Connect the UI

Point the Next.js app at this server (e.g. proxy `/api` to `http://localhost:8000/api` in `next.config` or set `NEXT_PUBLIC_API_URL` if you add a fetch base URL).

Default CORS allows `http://localhost:3000`. Override in `.env`:

```
CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
```

## Notes

- In-memory store (resets on restart); suitable for local dev.
- Password fields are accepted but not validated yet (matches the UI mock behavior).
