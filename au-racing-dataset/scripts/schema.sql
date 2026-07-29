-- au_racing.db schema
-- WA thoroughbred racing dataset scraped from racenet.com.au (form-guide + results pages).
-- One row per runner per start in `runners`; one row per race in `races`.

CREATE TABLE IF NOT EXISTS races (
    race_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    track             TEXT NOT NULL,          -- e.g. 'Ascot'
    date              TEXT NOT NULL,          -- ISO YYYY-MM-DD
    race_number        INTEGER NOT NULL,
    race_name         TEXT,
    class_raw         TEXT,                   -- verbatim "Class:" text from Racenet
    class_score       REAL,                   -- heuristic ordinal score, see class_rank.py
    distance_m        INTEGER,
    track_condition   TEXT,                   -- e.g. 'Good 4'
    weather           TEXT,
    prize_total       INTEGER,
    track_info        TEXT,                   -- rail position etc.
    race_time         TEXT,
    race_time_elapsed TEXT,
    sectional_time    TEXT,
    sectional_at_m    INTEGER,
    field_size        INTEGER,
    source_url        TEXT,
    UNIQUE(track, date, race_number)
);

CREATE TABLE IF NOT EXISTS runners (
    runner_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    race_id           INTEGER NOT NULL REFERENCES races(race_id),
    runner_number     INTEGER,
    horse_name        TEXT NOT NULL,
    horse_url         TEXT,
    barrier           INTEGER,
    age               INTEGER,
    sex               TEXT,
    trainer           TEXT,
    jockey            TEXT,
    weight_kg         REAL,
    claim_kg          REAL,                   -- apprentice claim, derived from "cd" weight annotation
    apprentice        INTEGER,                -- 1/0/NULL boolean
    finish_position   INTEGER,                -- NULL if scratched/DNF
    margin            TEXT,                   -- verbatim margin string, e.g. '1.75L'
    win_sp            REAL,
    place_sp          REAL,
    scratched         INTEGER NOT NULL DEFAULT 0,
    win               INTEGER,                -- 1 if finish_position = 1
    placed            INTEGER,                -- 1 if finish_position <= 3 (documented convention, see notes)
    gear_change       TEXT,                   -- verbatim gear-change text for this start, if any
    first_time_gear   TEXT,                   -- comma list of gear items flagged "first time" this start
    -- class movement, computed from this horse's previous scraped start (see class_rank.py)
    prev_race_id      INTEGER REFERENCES races(race_id),
    prev_class_raw    TEXT,
    days_since_prev   INTEGER,
    class_movement    TEXT,                   -- 'higher' | 'lower' | 'equal' | 'unknown' (no prior start in dataset)
    UNIQUE(race_id, runner_number)
);

CREATE INDEX IF NOT EXISTS idx_runners_horse ON runners(horse_name);
CREATE INDEX IF NOT EXISTS idx_runners_trainer ON runners(trainer);
CREATE INDEX IF NOT EXISTS idx_runners_jockey ON runners(jockey);
CREATE INDEX IF NOT EXISTS idx_races_track_date ON races(track, date);

CREATE TABLE IF NOT EXISTS data_quality_notes (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    note   TEXT NOT NULL
);
