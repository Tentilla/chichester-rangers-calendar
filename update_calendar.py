import hashlib
import re
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

TEAM = "Chichester Rangers U10 Black"
SOURCE = "https://fulltime.thefa.com/displayTeam.html?id=218345409"
OUTPUT = Path("calendar.ics")
TZ = ZoneInfo("Europe/London")


def clean(text):
    return " ".join(text.split())


def esc(text):
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def fixture_rows(html):
    soup = BeautifulSoup(html, "html.parser")
    fixtures = []
    for tr in soup.find_all("tr"):
        text = clean(tr.get_text(" | ", strip=True))
        if TEAM not in text:
            continue
        m = re.search(r"(\d{2}/\d{2}/\d{2})\D+(\d{2}:\d{2})", text)
        if not m:
            continue
        # Full-Time fixture rows contain home/away team links. Find our team and
        # the other plausible team link while ignoring navigation/action links.
        names = []
        for a in tr.find_all("a"):
            name = clean(a.get_text(" ", strip=True))
            href = a.get("href", "")
            if name and ("displayTeam" in href or "team" in href.lower()):
                if name not in names:
                    names.append(name)
        if TEAM not in names or len(names) < 2:
            continue
        idx = names.index(TEAM)
        if idx == 0:
            home, away = names[0], names[1]
        else:
            home, away = names[idx - 1], names[idx]
        cells = [clean(td.get_text(" ", strip=True)) for td in tr.find_all("td")]
        venue = cells[-1] if cells else ""
        if venue in (home, away, "VS") or re.search(r"\d{2}/\d{2}/\d{2}|\d{2}:\d{2}", venue):
            venue = ""
        start = datetime.strptime(f"{m.group(1)} {m.group(2)}", "%d/%m/%y %H:%M").replace(tzinfo=TZ)
        fixtures.append((start, home, away, venue))
    # De-duplicate in case Full-Time repeats a fixture in multiple responsive tables.
    return list(dict.fromkeys(fixtures))


def make_ics(fixtures):
    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0",
        "PRODID:-//Chichester Rangers U10 Black//Full-Time Calendar//EN",
        "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
        "X-WR-CALNAME:Chichester Rangers U10 Black",
        "X-WR-TIMEZONE:Europe/London", "X-PUBLISHED-TTL:PT1H"
    ]
    for start, home, away, venue in sorted(fixtures):
        # Stable across a date/time change so calendar clients update rather than duplicate.
        uid = hashlib.sha256(f"{home}|{away}".lower().encode()).hexdigest()[:24] + "@cru10black"
        opponent = away if home == TEAM else home
        ha = "Home" if home == TEAM else "Away"
        end = start + timedelta(hours=1, minutes=15)
        lines += [
            "BEGIN:VEVENT", f"UID:{uid}", f"DTSTAMP:{stamp}",
            f"DTSTART;TZID=Europe/London:{start:%Y%m%dT%H%M%S}",
            f"DTEND;TZID=Europe/London:{end:%Y%m%dT%H%M%S}",
            f"SUMMARY:{esc(TEAM + ' v ' + opponent + ' (' + ha + ')')}",
            f"LOCATION:{esc(venue)}" if venue else "LOCATION:",
            f"DESCRIPTION:{esc('From FA Full-Time. Check Centre Circle/club messages for late changes.')}",
            f"URL:{SOURCE}", "END:VEVENT"
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def main():
    r = requests.get(SOURCE, timeout=30, headers={"User-Agent": "Mozilla/5.0 (compatible; ChichesterRangersCalendar/1.0)"})
    r.raise_for_status()
    fixtures = fixture_rows(r.text)
    if not fixtures:
        raise RuntimeError("No upcoming fixtures parsed; existing calendar left untouched")
    OUTPUT.write_bytes(make_ics(fixtures).encode("utf-8"))
    print(f"Wrote {len(fixtures)} fixtures")


if __name__ == "__main__":
    main()
