# quick benchmark on 20 files max
import sys, os, json, sqlite3
sys.path.insert(0, r'C:\Users\mimoh\Desktop\schudel maker')
os.chdir(r'C:\Users\mimoh\Desktop\schudel maker')
import extractor as E

files = sorted(f for f in os.listdir('pdfs') if f.lower().endswith('.pdf'))[:20]
con = sqlite3.connect('schedules.db')
con.row_factory = sqlite3.Row
tot_new = 0
acc_new = 0
url_new = 0
und_new = 0
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
print('tot', tot_new, 'acc', acc_new, 'url', url_new, 'und', und_new)
con.close()