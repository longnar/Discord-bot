PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS characters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    display_name TEXT,
    aliases TEXT DEFAULT '',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS moves (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    character_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    aliases TEXT DEFAULT '',
    move_type TEXT DEFAULT 'normal',
    notes TEXT DEFAULT '',
    FOREIGN KEY (character_id) REFERENCES characters(id),
    UNIQUE(character_id, name)
);

CREATE TABLE IF NOT EXISTS frame_data (
    move_id INTEGER PRIMARY KEY,
    startup INTEGER,
    active INTEGER,
    recovery INTEGER,
    damage REAL,

    guard TEXT DEFAULT '',
    adv_on_block TEXT DEFAULT '',
    adv_on_hit TEXT DEFAULT '',
    invulnerability TEXT DEFAULT '',
    image_url TEXT DEFAULT '',
    image_data TEXT DEFAULT '',
    notes TEXT DEFAULT '',

    FOREIGN KEY (move_id) REFERENCES moves(id)
);

CREATE TABLE IF NOT EXISTS glossary (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    term TEXT NOT NULL UNIQUE,
    normalized_term TEXT NOT NULL,
    category TEXT DEFAULT 'general',
    definition TEXT NOT NULL,
    aliases TEXT DEFAULT '',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_moves_character_id ON moves(character_id);
CREATE INDEX IF NOT EXISTS idx_moves_normalized_name ON moves(normalized_name);
CREATE INDEX IF NOT EXISTS idx_glossary_normalized_term ON glossary(normalized_term);
CREATE INDEX IF NOT EXISTS idx_characters_name ON characters(name);
