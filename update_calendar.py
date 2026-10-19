import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen

from icalendar import Calendar
from dateutil.rrule import rrulestr


DEFAULT_ICAL_URL = (
    "webcal://p162-caldav.icloud.com/published/2/"
    "MTE2OTYzNzg5NjExNjk2M7HKAZnoVMTh3P9wjhD3NWyugl0CXRo0y04Vw5Rsh82bVwvYOMEgpTT8ucPmxiSUiVpqzkkyWWMSMmr5Vvy4R3k"
)

URL = os.environ.get("ICAL_URL", DEFAULT_ICAL_URL).strip()

if URL.startswith("webcal://"):
    URL = "https://" + URL[len("webcal://"):]


req = Request(
    URL,
    headers={
        "User-Agent": "FamilyDashboard/1.0"
    }
)

with urlopen(req, timeout=30) as r:
    raw = r.read()

cal = Calendar.from_ical(raw)


now = datetime.now(timezone.utc)
window_start = now - timedelta(days=45)
window_end = now + timedelta(days=400)

events = []


def iso(v):
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return str(v)


def normalize_rrule_until(rule_text, dtstart):
    """
    dateutil verlangt:
    Wenn DTSTART timezone-aware ist, muss UNTIL ebenfalls UTC sein.

    Manche iCloud-/ICS-Kalender liefern z.B.:

        UNTIL=20261231T180000

    obwohl DTSTART eine Zeitzone wie Europe/Zurich besitzt.

    Diese Funktion interpretiert UNTIL in derselben Zeitzone wie DTSTART
    und wandelt den Wert korrekt nach UTC um:

        UNTIL=20261231T170000Z
    """

    if not isinstance(dtstart, datetime):
        return rule_text

    if dtstart.tzinfo is None:
        return rule_text

    match = re.search(
        r"UNTIL=(\d{8}T\d{6})(?!Z)",
        rule_text
    )

    if not match:
        return rule_text

    raw_until = match.group(1)

    local_until = datetime.strptime(
        raw_until,
        "%Y%m%dT%H%M%S"
    ).replace(
        tzinfo=dtstart.tzinfo
    )

    utc_until = local_until.astimezone(
        timezone.utc
    )

    corrected_until = utc_until.strftime(
        "%Y%m%dT%H%M%SZ"
    )

    corrected_rule = rule_text.replace(
        f"UNTIL={raw_until}",
        f"UNTIL={corrected_until}"
    )

    print(
        "RRULE UNTIL korrigiert:",
        rule_text,
        "->",
        corrected_rule
    )

    return corrected_rule


def add_event(comp, start, end=None):
    title = str(
        comp.get("summary")
        or "Termin"
    )

    all_day = not isinstance(
        start,
        datetime
    )

    if isinstance(start, datetime):

        if start.tzinfo is None:
            start = start.replace(
                tzinfo=timezone.utc
            )

        sdt = start.astimezone(
            timezone.utc
        )

    else:

        sdt = datetime.combine(
            start,
            datetime.min.time(),
            tzinfo=timezone.utc
        )

    if sdt < window_start:
        return

    if sdt > window_end:
        return


    if isinstance(end, datetime):

        if end.tzinfo is None:
            end = end.replace(
                tzinfo=timezone.utc
            )

        edt = end.astimezone(
            timezone.utc
        )

    elif end is not None:

        edt = datetime.combine(
            end,
            datetime.min.time(),
            tzinfo=timezone.utc
        )

    else:
        edt = None


    events.append(
        {
            "title": title,
            "start": iso(start),
            "end": iso(end)
            if end is not None
            else None,
            "allDay": all_day
        }
    )


for comp in cal.walk("VEVENT"):

    try:

        start = comp.decoded(
            "dtstart"
        )

        end = (
            comp.decoded("dtend")
            if comp.get("dtend")
            else None
        )

        rule = comp.get(
            "rrule"
        )


        #
        # NORMALER EINZELTER TERMIN
        #

        if not rule:

            add_event(
                comp,
                start,
                end
            )

            continue


        #
        # SERIENTERMIN
        #

        rule_text = (
            rule
            .to_ical()
            .decode()
        )


        #
        # GANZTÄGIGER SERIENTERMIN
        #

        if not isinstance(
            start,
            datetime
        ):

            base = datetime.combine(
                start,
                datetime.min.time(),
                tzinfo=timezone.utc
            )

            duration = (
                end - start
                if end is not None
                else timedelta(days=1)
            )

            rule_text = normalize_rrule_until(
                rule_text,
                base
            )

            try:

                rr = rrulestr(
                    rule_text,
                    dtstart=base
                )

            except Exception as e:

                print(
                    "WARNUNG:",
                    "RRULE konnte nicht verarbeitet werden."
                )

                print(
                    "Termin:",
                    comp.get("summary")
                )

                print(
                    "RRULE:",
                    rule_text
                )

                print(
                    "Fehler:",
                    e
                )

                continue


            try:

                occurrences = rr.between(
                    window_start,
                    window_end,
                    inc=True
                )

            except Exception as e:

                print(
                    "WARNUNG:",
                    "Serientermine konnten nicht expandiert werden."
                )

                print(
                    "Termin:",
                    comp.get("summary")
                )

                print(
                    "Fehler:",
                    e
                )

                continue


            for occ in occurrences:

                occ_date = occ.date()

                add_event(
                    comp,
                    occ_date,
                    occ_date + duration
                )


        #
        # SERIENTERMIN MIT UHRZEIT
        #

        else:

            base = (
                start
                if start.tzinfo
                else start.replace(
                    tzinfo=timezone.utc
                )
            )

            duration = (
                end - start
                if isinstance(
                    end,
                    datetime
                )
                else None
            )

            rule_text = normalize_rrule_until(
                rule_text,
                base
            )

            try:

                rr = rrulestr(
                    rule_text,
                    dtstart=base
                )

            except Exception as e:

                print(
                    "WARNUNG:",
                    "RRULE konnte nicht verarbeitet werden."
                )

                print(
                    "Termin:",
                    comp.get("summary")
                )

                print(
                    "RRULE:",
                    rule_text
                )

                print(
                    "Fehler:",
                    e
                )

                continue


            try:

                occurrences = rr.between(
                    window_start,
                    window_end,
                    inc=True
                )

            except Exception as e:

                print(
                    "WARNUNG:",
                    "Serientermine konnten nicht expandiert werden."
                )

                print(
                    "Termin:",
                    comp.get("summary")
                )

                print(
                    "Fehler:",
                    e
                )

                continue


            for occ in occurrences:

                add_event(
                    comp,
                    occ,
                    occ + duration
                    if duration
                    else None
                )


    except Exception as e:

        #
        # Ein einzelner kaputter Termin darf nie
        # den ganzen Kalender-Workflow stoppen.
        #

        print(
            "WARNUNG:",
            "Termin konnte nicht verarbeitet werden."
        )

        print(
            "Termin:",
            comp.get("summary")
        )

        print(
            "Fehler:",
            e
        )

        continue


events.sort(
    key=lambda e: e["start"]
)


Path(
    "calendar.json"
).write_text(
    json.dumps(
        {
            "updated":
                datetime.now(
                    timezone.utc
                ).isoformat(),

            "events":
                events
        },
        ensure_ascii=False,
        indent=2
    ),
    encoding="utf-8"
)


print(
    f"{len(events)} Termine geschrieben"
)
