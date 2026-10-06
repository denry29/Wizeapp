-- ============================================================================
--  Wize - Trip Planner
--  SQLite schema (standard library sqlite3 module, no ORM)
--  Create the database with:  python scripts/init_db.py
-- ============================================================================

PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------- Users ----
CREATE TABLE IF NOT EXISTS users (
    user_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name     TEXT    NOT NULL CHECK (length(trim(full_name)) BETWEEN 2 AND 80),
    email         TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT    NOT NULL,
    email_verified INTEGER NOT NULL DEFAULT 1 CHECK (email_verified IN (0,1)),
    email_verified_at TEXT,
    last_login_at TEXT,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS email_verifications (
    user_id       INTEGER PRIMARY KEY,
    code_hash     TEXT NOT NULL,
    expires_at    TEXT NOT NULL,
    sent_at       TEXT NOT NULL,
    attempts      INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS auth_rate_limits (
    rate_key      TEXT PRIMARY KEY,
    window_started_at TEXT NOT NULL,
    attempts      INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0)
);

CREATE TABLE IF NOT EXISTS login_history (
    login_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL,
    login_at      TEXT NOT NULL,
    device_type   TEXT NOT NULL,
    client_name   TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_login_history_user_time
    ON login_history (user_id, login_at);

-- ---------------------------------------------------------------- Trips ----
CREATE TABLE IF NOT EXISTS trips (
    trip_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL,
    trip_name    TEXT    NOT NULL CHECK (length(trim(trip_name)) BETWEEN 2 AND 100),
    start_date   TEXT    NOT NULL,
    end_date     TEXT    NOT NULL,
    description  TEXT,
    budget       REAL    CHECK (budget IS NULL OR budget >= 0),
    budget_currency TEXT CHECK (budget_currency IS NULL OR length(budget_currency) = 3),
    status       TEXT    NOT NULL DEFAULT 'planning'
                 CHECK (status IN ('planning','upcoming','ongoing','completed','cancelled')),
    created_at   TEXT    NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE,
    CHECK (date(end_date) >= date(start_date))
);

CREATE INDEX IF NOT EXISTS idx_trips_user      ON trips (user_id);
CREATE INDEX IF NOT EXISTS idx_trips_user_date ON trips (user_id, start_date);
CREATE INDEX IF NOT EXISTS idx_trips_status    ON trips (status);

-- ---------------------------------------------------------- Destinations ---
-- One table holds the shared Asian catalogue AND user-created custom spots:
--   is_custom = 0 -> shared catalogue row (user_id IS NULL)
--   is_custom = 1 -> personal row owned by user_id
-- name_key holds the normalised name and, together with UNIQUE(name_key,
-- country, city), makes the catalogue duplicate-proof and the seeding
-- script idempotent.
CREATE TABLE IF NOT EXISTS destinations (
    destination_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    name                  TEXT    NOT NULL CHECK (length(trim(name)) BETWEEN 2 AND 120),
    name_key              TEXT    NOT NULL,
    country               TEXT    NOT NULL,
    city                  TEXT,
    category              TEXT    NOT NULL CHECK (category IN (
                              'beach','mountain','historical_site','temple','museum',
                              'cultural','park','natural_landmark','architectural_landmark',
                              'theme_park','island','lake','waterfall','market','other')),
    description           TEXT,
    image_url             TEXT,
    estimated_entrance_fee REAL   CHECK (estimated_entrance_fee IS NULL
                                        OR estimated_entrance_fee >= 0),
    currency              TEXT    CHECK (currency IS NULL OR length(currency) = 3),
    is_custom             INTEGER NOT NULL DEFAULT 0 CHECK (is_custom IN (0,1)),
    is_listed             INTEGER NOT NULL DEFAULT 1 CHECK (is_listed IN (0,1)),
    user_id               INTEGER,
    best_time_to_visit    TEXT,
    recommended_duration  TEXT,
    latitude              REAL,
    longitude             REAL,
    created_at            TEXT    NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE,
    CHECK (is_custom = 1 OR user_id IS NULL),
    UNIQUE (name_key, country, city)
);

CREATE INDEX IF NOT EXISTS idx_dest_name     ON destinations (name);
CREATE INDEX IF NOT EXISTS idx_dest_country  ON destinations (country);
CREATE INDEX IF NOT EXISTS idx_dest_city     ON destinations (city);
CREATE INDEX IF NOT EXISTS idx_dest_category ON destinations (category);
CREATE INDEX IF NOT EXISTS idx_dest_custom   ON destinations (is_custom, user_id);

-- ------------------------------------------------- Destination imagery ----
-- Attribution columns for images sourced from Wikimedia Commons.  They are
-- filled by ``scripts/fetch_destination_images.py`` and are always NULL for a
-- destination that has no matched image, which is what keeps the placeholder
-- visible on the browse page.
--
-- The columns are added by ``DatabaseManager.create_tables()`` rather than by
-- an ALTER TABLE here: ``CREATE TABLE IF NOT EXISTS`` silently skips an
-- existing table, but ``ALTER TABLE ... ADD COLUMN`` raises "duplicate column
-- name" on the second run, which would break the idempotent contract of this
-- file.  ``create_tables`` therefore checks ``PRAGMA table_info`` first and
-- only adds the columns an older database is missing.

-- One row per destination that has been *processed* by the image fetcher.
-- This ledger is what makes the script resumable: a destination present here
-- is never searched again, so a re-run only costs the rows still missing.
--   status = 'matched'   -> image_url + attribution were written
--           'review'     -> candidates existed but scored too low to trust
--           'no_result'  -> Commons returned nothing at all
--           'error'      -> network/API failure; safe to retry later
CREATE TABLE IF NOT EXISTS destination_images (
    destination_id  INTEGER PRIMARY KEY,
    status          TEXT    NOT NULL DEFAULT 'pending' CHECK (status IN
                       ('pending','matched','review','no_result','error')),
    image_title     TEXT,
    creator         TEXT,
    source_page_url TEXT,
    license         TEXT,
    license_url     TEXT,
    query_used      TEXT,                       -- exact search string used
    confidence      REAL,                       -- 0..1 score of the match
    note            TEXT,                       -- why review/error was chosen
    checked_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (destination_id) REFERENCES destinations (destination_id)
        ON DELETE CASCADE
);

-- Partial unique index: the same Commons file may only back one destination,
-- which is what implements the "avoid duplicate images" rule at the DB level.
CREATE UNIQUE INDEX IF NOT EXISTS idx_dest_image_unique
    ON destination_images (source_page_url)
    WHERE source_page_url IS NOT NULL AND source_page_url <> '';

CREATE INDEX IF NOT EXISTS idx_destimg_status ON destination_images (status);

-- ------------------------------------------------------ Trip Destinations --
CREATE TABLE IF NOT EXISTS trip_destinations (
    trip_destination_id INTEGER PRIMARY KEY AUTOINCREMENT,
    trip_id             INTEGER NOT NULL,
    destination_id      INTEGER NOT NULL,
    visit_date          TEXT    CHECK (visit_date IS NULL OR length(visit_date) = 10),
    notes               TEXT,
    sequence_number     INTEGER NOT NULL DEFAULT 1 CHECK (sequence_number > 0),
    FOREIGN KEY (trip_id)        REFERENCES trips (trip_id)        ON DELETE CASCADE,
    FOREIGN KEY (destination_id) REFERENCES destinations (destination_id) ON DELETE CASCADE,
    UNIQUE (trip_id, destination_id)
);

CREATE INDEX IF NOT EXISTS idx_td_trip ON trip_destinations (trip_id, sequence_number);
CREATE INDEX IF NOT EXISTS idx_td_dest ON trip_destinations (destination_id);
-- ------------------------------------------------------------ Schedules ---
CREATE TABLE IF NOT EXISTS schedules (
    schedule_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    trip_id        INTEGER NOT NULL,
    destination_id INTEGER,                       -- optional association
    activity_name  TEXT    NOT NULL CHECK (length(trim(activity_name)) BETWEEN 2 AND 120),
    activity_date  TEXT    NOT NULL CHECK (length(activity_date) = 10),
    start_time     TEXT    CHECK (start_time IS NULL OR length(start_time) = 5),
    end_time       TEXT    CHECK (end_time   IS NULL OR length(end_time)   = 5),
    notes          TEXT,
    FOREIGN KEY (trip_id)        REFERENCES trips (trip_id)        ON DELETE CASCADE,
    FOREIGN KEY (destination_id) REFERENCES destinations (destination_id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_sched_trip_date ON schedules (trip_id, activity_date);
CREATE INDEX IF NOT EXISTS idx_sched_dest      ON schedules (destination_id);

-- ------------------------------------------------------------- Expenses ---
CREATE TABLE IF NOT EXISTS expenses (
    expense_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    trip_id      INTEGER NOT NULL,
    expense_name TEXT    NOT NULL CHECK (length(trim(expense_name)) BETWEEN 2 AND 120),
    category     TEXT    NOT NULL CHECK (category IN
                    ('flights','hotels','food','transportation','accommodation',
                     'entrance_fees','shopping','activities','other')),
    amount       REAL    NOT NULL CHECK (amount > 0),
    expense_kind TEXT    NOT NULL DEFAULT 'actual'
                 CHECK (expense_kind IN ('planned','actual')),
    source_option_id INTEGER REFERENCES saved_options (option_id)
                 ON DELETE CASCADE,
    currency     TEXT    NOT NULL DEFAULT 'USD' CHECK (length(currency) = 3),
    expense_date TEXT    NOT NULL CHECK (length(expense_date) = 10),
    notes        TEXT,
    FOREIGN KEY (trip_id) REFERENCES trips (trip_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_exp_trip ON expenses (trip_id);
CREATE INDEX IF NOT EXISTS idx_exp_cat  ON expenses (trip_id, category);

-- ----------------------------------------------------------- Checklists ---
CREATE TABLE IF NOT EXISTS checklists (
    checklist_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    trip_id        INTEGER NOT NULL,
    checklist_name TEXT    NOT NULL CHECK (length(trim(checklist_name)) BETWEEN 2 AND 100),
    created_at     TEXT    NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (trip_id) REFERENCES trips (trip_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_check_trip ON checklists (trip_id);

CREATE TABLE IF NOT EXISTS checklist_items (
    item_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    checklist_id INTEGER NOT NULL,
    item_name    TEXT    NOT NULL CHECK (length(trim(item_name)) BETWEEN 2 AND 120),
    is_completed INTEGER NOT NULL DEFAULT 0 CHECK (is_completed IN (0,1)),
    created_at   TEXT    NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (checklist_id) REFERENCES checklists (checklist_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_items_checklist ON checklist_items (checklist_id, is_completed);

-- --------------------------------------------------------- Mobile app data --
CREATE TABLE IF NOT EXISTS favorites (
    user_id        INTEGER NOT NULL,
    destination_id INTEGER NOT NULL,
    created_at     TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (user_id, destination_id),
    FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE,
    FOREIGN KEY (destination_id) REFERENCES destinations (destination_id)
        ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS trip_notes (
    note_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    trip_id    INTEGER NOT NULL,
    title      TEXT NOT NULL CHECK (length(trim(title)) BETWEEN 1 AND 120),
    content    TEXT NOT NULL CHECK (length(content) <= 10000),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (trip_id) REFERENCES trips (trip_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_trip_notes_trip ON trip_notes (trip_id, updated_at);

CREATE TABLE IF NOT EXISTS saved_options (
    option_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    trip_id     INTEGER NOT NULL,
    option_type TEXT NOT NULL CHECK (option_type IN ('flight','hotel')),
    title       TEXT NOT NULL CHECK (length(trim(title)) BETWEEN 1 AND 200),
    amount      REAL CHECK (amount IS NULL OR amount >= 0),
    currency    TEXT CHECK (currency IS NULL OR length(currency) = 3),
    details_json TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (trip_id) REFERENCES trips (trip_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_saved_options_trip ON saved_options (trip_id, option_type);