"""
Bulk import all PDFs from a folder into schedules.db.
Usage:  python import_pdfs.py pdfs
"""
import os
import sys
import json
import sqlite3
import traceback

from extractor import extract_group, extract_schedule

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "schedules.db")


def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS schedules (
                group_name  TEXT PRIMARY KEY,
                schedule    TEXT NOT NULL,
                pdf_name    TEXT,
                uploaded_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS classes (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                group_name      TEXT NOT NULL,
                day             TEXT NOT NULL,
                time_slot       TEXT NOT NULL,
                break           TEXT NOT NULL DEFAULT '',
                discipline      TEXT NOT NULL DEFAULT '',
                type            TEXT NOT NULL DEFAULT '',
                instructor      TEXT NOT NULL DEFAULT '',
                instructor_key  TEXT NOT NULL DEFAULT '',
                location        TEXT NOT NULL DEFAULT '',
                dates           TEXT NOT NULL DEFAULT '[]'
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_classes_instructor ON classes(instructor_key)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_classes_group ON classes(group_name)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_classes_day ON classes(day)")
        conn.commit()


def flatten_classes(group_name: str, schedule: dict):
    rows = []
    for day, day_data in (schedule or {}).items():
        for ts, slot in day_data.get("time_slots", {}).items():
            for cls in slot.get("classes", []):
                instructor = cls.get("instructor", "")
                rows.append((
                    group_name, day, ts,
                    slot.get("break", ""),
                    cls.get("discipline", ""),
                    cls.get("type", ""),
                    instructor,
                    instructor.lower().strip(),
                    cls.get("location", ""),
                    json.dumps(cls.get("dates", []), ensure_ascii=False),
                ))
    return rows


def import_folder(folder: str):
    pdf_files = sorted(f for f in os.listdir(folder) if f.lower().endswith(".pdf"))
    total = len(pdf_files)
    print(f"Found {total} PDF files in '{folder}'")

    ok, fail = 0, 0
    with sqlite3.connect(DB_PATH) as conn:
        for i, name in enumerate(pdf_files, 1):
            path = os.path.join(folder, name)
            print(f"[{i}/{total}] {name}", end=" ... ", flush=True)
            try:
                group = extract_group(path)
                schedule = extract_schedule(path)
                conn.execute(
                    "INSERT OR REPLACE INTO schedules (group_name, schedule, pdf_name) "
                    "VALUES (?, ?, ?)",
                    (group, json.dumps(schedule, ensure_ascii=False), name)
                )
                conn.execute("DELETE FROM classes WHERE group_name = ?", (group,))
                class_rows = flatten_classes(group, schedule)
                if class_rows:
                    conn.executemany(
                        "INSERT INTO classes (group_name, day, time_slot, break, "
                        "discipline, type, instructor, instructor_key, location, dates) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        class_rows
                    )
                conn.commit()
                print(f"OK ({group})")
                ok += 1
            except Exception as e:
                print(f"FAIL: {e}")
                traceback.print_exc()
                fail += 1

    print(f"\n✅ Imported: {ok}   ❌ Failed: {fail}")


if __name__ == "__main__":
    folder = sys.argv[1] if len(sys.argv) > 1 else "pdfs"
    if not os.path.isdir(folder):
        print(f"Folder not found: {folder}")
        sys.exit(1)
    init_db()
    import_folder(folder)