# SIGL Letter Management

This is a small Flask/SQLite intranet backend for routing scanned agency letters
through the SIGL role hierarchy:

`front_desk -> department_head -> team_member -> md_pa -> md -> finalized PDF`

## Run

1. Create a virtual environment and install `requirements.txt`.
2. Set a strong `SECRET_KEY` and a writable `LETTER_DATABASE` path.
3. Run `flask --app app run --host 127.0.0.1`.
4. Run `pytest`.

For Windows development, activate the environment with
`.venv\Scripts\Activate.ps1`. For an intranet deployment, run behind a
reverse proxy with TLS and set `SECRET_KEY` through the service manager rather
than checking it into a file.

Set `SEED_DEMO_DATA=1` only for local development. It creates demo users with
the password `change-me`; do not enable it in production.

Every mutation is checked in the workflow service, records an audit event, and
is scoped by department unless the user is the MD or MD PA. The intake record
stores the scanned source bytes and a SHA-256 integrity hash. Approval generates
and stores a PDF blob, changes the status to `finalized`, and prevents further
response edits. The production deployment should put the app behind HTTPS,
replace demo authentication with the intranet identity provider, configure
backups for SQLite (or migrate the same schema to PostgreSQL), and store
uploaded source files in controlled encrypted storage. The included interface
is available at `/`; it intentionally exposes only scope-filtered letter data.
`SALES_NOTIFICATION_WEBHOOK` is reserved for connecting an approved internal
notification adapter; this code does not send business-initiated WhatsApp
messages.

Uploads retain the original scan and automatically create an editable `.docx`
copy. Text PDFs are extracted directly; image-only PDFs and image files use
Tesseract OCR when the Tesseract executable is installed on the host. If OCR
is unavailable or cannot read a scan, the Word file is still created with a
clear manual-transcription note, and the original scan remains available.
Front Desk and the MD PA can route intake records to any department. The
initial department catalogue includes Administration, Finance and Accounts,
Sales and Marketing, HR, and Civil; additional departments can be created by
an administrator.

Production settings are represented in `.env.example`. Set `DATABASE_URL` to a
PostgreSQL connection string and `AUTH_MODE=entra` when the intranet identity
provider is ready; local mode remains available for development. The current
SQLite adapter is intentionally retained as the tested development path while
the PostgreSQL repository migration is staged separately.

## Vercel deployment

Vercel uses [api/index.py](./api/index.py) as the WSGI entrypoint. Configure
these Vercel environment variables before deploying:

```text
SECRET_KEY=<long-random-value>
SEED_DEMO_DATA=1
VERCEL=1
```

`SEED_DEMO_DATA=1` creates the local demonstration accounts and must not be
used for production. Vercel's `/tmp` SQLite fallback is ephemeral and is only
for demos; production must provide a persistent PostgreSQL or network database
and set `LETTER_DATABASE` or complete the PostgreSQL adapter before relying on
stored letters.
