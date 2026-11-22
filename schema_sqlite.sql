-- SQLite version of schema.sql, used only for local development on your laptop.
-- Same tables and columns as the MySQL/RDS schema.

CREATE TABLE IF NOT EXISTS users (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    name                  TEXT NOT NULL,
    email                 TEXT NOT NULL UNIQUE,
    password_hash         TEXT NOT NULL,
    role                  TEXT NOT NULL CHECK (role IN ('donor','ngo','admin')),
    organization          TEXT,
    phone                 TEXT,
    verification_doc_key  TEXT,
    is_verified           INTEGER NOT NULL DEFAULT 0,
    active                INTEGER NOT NULL DEFAULT 1,
    created_at            TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS food_listings (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    donor_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    food_name        TEXT NOT NULL,
    food_type        TEXT NOT NULL DEFAULT 'veg' CHECK (food_type IN ('veg','non-veg','mixed')),
    quantity         INTEGER NOT NULL CHECK (quantity > 0),
    location         TEXT NOT NULL,
    description      TEXT,
    image_key        TEXT,
    available_until  TEXT NOT NULL,
    status           TEXT NOT NULL DEFAULT 'available'
                     CHECK (status IN ('available','requested','approved','picked_up','completed','expired')),
    created_at       TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS pickup_requests (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    food_id     INTEGER NOT NULL REFERENCES food_listings(id) ON DELETE CASCADE,
    ngo_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    message     TEXT,
    status      TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','rejected')),
    created_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (food_id, ngo_id)
);
