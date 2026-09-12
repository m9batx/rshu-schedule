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
        conn.commit()


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