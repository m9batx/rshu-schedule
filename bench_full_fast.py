# full benchmark fast
import sys, os, json, sqlite3
sys.path.insert(0, '.')
os.chdir(r'C:\Users\mimoh\Desktop\schudel maker')
import extractor as E

files = sorted(f for f in os.listdir('pdfs') if f.lower().endswith('.pdf'))
con = sqlite3.connect('schedules.db')
con.row_factory = sqlite3.Row
# get old counts
old_tot = con.execute('select count(*) from classes').fetchone()[0]
old_und = con.execute("select count(*) from classes where dates='[]'").fetchone()[0]
old_acc = con.execute("select count(*) from classes where discipline like '%кселератор%'").fetchone()[0]
old_url = con.execute("select count(*) from classes where location like 'http%'").fetchone()[0]
con.close()

tot_new = acc_new = url_new = und_new = 0
for i, fn in enumerate(files):
    sched = E.extract_schedule(os.path.join('pdfs', fn))
    for day, dd in sched.items():
        for ts, slot in (dd.get('time_slots') or {}).items():
            for c in slot.get('classes') or []:
                tot_new += 1
                if 'кселератор' in c['discipline']:
                    acc_new += 1
                if (c.get('location') or '').startswith('http'):
                    url_new += 1
                if not c.get('dates'):
                    und_new += 1
    if i % 30 == 29:
        print(i+1, '/', len(files))
print('---')
print('total:', old_tot, '->', tot_new, '(+' if tot_new>=old_tot else '', tot_new-old_tot, ')')
print('undated:', old_und, '->', und_new, und_new-old_und)
print('accel:', old_acc, '->', acc_new, acc_new-old_acc)
print('url:', old_url, '->', url_new, url_new-old_url)