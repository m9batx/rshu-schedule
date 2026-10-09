import sys
sys.path.insert(0, r'C:\Users\mimoh\Desktop\schudel maker')
import extractor as E
s = E.extract_schedule('pdfs/ПГ-Б23-1-4.pdf')
# thursday 09:00
for day,d in s.items():
    if day=='thursday':
        for ts,slot in d['time_slots'].items():
            if '09.00' in ts:
                print(ts, len(slot['classes']))
                for c in slot['classes']:
                    print('---')
                    print(c['discipline'])
                    print(c['dates'])
                break
