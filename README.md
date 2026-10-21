# SIGL Letter Management

This is a small Flask/SQLite intranet backend for routing scanned agency letters
through the SIGL role hierarchy:

`front_desk -> department_head -> team_member -> md_pa -> md -> finalized PDF`

## Registers

Letters live in two registers, both in the `letters` table (`direction`):

- **Incoming** (received): registered by the front desk with the details on the
  letter (locked afterwards; the MD or MD PA can correct them), routed to a
  department and assigned. Action required, deadline, status
  (open/closed/responded) and remarks are tracked throughout.
- **Outgoing** (sent): a new letter, or a reply started with **Respond** on a
  received letter (`in_reply_to`). Each gets an *our reference*
  `SIGL/<institution initials>/<department code>/<serial>`, the serial counted
  per institution. It is drafted in Word on letterhead, sent for approval
  (MD PA, then MD, who can approve or return it), finalised as a locked PDF,
  then dispatched (method, date) and tracked to delivery (date, note, optional
  proof) before being closed.

On approval a reply's Word draft is deleted, as the original process required;
a new letter keeps an approved Word copy alongside the PDF.

## Run

1. Create a virtual environment and install `requirements.txt`.
2. Set a strong `SECRET_KEY`, and either `DATABASE_URL` or a writable
   `LETTER_DATABASE` path (see [Database](#database)).
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

Production settings are represented in `.env.example`.

### Sign in with Microsoft

Staff can sign in with their Microsoft 365 (Entra ID) accounts. In the Azure
portal, register an app (Entra ID > App registrations > New registration,
single tenant) with the web redirect URI
`https://<your-domain>/auth/microsoft/callback`, create a client secret, and set
`ENTRA_TENANT_ID`, `ENTRA_CLIENT_ID`, `ENTRA_CLIENT_SECRET` and `APP_BASE_URL`.

A Microsoft account gets in only if a Letter Desk user has the same email
address; the first sign-in links them. Password sign-in stays available until
`AUTH_MODE=entra` is set, so set that once everyone has signed in successfully.

## Database

When `POSTGRES_URL` or `DATABASE_URL` is set, the app uses PostgreSQL
([schema_postgres.sql](./schema_postgres.sql)); otherwise it uses SQLite at
`LETTER_DATABASE` ([schema.sql](./schema.sql)). The schema is created
automatically on startup.

To run locally against the same database as Vercel:

```text
vercel env pull .env.local
.venv\Scripts\python app.py
```

`python app.py` loads `.env.local`. Anything done locally then changes the live
data.

To copy an existing local SQLite database into PostgreSQL once:

```text
.venv\Scripts\python migrate_to_postgres.py
```

### Large scans (Supabase Storage)

Vercel rejects request and response bodies over 4.5 MB. Set `SUPABASE_URL` and
`SUPABASE_SECRET_KEY` (or `SUPABASE_SERVICE_ROLE_KEY`) and the browser uploads
scans straight to a private `letters` bucket, which the app creates on first
use; downloads are redirected to short-lived signed URLs. Without these
settings, scans are stored in the database and uploads over 4.5 MB fail on
Vercel.

Tests always use a temporary SQLite file. To run them against PostgreSQL, point
`TEST_DATABASE_URL` at a disposable database; the tests drop its `public` schema.

## Vercel deployment

Vercel uses [api/index.py](./api/index.py) as the WSGI entrypoint. Configure
these Vercel environment variables before deploying:

```text
SECRET_KEY=<long-random-value>
POSTGRES_URL=<PostgreSQL connection string, set by the Supabase or Neon integration>
SEED_DEMO_DATA=1
```

`SEED_DEMO_DATA=1` creates the demonstration accounts (password `change-me`)
and must not be used for production. Without a PostgreSQL URL, Vercel falls
back to SQLite in `/tmp`, which is wiped between instances and is only for demos.

The application initializes and verifies the database schema on every cold start.
After changing deployment configuration, create a new Vercel deployment rather
than relying on a previous function instance.
