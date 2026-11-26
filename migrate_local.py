"""Import exported CSV or JSON files, or make a consistent SQLite backup."""
import argparse
import csv
import json
from pathlib import Path
from services.database import TABLES, backup_database, database_path, import_records

BOOL = {"active", "is_active", "is_starred", "is_unusable", "review_decision_correct", "crs_original_fault_changed"}
JSON_FIELDS = {"video_urls", "dvsport_metadata", "tags"}
NUMBER = {"set_number", "challenge_length_seconds", "dvsport_challenge_length_seconds", "dvsport_play_number"}


def csv_value(key, value):
    if value == "":
        return None
    if key in BOOL:
        val = value.lower()
        if val in {"true", "t", "1", "yes"}:
            return True
        if val in {"false", "f", "0", "no"}:
            return False
        raise ValueError(f"Invalid boolean in {key}: {value}")
    if key in JSON_FIELDS:
        return json.loads(value)
    if key in NUMBER or key in {"id", "play_id"}:
        try:
            if str(int(value)) == value:
                return int(value)
            if key in NUMBER:
                return float(value)
        except ValueError:
            if key in NUMBER:
                raise
    return value


def read_export(path):
    if path.suffix.lower() == ".json":
        with path.open(encoding="utf-8-sig") as f:
            rows = json.load(f)
        if not isinstance(rows, list):
            raise ValueError("JSON must contain an array of records")
        return rows
    if path.suffix.lower() == ".csv":
        with path.open(encoding="utf-8-sig", newline="") as f:
            return [{k: csv_value(k, v) for k, v in row.items()} for row in csv.DictReader(f)]
    raise ValueError("Use a CSV or JSON export")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--backup", action="store_true")
    parser.add_argument("--table", choices=sorted(TABLES), default="plays")
    parser.add_argument("file", nargs="?", type=Path)
    args = parser.parse_args()
    if args.backup:
        print("Backup:", backup_database() or "No database yet")
        return
    if not args.file:
        parser.error("Supply an export file or --backup")
    rows = read_export(args.file)
    print(f"Imported {import_records(args.table, rows)} rows into {args.table}: {database_path()}")


if __name__ == "__main__":
    main()
