PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS departments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    display_name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('front_desk', 'department_head', 'team_member', 'md', 'md_pa')),
    department_id INTEGER REFERENCES departments(id),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS letters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    reference TEXT NOT NULL UNIQUE,
    sender TEXT NOT NULL,
    subject TEXT NOT NULL,
    received_date TEXT NOT NULL,
    source_file TEXT NOT NULL,
    source_sha256 TEXT NOT NULL,
    source_document BLOB NOT NULL,
    editable_document BLOB,
    editable_filename TEXT,
    department_id INTEGER NOT NULL REFERENCES departments(id),
    status TEXT NOT NULL CHECK (status IN (
        'intake', 'assigned', 'in_progress', 'submitted_for_review',
        'md_review', 'changes_requested', 'approved', 'finalized'
    )),
    response_text TEXT,
    final_pdf BLOB,
    finalized_at TEXT,
    created_by INTEGER NOT NULL REFERENCES users(id),
    assigned_to INTEGER REFERENCES users(id),
    agency_reference TEXT,
    category TEXT NOT NULL DEFAULT 'General correspondence',
    priority TEXT NOT NULL DEFAULT 'normal' CHECK (priority IN ('low', 'normal', 'high', 'urgent')),
    confidentiality TEXT NOT NULL DEFAULT 'internal' CHECK (confidentiality IN ('internal', 'confidential', 'restricted')),
    due_date TEXT,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS letter_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    letter_id INTEGER NOT NULL REFERENCES letters(id),
    version_number INTEGER NOT NULL,
    version_type TEXT NOT NULL CHECK (version_type IN ('source', 'editable', 'response', 'final')),
    content BLOB NOT NULL,
    file_name TEXT NOT NULL,
    file_sha256 TEXT NOT NULL,
    created_by INTEGER NOT NULL REFERENCES users(id),
    change_summary TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(letter_id, version_number)
);

CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    letter_id INTEGER REFERENCES letters(id),
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    read_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_versions_letter ON letter_versions(letter_id, version_number);
CREATE INDEX IF NOT EXISTS idx_notifications_user_read ON notifications(user_id, read_at);

CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    letter_id INTEGER NOT NULL REFERENCES letters(id),
    actor_id INTEGER NOT NULL REFERENCES users(id),
    action TEXT NOT NULL,
    from_status TEXT,
    to_status TEXT,
    details TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_letters_department_status
    ON letters(department_id, status);
CREATE INDEX IF NOT EXISTS idx_audit_letter_created
    ON audit_events(letter_id, created_at);
