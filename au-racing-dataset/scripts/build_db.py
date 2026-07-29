#!/usr/bin/env python3
"""
Aggregate raw/*.jsonl (one JSON object per race: {"race": {...}, "runners": [...]})
into au_racing.db, then compute class movement per runner from each horse's
previous start within the scraped dataset.

Usage: python3 build_db.py [--raw-dir raw] [--db au_racing.db]
"""
import argparse
import glob
import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(__file__))
from class_rank import class_score, compare_class


def load_races(raw_dir):
    races = []
    seen = set()
    dupes = 0
    files = sorted(glob.glob(os.path.join(raw_dir, "*.jsonl")))
    for fp in files:
        with open(fp) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                race = obj["race"]
                key = (race.get("track"), race.get("date"), race.get("race_number"))
                if None in key:
                    continue
                if key in seen:
                    dupes += 1
                    continue
                seen.add(key)
                races.append(obj)
    return races, dupes


def build(raw_dir, db_path, schema_path):
    if os.path.exists(db_path):
        os.remove(db_path)
    conn = sqlite3.connect(db_path)
    with open(schema_path) as f:
        conn.executescript(f.read())

    races, dupes = load_races(raw_dir)
    print(f"Loaded {len(races)} unique races ({dupes} duplicate race records skipped)")

    race_id_map = {}
    n_runners = 0
    for obj in races:
        race = obj["race"]
        score, _ = class_score(race.get("class_raw"))
        cur = conn.execute(
            """INSERT OR IGNORE INTO races
               (track, date, race_number, race_name, class_raw, class_score, distance_m,
                track_condition, weather, prize_total, track_info, race_time,
                race_time_elapsed, sectional_time, sectional_at_m, field_size, source_url)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                race.get("track"), race.get("date"), race.get("race_number"),
                race.get("race_name"), race.get("class_raw"), score,
                race.get("distance_m"), race.get("track_condition"), race.get("weather"),
                race.get("prize_total"), race.get("track_info"), race.get("race_time"),
                race.get("race_time_elapsed"), race.get("sectional_time"),
                race.get("sectional_at_m"), race.get("field_size"), race.get("url"),
            ),
        )
        race_id = cur.lastrowid
        race_id_map[(race["track"], race["date"], race["race_number"])] = race_id

        for r in obj["runners"]:
            win = 1 if r.get("finish_position") == 1 else (0 if r.get("finish_position") else None)
            placed = 1 if (r.get("finish_position") or 99) <= 3 else (0 if r.get("finish_position") else None)
            gear_change = r.get("gear_change")
            first_time = None
            if gear_change:
                items = [g.strip() for g in gear_change.split(",") if "first time" in g]
                first_time = ", ".join(items) if items else None
            conn.execute(
                """INSERT OR IGNORE INTO runners
                   (race_id, runner_number, horse_name, horse_url, barrier, age, sex,
                    trainer, jockey, weight_kg, claim_kg, apprentice, finish_position,
                    margin, win_sp, place_sp, scratched, win, placed, gear_change, first_time_gear)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    race_id, r.get("runner_number"), r.get("horse_name"), r.get("horse_url"),
                    r.get("barrier"), r.get("age"), r.get("sex"), r.get("trainer"), r.get("jockey"),
                    r.get("weight_kg"), r.get("claim_kg"), r.get("apprentice"),
                    r.get("finish_position"), r.get("margin"), r.get("win_sp"), r.get("place_sp"),
                    1 if r.get("scratched") else 0, win, placed, gear_change, first_time,
                ),
            )
            n_runners += 1
    conn.commit()
    print(f"Inserted {n_runners} runner rows across {len(race_id_map)} races")

    compute_class_movement(conn)
    write_data_quality_notes(conn)
    conn.commit()
    conn.close()


def compute_class_movement(conn):
    cur = conn.cursor()
    horses = cur.execute("SELECT DISTINCT horse_name FROM runners WHERE horse_name IS NOT NULL").fetchall()
    updated = 0
    for (horse_name,) in horses:
        rows = cur.execute(
            """SELECT r.runner_id, r.race_id, ra.date, ra.class_raw
               FROM runners r JOIN races ra ON r.race_id = ra.race_id
               WHERE r.horse_name = ? AND r.scratched = 0
               ORDER BY ra.date ASC, ra.race_number ASC""",
            (horse_name,),
        ).fetchall()
        prev = None
        for runner_id, race_id, date, class_raw in rows:
            if prev is None:
                cur.execute(
                    "UPDATE runners SET class_movement = 'unknown' WHERE runner_id = ?",
                    (runner_id,),
                )
            else:
                prev_race_id, prev_date, prev_class_raw = prev
                movement = compare_class(prev_class_raw, class_raw)
                days_since = None
                try:
                    from datetime import date as d
                    y1, m1, d1_ = [int(x) for x in prev_date.split("-")]
                    y2, m2, d2_ = [int(x) for x in date.split("-")]
                    days_since = (d(y2, m2, d2_) - d(y1, m1, d1_)).days
                except Exception:
                    pass
                cur.execute(
                    """UPDATE runners SET prev_race_id=?, prev_class_raw=?, days_since_prev=?,
                       class_movement=? WHERE runner_id=?""",
                    (prev_race_id, prev_class_raw, days_since, movement, runner_id),
                )
                updated += 1
            prev = (race_id, date, class_raw)
    print(f"Computed class movement for {updated} runner starts (with a prior scraped start)")


def write_data_quality_notes(conn):
    notes = [
        "Scrape scope is a bounded sample (see README/report for exact meeting counts and date "
        "range per track), not an exhaustive scrape of all history back to 2012 -- volume was "
        "capped to respect Racenet's servers and this project's tool-call budget.",
        "Apprentice status and claim weight are derived from the weight annotation on the results "
        "page (e.g. '56.5kg cd 54.5kg' -> apprentice=True, claim_kg=2.0), not from the literal "
        "'(a)' marker, which is not present on the /results page (only on /overview). This is "
        "equivalent information but an apprentice riding out fully claimed (no residual claim) "
        "would not be flagged.",
        "The runner-table 'Class' career-record stat (e.g. 'Class: 8:3-2-1') seen on the "
        "form-guide overview page is only rendered for the horse(s) that lead that statistical "
        "category in a given race, not for every runner, so it was not reliably extractable and "
        "is NOT stored per-runner. Class movement is instead computed by comparing the race-level "
        "'Class:' header text across a horse's own consecutive starts within this scraped dataset.",
        "class_score/class_movement use a heuristic ordinal ranking of race grade text (see "
        "class_rank.py) -- benchmark/restricted grading is rating-relative, not a strict national "
        "ladder, so cross-race-type comparisons (e.g. BM66 vs a restricted 3yo race) are "
        "approximate, not certified.",
        "class_movement is 'unknown' for a runner's first scraped start (no prior start present "
        "in this dataset) or when either the previous or current race's Class: text could not be "
        "scored by the heuristic. It is NOT looked up via the horse's full profile page history -- "
        "only starts within this scraped dataset are used, per the task's documented approach.",
        "'placed' is defined as finish_position <= 3 (top-3), independent of the field's actual "
        "paying-place count (some small fields pay only 1st-2nd). This is a simplification "
        "documented here rather than modeled per-field.",
        "Gear-change data is scraped once per meeting from the /overview page's meeting-wide gear "
        "changes index and merged onto runners by race number + horse name; a runner with no entry "
        "there has gear_change = NULL (no gear change that start), not missing data.",
    ]
    for n in notes:
        conn.execute("INSERT INTO data_quality_notes (note) VALUES (?)", (n,))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw-dir", default=os.path.join(os.path.dirname(__file__), "..", "raw"))
    ap.add_argument("--db", default=os.path.join(os.path.dirname(__file__), "..", "au_racing.db"))
    ap.add_argument("--schema", default=os.path.join(os.path.dirname(__file__), "schema.sql"))
    args = ap.parse_args()
    build(args.raw_dir, args.db, args.schema)
