import json, os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen

from icalendar import Calendar
from dateutil.rrule import rrulestr

DEFAULT_ICAL_URL = 'webcal://p162-caldav.icloud.com/published/2/MTE2OTYzNzg5NjExNjk2M7HKAZnoVMTh3P9wjhD3NWyugl0CXRo0y04Vw5Rsh82bVwvYOMEgpTT8ucPmxiSUiVpqzkkyWWMSMmr5Vvy4R3k'
URL = os.environ.get('ICAL_URL', DEFAULT_ICAL_URL).strip()
if URL.startswith('webcal://'):
    URL = 'https://' + URL[len('webcal://'):]

req = Request(URL, headers={'User-Agent':'FamilyDashboard/1.0'})
with urlopen(req, timeout=30) as r:
    raw = r.read()
cal = Calendar.from_ical(raw)

now = datetime.now(timezone.utc)
window_start = now - timedelta(days=45)
window_end = now + timedelta(days=400)
events=[]

def iso(v):
    if hasattr(v, 'isoformat'): return v.isoformat()
    return str(v)

def add_event(comp, start, end=None):
    title = str(comp.get('summary') or 'Termin')
    all_day = not isinstance(start, datetime)
    if isinstance(start, datetime):
        if start.tzinfo is None: start = start.replace(tzinfo=timezone.utc)
        sdt = start.astimezone(timezone.utc)
    else:
        sdt = datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc)
    if sdt < window_start or sdt > window_end: return
    if isinstance(end, datetime):
        if end.tzinfo is None: end = end.replace(tzinfo=timezone.utc)
        edt=end.astimezone(timezone.utc)
    elif end is not None:
        edt=datetime.combine(end, datetime.min.time(), tzinfo=timezone.utc)
    else:
        edt=None
    events.append({'title':title,'start':iso(start),'end':iso(end) if end is not None else None,'allDay':all_day})

for comp in cal.walk('VEVENT'):
    start = comp.decoded('dtstart')
    end = comp.decoded('dtend') if comp.get('dtend') else None
    rule = comp.get('rrule')
    if not rule:
        add_event(comp,start,end)
        continue
    # recurring events: expand occurrences within window
    if not isinstance(start, datetime):
        # keep all-day recurring events simple; dateutil can still expand via midnight UTC
        base = datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc)
        duration = (end-start) if end is not None else timedelta(days=1)
        rule_text = rule.to_ical().decode()
        rr = rrulestr(rule_text, dtstart=base)
        for occ in rr.between(window_start,window_end,inc=True):
            occ_date=occ.date()
            add_event(comp,occ_date,occ_date+duration)
    else:
        base=start if start.tzinfo else start.replace(tzinfo=timezone.utc)
        duration=(end-start) if isinstance(end,datetime) else None
        rule_text=rule.to_ical().decode()
        rr=rrulestr(rule_text,dtstart=base)
        for occ in rr.between(window_start,window_end,inc=True):
            add_event(comp,occ,occ+duration if duration else None)

events.sort(key=lambda e:e['start'])
Path('calendar.json').write_text(json.dumps({'updated':datetime.now(timezone.utc).isoformat(),'events':events},ensure_ascii=False,indent=2),encoding='utf-8')
print(f'{len(events)} Termine geschrieben')
