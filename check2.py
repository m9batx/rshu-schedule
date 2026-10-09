import sqlite3
conn = sqlite3.connect('schedules.db')
cur = conn.cursor()
cur.execute("select group_name, discipline, location, dates from classes where not (discipline like '%кселератор%') and (dates='[]' or dates is null) limit 5")
for r in cur.fetchall():
    print(r[0], r[1][:40], r[2], r[3])
conn.close()
