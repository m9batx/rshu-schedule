# RSHU Schedule

A schedule website for RSHU that converts the university's schedules from PDF files into an easy-to-use calendar format.

The main goal of this project is to take the existing schedule PDFs and automatically convert the information into a structured calendar schedule, making it easier to view and manage classes.

## Configuration (environment variables)

Do **not** commit secrets. Set these in the environment / a local `.env` (git-ignored):

| Variable | Purpose |
| --- | --- |
| `ADMIN_USER` | Admin login path (`/<ADMIN_USER>`). Default `admin`. |
| `ADMIN_PASSWORD_HASH` | bcrypt hash of the admin password. Generate with `python hash_password.py "your-password"`. Login is disabled if unset. |
| `SECRET_KEY` | Fixed Flask secret key (sessions/CSRF). Required in production and with multiple workers. |
| `SESSION_COOKIE_SECURE` | `1` (default) sends the session cookie over HTTPS only; set `0` for plain-HTTP local dev. |
| `WEB_CONCURRENCY` | gunicorn worker count (default `2`). |
| `DATA_DIR` | Directory holding `schedules.db` + uploads. Defaults to the app dir; falls back to `/tmp` if read-only. |

### Persistence

The SQLite database (schedules, **visitor statistics**, login attempts) and uploaded PDFs are stored in `DATA_DIR` (default `/app/data` in Docker). Use a **mounted volume** for it, otherwise the data is lost on every restart/redeploy:

```yaml
volumes:
  - appdata:/app/data   # named volume (survives restarts)
  # or:  - ./data:/app/data
```

Without a host path or volume, `/tmp`-style ephemeral storage drops the visitor logs.

## Run with Docker

```
ADMIN_USER=mohammedbekhit \
ADMIN_PASSWORD_HASH="$(python hash_password.py 'your-password')" \
SECRET_KEY="$(python -c 'import secrets;print(secrets.token_hex(32))')" \
docker compose up --build
```

The admin password hash that used to live in the source must be rotated.
