PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS departments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    code TEXT
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
    source_storage_path TEXT,
    editable_document BLOB,
    editable_filename TEXT,
    -- Empty while a newly received letter waits for the MD to send it to a department.
    department_id INTEGER REFERENCES departments(id),
    status TEXT NOT NULL CHECK (status IN (
        'intake', 'assigned', 'in_progress', 'dept_review', 'submitted_for_review',
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
    direction TEXT NOT NULL DEFAULT 'incoming',
    letter_date TEXT,
    signatory TEXT,
    cc_parties TEXT,
    our_reference TEXT,
    matter_status TEXT NOT NULL DEFAULT 'open',
    status_remarks TEXT,
    response_document BLOB,
    response_filename TEXT,
    received_via TEXT,
    action_required TEXT,
    addressee TEXT,
    recipient_address TEXT,
    in_reply_to INTEGER REFERENCES letters(id),
    dispatch_status TEXT,
    dispatch_method TEXT,
    dispatched_on TEXT,
    dispatched_by INTEGER REFERENCES users(id),
    dispatch_note TEXT,
    delivered_on TEXT,
    delivery_note TEXT,
    delivery_proof BLOB,
    delivery_proof_filename TEXT,
    body_html TEXT,
    signatory_id INTEGER REFERENCES users(id),
    signatory_title TEXT,
    addressee_title TEXT,
    editing_by INTEGER REFERENCES users(id),
    editing_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS letter_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    letter_id INTEGER NOT NULL REFERENCES letters(id),
    version_number INTEGER NOT NULL,
    version_type TEXT NOT NULL CHECK (version_type IN ('source', 'editable', 'response', 'final')),
    content BLOB NOT NULL,
    storage_path TEXT,
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

CREATE TABLE IF NOT EXISTS letter_enclosures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    letter_id INTEGER NOT NULL REFERENCES letters(id),
    file_name TEXT NOT NULL,
    content BLOB NOT NULL,
    size INTEGER NOT NULL,
    uploaded_by INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_enclosures_letter ON letter_enclosures(letter_id);

CREATE TABLE IF NOT EXISTS letter_comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    letter_id INTEGER NOT NULL REFERENCES letters(id),
    parent_id INTEGER REFERENCES letter_comments(id),
    author_id INTEGER NOT NULL REFERENCES users(id),
    body TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_comments_letter ON letter_comments(letter_id, id);

CREATE TABLE IF NOT EXISTS letter_collaborators (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    letter_id INTEGER NOT NULL REFERENCES letters(id),
    user_id INTEGER REFERENCES users(id),
    department_id INTEGER REFERENCES departments(id),
    can_edit INTEGER NOT NULL DEFAULT 0 CHECK (can_edit IN (0, 1)),
    request_note TEXT,
    due_date TEXT,
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'done')),
    done_note TEXT,
    done_at TEXT,
    done_by INTEGER REFERENCES users(id),
    added_by INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK ((user_id IS NULL) <> (department_id IS NULL))
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_collab_user ON letter_collaborators(letter_id, user_id) WHERE user_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_collab_department ON letter_collaborators(letter_id, department_id) WHERE department_id IS NOT NULL;
