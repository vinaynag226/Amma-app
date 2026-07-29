#!/usr/bin/env python3
"""
Glue script for scraping subagents: parse one race's /results page markdown,
merge in that race's gear changes (from the meeting-wide gear-changes dict),
and append one JSON line to the track's output JSONL file.

Usage:
  python3 emit_race.py <results_md_file> <race_url> <gear_changes_json_file> <output_jsonl_path>

gear_changes_json_file should be the output of `parse_race.py <overview_md> gear`
saved to disk (a {race_number_str: {horse_name: change_text}} mapping).
Pass "" (empty string) for gear_changes_json_file if not available.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from parse_race import parse_results_page


def main():
    results_md_file, race_url, gear_json_file, out_path = sys.argv[1:5]
    with open(results_md_file) as f:
        text = f.read()
    race, runners = parse_results_page(text, race_url)

    gear_map = {}
    if gear_json_file and os.path.exists(gear_json_file):
        with open(gear_json_file) as f:
            gear_all = json.load(f)
        gear_map = gear_all.get(str(race["race_number"]), {})

    for r in runners:
        r["gear_change"] = gear_map.get(r["horse_name"])

    if not race.get("track") or not race.get("date") or not race.get("race_number"):
        print(f"WARNING: incomplete race identity for {race_url}: "
              f"track={race.get('track')} date={race.get('date')} race_number={race.get('race_number')}",
              file=sys.stderr)

    with open(out_path, "a") as f:
        f.write(json.dumps({"race": race, "runners": runners}) + "\n")

    print(f"OK {race.get('track')} {race.get('date')} R{race.get('race_number')} "
          f"({race.get('field_size')} runners) -> {out_path}")


if __name__ == "__main__":
    main()
