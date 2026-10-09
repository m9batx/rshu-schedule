import sqlite3
conn = sqlite3.connect('schedules.db')
cur = conn.cursor()
cur.execute("select group_name, discipline from classes where discipline like '%кселератор%' and (dates='[]' or dates is null) limit 3")
for r in cur.fetchall():
    print(r[0], r[1][:60])
conn.close()
