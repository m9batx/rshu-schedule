import re
import os
import pdfplumber
from collections import OrderedDict
from datetime import datetime, timedelta, date
from typing import Optional, List, Dict


# ================= Day / weekday maps =================
DAYS_RU = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота"]
DAYS_EN = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday"]
DAY_MAP = dict(zip(DAYS_RU, DAYS_EN))
WEEKDAY_MAP = {
    "monday": 0, "tuesday": 1, "wednesday": 2,
    "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6,
}


# ================= PDF text =================
def _extract_text(pdf_path: str) -> str:
    text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                text += t + "\n"
    # Keep line breaks: the parser uses them to separate weekday sections.
    # Removing all control characters here merges the entire PDF into one line.
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', text)


# ================= Group name from filename =================
def extract_group(pdf_path: str) -> Optional[str]:
    filename = os.path.splitext(os.path.basename(pdf_path))[0]
    for pattern in [
        r'([А-Яа-я]{2,6}-\d?[А-Яа-я]?\d{2,3}(?:-\d+)*)',
        r'([A-Za-z]{2,6}-\d?[A-Za-z]?\d{2,3}(?:-\d+)*)',
    ]:
        m = re.search(pattern, filename)
        if m:
            return m.group(1).strip()
    return filename


# ================= Dates expansion =================
# Dates appear as '09.09.2026', '09.09.26' or (first-year PDFs) year-less '16.09'.
DATE_TOKEN = r"\d{2}\.\d{2}(?:\.\d{2,4})?"
_DATE_SHAPE_RE = re.compile(r"(\d{2})\.(\d{2})(?:\.(\d{2,4}))?")


def _looks_like_date(token: str) -> bool:
    """True if every dd.mm[.yyyy] fragment has a plausible month.

    Filters out lesson times like '09.00-10.35' (month 00/35 is invalid).
    """
    found = False
    for m in _DATE_SHAPE_RE.finditer(token):
        found = True
        if not (1 <= int(m.group(2)) <= 12):
            return False
    return found


def _parse_date(value: str) -> datetime:
    for date_format in ("%d.%m.%Y", "%d.%m.%y"):
        try:
            return datetime.strptime(value.strip(), date_format)
        except ValueError:
            pass
    try:
        base = datetime.strptime(value.strip(), "%d.%m")
    except ValueError:
        raise ValueError(f"Unsupported date: {value}")
    # Academic year inference: Sep-Dec belong to the current year,
    # Jan-Aug to the following year.
    today = date.today()
    year = today.year if base.month >= 9 else today.year + 1
    return base.replace(year=year)


def _expand_dates(date_strings: List[str], weekday: int) -> List[str]:
    expanded = []
    for item in date_strings:
        item = item.strip()
        for part in item.split(","):
            part = part.strip()
            if not part:
                continue
            if "–" in part or "—" in part or "-" in part:
                parts = re.split(r"\s*[–—-]\s*", part)
            else:
                parts = [part]
            if len(parts) == 2:
                try:
                    start = _parse_date(parts[0])
                    end = _parse_date(parts[1])
                except ValueError:
                    expanded.append(part)
                    continue
                if end < start:
                    # a range crossing into the next year, e.g. '01.12-15.01'
                    end = end.replace(year=start.year + 1)
                current = start
                days_ahead = weekday - current.weekday()
                if days_ahead < 0:
                    days_ahead += 7
                current += timedelta(days=days_ahead)
                while current <= end:
                    expanded.append(current.strftime("%d.%m.%y"))
                    current += timedelta(days=7)
            else:
                # a single explicit date lands on that exact day, regardless
                # of the slot's weekday (PDFs sign one-off lectures this way)
                try:
                    start = _parse_date(part)
                except ValueError:
                    expanded.append(part)
                    continue
                expanded.append(start.strftime("%d.%m.%y"))
    return expanded


# ================= Class block parser =================
_STREET_RE = re.compile(
    r'(?:Малоохтинский|Металлистов|Рижский|Воронежская|'
    r'Ленин\w*|Московский|Гражданский|Дегтярн\w*|Северн\w*|Заневский)'
)


def _clean_loc(seg: str) -> str:
    seg = re.sub(r'перерыв', ' ', seg, flags=re.IGNORECASE)
    seg = re.sub(r'\d{1,2}\.\d{2}[-–—]\d{1,2}\.\d{2}', ' ', seg)
    seg = re.sub(r'\d{1,2}:\d{2}[-–—]\d{1,2}:\d{2}', ' ', seg)
    seg = re.sub(r'\s+', ' ', seg).strip()
    return seg


_LINK_RE = re.compile(
    r'https?://[^\s,;)\]<>"]+|www\.[^\s,;)\]<>"]+',
    re.IGNORECASE,
)



# Geometric split helpers for side-by-side subgroup cells
def _merge_near(cand, dist=2.0):
    if not cand:
        return cand
    cand.sort(key=lambda e: e['x'])
    res = [cand[0]]
    for e in cand[1:]:
        last = res[-1]
        if abs(e['x'] - last['x']) < dist:
            last['top'] = min(last['top'], e['top'])
            last['bottom'] = max(last['bottom'], e['bottom'])
            continue
        res.append(e)
    return res


def _find_dividers(page, cell, tol=2.0, span_ratio=0.4):
    x0, top, x1, bottom = cell
    cand = []
    for e in page.edges:
        if e.get('orientation') != 'v':
            continue
        ex = (e['x0'] + e['x1']) / 2
        if not (x0 + tol < ex < x1 - tol):
            continue
        lo, hi = min(e['top'], e['bottom']), max(e['top'], e['bottom'])
        ov = min(hi, bottom) - max(lo, top)
        h = bottom - top
        if h > 0 and ov / h >= span_ratio and (hi - lo) / h >= span_ratio:
            cand.append({'x': ex, 'top': max(lo, top), 'bottom': min(hi, bottom)})
    return _merge_near(cand)


def _cell_lines_chars(page, cell, ypad=1.0):
    x0, top, x1, bottom = cell
    chars = [c for c in page.chars
             if x0 - 0.5 <= (c['x0'] + c['x1']) / 2 <= x1 + 0.5
             and top - ypad <= c['top'] and c['bottom'] <= bottom + ypad]
    lines = {}
    for c in chars:
        key = None
        for k in lines:
            if abs(k - c['top']) <= 2.0:
                key = k
                break
        if key is None:
            key = c['top']
            lines[key] = []
        lines[key].append(c)
    out = []
    for k in sorted(lines):
        cs = sorted(lines[k], key=lambda c: c['x0'])
        out.append({'top': k, 'bottom': max(c['bottom'] for c in cs), 'chars': cs})
    return out


def _render_chars(chars):
    return ''.join(c['text'] for c in chars).strip()


def _extract_location(raw: str) -> str:
    """Find a classroom/address in the class text.

    A web link wins over the address: remote classes (accelerator blocks) print
    'https://startup.rshu.ru' instead of a room, and that link is what a student
    actually needs.

    Handles the many PDF formats:
      'Ауд. 101 2 корпус (пр. Металлистов, д.3)'
      'Ауд. 18а 2 корпус (пр. Металлистов, д.3)'
      'Ауд. 103.4 корпус 4 (Рижский пр., д. 11)'
      'Ауд. 201 корпус 4 (Рижский пр., д. 11)'
      '107 ауд., Рижский пр., 11'
      '20 ауд. 209 корпус 1'
      '0 Спортзал 1 корпус (Малоохтинский пр., д.98)'
      ', ауд. 44, корпус 3 (Воронежская ул., д. 79)'
      'Дистанционная поддержка'
      '10.45-12.20 (Малоохтинский пр., д.98)'
    """
    if not raw:
        return ""

    link = _LINK_RE.search(raw)
    if link:
        return link.group(0).rstrip('.,;')

    if "Дистанционная поддержка" in raw:
        return "Дистанционная поддержка"

    # 1) room + building + (street address) — with junk between room and paren
    loc = re.search(
        r'(?:(?:Ауд|ауд)\.\s*[\dА-Яа-я\.\-]+'
        r'|\d{1,4}(?:\.\d+)?\s+ауд\.?'
        r'|[Сс]портзал)'
        r'[^()]{0,40}\([^)]*\)',
        raw
    )
    if loc:
        seg = _clean_loc(loc.group(0))
        if len(seg) > 3:
            return seg

    # 2) bare street address in parentheses
    loc = re.search(r'\(([^()]*' + _STREET_RE.pattern + r'[^()]*)\)', raw)
    if loc:
        seg = _clean_loc(loc.group(0))
        if len(seg) > 3:
            return seg

    # 3) comma style: '107 ауд., Рижский пр., 11'
    loc = re.search(
        r'\d{1,4}(?:\.\d+)?\s+ауд\.,?\s*[^.;\n]{0,45}', raw
    )
    if loc:
        seg = _clean_loc(loc.group(0))
        if _STREET_RE.search(seg) or "корпус" in seg:
            return seg

    return ""


def _to_minutes(t: str):
    """'09.00-10.35' -> (540, 635). Also '17:00-18:00' (Accelerator rows). """
    st, en = re.split(r'[-–—]', t)
    st, en = st.replace(':', '.'), en.replace(':', '.')
    h1, m1 = st.split('.')
    h2, m2 = en.split('.')
    return (int(h1) * 60 + int(m1), int(h2) * 60 + int(m2))


def _lesson_breaks(time_strings: List[str]) -> Dict[str, List[str]]:
    """
    Split time ranges into lessons and their breaks.
    A range contained strictly inside another range is that lesson's BREAK:
        '09.00-10.35' with '09.45-09.50'  -> lesson '09.00-10.35', break '09.45-09.50'
    Returns {lesson_time: [break_times, ...]}.
    """
    mins = {t: _to_minutes(t) for t in time_strings}
    breaks_of = {t: [] for t in time_strings}
    lessons = []
    for t, (r1, r2) in mins.items():
        container, container_span = None, None
        for other, (o1, o2) in mins.items():
            if other == t:
                continue
            if o1 < r1 and r2 < o2:   # strictly inside another range
                span = o2 - o1
                if container_span is None or span < container_span:
                    container, container_span = other, span
        if container is None:
            lessons.append(t)
        else:
            breaks_of[container].append(t)
    return {t: breaks_of[t] for t in lessons}
# Type markers and matching pattern for class blocks within a cell.
# Discipline = run of name characters; a type marker is one of the
# known tokens in parentheses right after it.
_TYPE_ALT = r'(?:лек|прак|практ|сем|лаб|срс|конс|экз|зач)'
_TYPE_CAP = r'(' + _TYPE_ALT + r'\.?)'

_CLASS_RE = re.compile(
    r'([А-Яа-я\s\-\.]+?)\s*\(' + _TYPE_CAP + r'\)'
)
_TYPED_TAIL_RE = re.compile(r'\s*\(' + _TYPE_CAP + r'\)')

# Some classes carry no (лек/лаб/...) marker but a qualifier in brackets:
#   'Акселератор «Гидромет» (Проектный блок)'
#   'Акселератор «Гидромет» (Образовательный блок)'
#   'Акселератор «Гидромет» (Работа с кураторами)'
#   'Физическая культура и спорт (элективная дисциплина)'
#   'Производственная практика (педагогическая практика)'
# These must still be read as classes, otherwise the whole block is dropped.
_KNOWN_TYPE_RE = re.compile(r'^(?:лек|прак|практ|сем|лаб|срс|конс|экз|зач)\.?$',
                            re.IGNORECASE)
_QUALIFIER_TYPE_RE = re.compile(
    r'([А-ЯЁA-Z][^()\n]{2,70}?)\s*\(([^()]{3,45})\)'
)
# ... but a bracket that is really part of an address or a date is not a type.
_NOT_A_TYPE_RE = re.compile(
    r'\d|пр\b|ул\b|д\.|корп|проезд|шоссе|переулок|улиц',
    re.IGNORECASE,
)
# ... and neither is a room/format phrase that belongs to the location line.
_NOT_A_TYPE_WORDS = (
    'дистанционная поддержка', 'дистанционно', 'смешанный формат',
    'очная поддержка', 'аудитория', 'спортзал', 'дистанционная работа',
)


def _qualifier_type_matches(text: str) -> list:
    """Class headers whose bracket holds a qualifier instead of a type."""
    out = []
    for m in _QUALIFIER_TYPE_RE.finditer(text):
        disc, phrase = m.group(1).strip(), m.group(2).strip()
        if _KNOWN_TYPE_RE.match(phrase) or _NOT_A_TYPE_RE.search(phrase):
            continue
        low = phrase.lower()
        if any(w in low for w in _NOT_A_TYPE_WORDS):
            continue
        if not re.search(r'[А-Яа-яЁё]', phrase):
            continue
        if len(phrase.split()) > 4:
            continue
        # the header itself must not be a room/address fragment
        if re.match(r'^(?:Ауд|ауд|Спортзал|спортзал)\b', disc):
            continue
        if not re.search(r'[А-Яа-яЁёA-Za-z]', disc):
            continue
        out.append(m)
    return out


def _class_markers(text: str) -> list:
    """All class starts in a cell: typed ones plus qualifier-typed ones.

    'Страноведение (второй иностранный язык) (прак)' has the qualifier inside
    the name, so the plain type regex would only see an empty name - the
    qualifier match keeps the whole name and the typed tail becomes the type.
    """
    qual = _qualifier_type_matches(text)
    consumed = []
    qual_marks = []
    for m in qual:
        disc, phrase = m.group(1).strip(), m.group(2).strip()
        # 'Учебная практика (учебно-ознакомительная практика) (лек)'
        t2 = _TYPED_TAIL_RE.match(text[m.end():])
        end = m.end()
        if t2:
            disc = f"{disc} ({phrase})"
            phrase = t2.group(1)
            end += t2.end()
            consumed.append((m.start(), end))
        if not disc:
            continue
        qual_marks.append((m.start(), disc, phrase.rstrip('.')))

    marks = []
    for m in _CLASS_RE.finditer(text):
        disc = m.group(1).strip()
        if not disc:
            continue                      # only "(прак)" with no name before it
        if any(a <= m.start() < b for a, b in consumed):
            continue                      # already handled as a qualifier class
        marks.append((m.start(), disc, m.group(2).strip().rstrip('.')))
    marks.extend(qual_marks)
    marks.sort(key=lambda t: t[0])
    out = []
    for s, d, t in marks:
        if out and s < out[-1][0] + 4:
            continue
        out.append((s, d, t))
    return out


def _norm_disc(value: str) -> str:
    return re.sub(r'\s+', ' ', re.sub(r'[^\w\s]', ' ', (value or '').lower())).strip()


_TITLE_RE = re.compile(
    r'^(проф\.|доц\.|ст\.?\s*преп\.|асс\.|ассис\.|преп\.|асп\.|зав\.?\s*каф\.?)\s+',
    re.IGNORECASE,
)


def _merge_field(a: str, b: str) -> str:
    parts = [p.strip() for p in (a or "").split(";") if p.strip()]
    for p in (b or "").split(";"):
        p = p.strip()
        if p and p not in parts:
            parts.append(p)
    return "; ".join(parts)


def _union_dates(a: list, b: list) -> list:
    return list(dict.fromkeys(list(a or []) + list(b or [])))


def _reconcile_classes(classes: List[Dict]) -> List[Dict]:
    """Repair classes parsed out of one lesson cell.

    The PDFs draw the two subgroups side by side inside a single cell, so the
    text arrives interleaved: the second subgroup's "(лаб.)" marker is read as
    a new class, which cuts the first subgroup off before the date line and
    leaves it dateless. A stray "(лаб.)" glued to an instructor line can even
    turn that instructor into a fake class that swallows every date.
    """
    if len(classes) < 2:
        return classes

    merged = []
    for c in classes:
        key = (_norm_disc(c["discipline"]), c["type"])
        if merged and (_norm_disc(merged[-1]["discipline"]), merged[-1]["type"]) == key:
            prev = merged[-1]
            prev["instructor"] = _merge_field(prev["instructor"], c["instructor"])
            prev["location"] = _merge_field(prev["location"], c["location"])
            prev["dates"] = _union_dates(prev["dates"], c["dates"])
            continue
        merged.append(c)

    donated_instructors, donated_dates = [], []
    real = []
    for c in merged:
        if _TITLE_RE.match((c["discipline"] or "").strip()):
            donated_instructors.append(c["instructor"])
            donated_dates.extend(c["dates"])
            continue
        real.append(c)

    out = []
    for c in real:
        c["dates"] = _union_dates(c["dates"], [])
        key = (_norm_disc(c["discipline"]), c["type"], c["instructor"], c["location"])
        if out and out[-1]["_key"] == key:
            out[-1]["dates"] = _union_dates(out[-1]["dates"], c["dates"])
            continue
        c["_key"] = key
        out.append(c)

    pool = list(dict.fromkeys(donated_dates))
    dateless = [c for c in out if not c["dates"]]
    if pool and len(dateless) == 1:
        dateless[0]["dates"] = list(pool)
    for c in dateless:
        if donated_instructors:
            c["instructor"] = _merge_field(c["instructor"], "; ".join(donated_instructors))

    for c in out:
        c.pop("_key", None)
    return out


def _parse_classes(block_text: str, weekday: int) -> List[Dict]:
    block_text = re.sub(r'\s*Верхняя\s*|\s*Нижняя\s*', ' ', block_text)
    block_text = re.sub(r'\s+', ' ', block_text).strip()

    markers = _class_markers(block_text)
    if not markers:
        return []

    classes = []
    for i, (start, disc, ctype) in enumerate(markers):
        end = markers[i + 1][0] if i + 1 < len(markers) else len(block_text)
        raw = re.sub(r'\s+', ' ', block_text[start:end].strip())

        instr_list = re.findall(
            r'((?:проф\.|доц\.|ст\.?\s*преп\.|асс\.|ассис\.|преп\.|'
            r'асп\.|зав\.?\s*каф\.?)\s+'
            r'[А-Я][а-я]+(?:\s+[А-Я][а-я]+){1,2})',
            raw,
            flags=re.IGNORECASE,
        )
        cleaned = []
        for name in instr_list:
            name = re.split(r'\s+(?:Ауд|ауд)\.?', name)[0]
            name = re.split(r'\s+корпус\w*', name)[0]
            # 'ст' from a following 'ст. преп.' title can get glued on
            name = re.sub(r'\s+ст\s*$', '', name, flags=re.IGNORECASE)
            # canonicalize the academic title (drop case-variants for dedupe)
            name = re.sub(
                r'^(проф\.|доц\.|ст\.?\s*преп\.|асс\.|ассис\.|преп\.|'
                r'асп\.|зав\.?\s*каф\.?)\s+',
                lambda m: m.group(1).lower() + ' ',
                name, flags=re.IGNORECASE,
            )
            name = re.sub(r'\s+', ' ', name).strip()
            if name and name not in cleaned:
                cleaned.append(name)
        instructor = "; ".join(cleaned)
        loc = _extract_location(raw)

        raw_dates = []
        for parenthetical in re.findall(r"\(([^()]*)\)", raw):
            if _looks_like_date(parenthetical):
                raw_dates.append(parenthetical.strip())

        classes.append({
            "discipline": disc,
            "type": ctype.strip().rstrip('.'),
            "instructor": instructor,
            "location": loc,
            "dates": _expand_dates(raw_dates, weekday),
        })
    return _reconcile_classes(classes)


# ================= Full schedule =================
# Time formats found in the PDFs:
#   '09.00-10.35'  '13.45-13.50'  '16.30-18.05'  (lesson + its own break)
#   '17:00-18:00'  '18:00-21:00'                 (used by the Accelerator rows)
_TIME_MAIN_RE = re.compile(r'\d{2}\.\d{2}[-–—]\d{2}\.\d{2}')
_TIME_ANY_RE = re.compile(r'\d{1,2}[:.]\d{2}[-–—]\d{1,2}[:.]\d{2}')


def _content_columns(table: List[List[Optional[str]]]):
    """Which table columns carry class content (vs time / week / day).

    Wide tables (>=5 cols) put subject-subgroup cells in columns 3..5
    ('1 подгруппа', '2 подгруппа'); narrow tables (3-4 cols) keep the
    whole cell in the last column.
    """
    if not table or not table[0]:
        return []
    ncols = len(table[0])
    if ncols >= 5:
        return [3, 4, 5]
    return [ncols - 1] if ncols >= 1 else []


def _cell_text(cell: Optional[str]) -> str:
    if not cell:
        return ""
    return re.sub(r'\s+', ' ', cell.strip())


def _extract_lessons_tables(pdf_path: str):
    """
    Read the PDF as a real table (pdfplumber.extract_tables).
    Returns (lessons, notes):
      lessons = [{ 'day': day_ru, 'times': [...], 'streams': {col: text} }]
      notes   = set of day_ru where a 'День самостоятельной работы' row exists
    Each lesson groups all rows until the next row that carries a time label,
    keeping each subgroup column's text in a separate stream.
    """
    lessons = []
    notes = set()
    cur_day = None
    cur = None
    pending = {}  # col -> text buffered before the first time row of a lesson

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            try:
                tables = page.extract_tables() or []
            except Exception:
                tables = []
            for table in tables:
                if not table:
                    continue
                cols = _content_columns(table)
                pending_after_colon = False
                other_times = []
                for row in table:
                    if not row:
                        continue
                    for cell in (row or []):
                        if cell and cell.strip().lower() in DAYS_RU:
                            if cur is not None:
                                # flush the last lesson of the day, otherwise a
                                # trailing Accelerator block is lost
                                lessons.append(cur)
                                cur = None
                            cur_day = cell.strip().lower()
                            pending = {}
                            pending_after_colon = False
                    if cur_day is None:
                        continue
                    if any(cell and 'самостоятельной работы' in cell for cell in row):
                        notes.add(cur_day)
                    time_cell = row[0] if len(row) > 0 and row[0] else ""
                    times = list(dict.fromkeys(_TIME_MAIN_RE.findall(time_cell)))
                    has_other_time = bool(_TIME_ANY_RE.search(time_cell))
                    if times or has_other_time:
                        if cur is not None:
                            lessons.append(cur)
                            cur = None
                        if has_other_time and not times:
                            # row with a colon time ('17:00-18:00'): these are
                            # the Accelerator blocks. Keep them - the class name
                            # sits in the content column and the link one row
                            # below.
                            other_times = list(dict.fromkeys(
                                _TIME_ANY_RE.findall(time_cell)))
                            pending = {}
                            pending_after_colon = True
                    if times:
                        cur = {'day': cur_day, 'times': times, 'streams': {}}
                        if pending_after_colon:
                            pending = {}
                        for c, t in pending.items():
                            cur['streams'][c] = t
                        pending = {}
                        pending_after_colon = False
                    appender = cur if cur is not None else None
                    if appender is None:
                        if pending_after_colon and other_times:
                            # Accelerator block: open a lesson on the colon time
                            # so the name and the link below join one stream.
                            for c in cols:
                                if c < len(row) and row[c]:
                                    txt = _cell_text(row[c])
                                    if txt and txt.lower() not in ('верхняя', 'нижняя') \
                                            and txt != 'Время':
                                        cur = {'day': cur_day, 'times': other_times,
                                               'streams': {c: txt}}
                                        pending_after_colon = False
                                        break
                        if cur is not None:
                            continue
                        # buffer content that appears above the first time row
                        if pending_after_colon:
                            continue
                        for c in cols:
                            if c < len(row) and row[c]:
                                txt = _cell_text(row[c])
                                if txt and txt.lower() not in ('верхняя', 'нижняя') \
                                        and txt != 'Время':
                                    pending[c] = pending.get(c, "") + " " + txt
                        continue
                    for c in cols:
                        if c < len(row) and row[c]:
                            txt = _cell_text(row[c])
                            if txt and txt.lower() not in ('верхняя', 'нижняя') \
                                    and txt != 'Время':
                                appender['streams'].setdefault(c, "")
                                appender['streams'][c] += " " + txt
    if cur is not None and cur['times']:
        lessons.append(cur)
    return lessons, notes


def extract_schedule(pdf_path: str) -> Dict:
    """
    Build the schedule from the PDF.

    Primary path reads the timetable as a real pdfplumber table so that the
    '1 подгруппа' / '2 подгруппа' cells are parsed independently (same
    discipline, separate instructor and room). Falls back to the old
    line-based text scan when the PDF has no usable table.
    """
    schedule = OrderedDict()
    for day_ru in DAYS_RU:
        schedule[DAY_MAP[day_ru]] = {"time_slots": OrderedDict(), "note": ""}
    try:
        lessons, notes = _extract_lessons_tables(pdf_path)
    except Exception:
        lessons, notes = [], set()

    if len(lessons) < 3:  # no usable table -> fall back to the text scan
        legacy = _extract_schedule_legacy(pdf_path)
        for day_en, info in legacy.items():
            schedule[day_en]["time_slots"] = info["time_slots"]
            schedule[day_en]["note"] = info["note"]
        return schedule

    by_day = OrderedDict()
    for lesson in lessons:
        if lesson['day'] in notes:
            continue
        by_day.setdefault(lesson['day'], []).append(lesson)

    for day_ru, lesson_list in by_day.items():
        day_en = DAY_MAP[day_ru]
        weekday = WEEKDAY_MAP[day_en]
        if day_ru in notes:
            schedule[day_en]["note"] = "День самостоятельной работы"
            continue

        all_times = []
        for lesson in lesson_list:
            all_times.extend(lesson['times'])
        lesson_breaks = _lesson_breaks(all_times)

        for lesson in lesson_list:
            for t_str in lesson['times']:
                if t_str not in lesson_breaks:
                    continue
                breaks = lesson_breaks[t_str]
                break_time = ", ".join(breaks)
                classes = []
                for col in sorted(lesson['streams']):
                    stream = lesson['streams'][col]
                    if not stream.strip():
                        continue
                    classes.extend(_parse_classes(stream, weekday))
                schedule[day_en]["time_slots"][t_str] = {
                    "break": break_time,
                    "classes": classes,
                }

    return schedule


def _extract_schedule_legacy(pdf_path: str) -> Dict:
    text = _extract_text(pdf_path)
    lines = text.split('\n')

    day_contents = {d: "" for d in DAYS_RU}
    current_day = None

    for line in lines:
        line = line.strip()
        if not line:
            continue
        found = False
        for day_ru in DAYS_RU:
            if re.search(rf'\b{day_ru}\b', line, re.IGNORECASE):
                current_day = day_ru
                found = True
                break
        if found and current_day:
            day_contents[current_day] = line
        elif current_day and not found:
            day_contents[current_day] += " " + line

    schedule = OrderedDict()
    for day_ru in DAYS_RU:
        day_en = DAY_MAP[day_ru]
        weekday = WEEKDAY_MAP[day_en]
        content = day_contents.get(day_ru, "")
        schedule[day_en] = {"time_slots": OrderedDict(), "note": ""}

        if "День самостоятельной работы" in content:
            schedule[day_en]["note"] = "День самостоятельной работы"
            continue

        time_pattern = re.compile(r'(\d{2}\.\d{2}-\d{2}\.\d{2})')
        matches = list(time_pattern.finditer(content))
        if not matches:
            continue

        lesson_breaks = _lesson_breaks([m.group(1) for m in matches])
        lesson_matches = [m for m in matches if m.group(1) in lesson_breaks]

        for i, tm in enumerate(lesson_matches):
            t_str = tm.group(1)
            s = tm.start()
            e = lesson_matches[i + 1].start() if i + 1 < len(lesson_matches) else len(content)
            block = content[s:e].strip()

            breaks = lesson_breaks[t_str]
            break_time = ", ".join(breaks)

            class_text = re.sub(r'\d{2}\.\d{2}[-–—]\d{2}\.\d{2}', ' ', block)
            class_text = class_text.strip()

            schedule[day_en]["time_slots"][t_str] = {
                "break": break_time,
                "classes": _parse_classes(class_text, weekday),
            }

    return schedule


# ================= Group-name helpers =================
# Naming logic:  FACULTY-CODE<YEAR>-SUBGROUP
#   'АМ-Б25-1'     -> faculty-code 'АМ-Б', year 25, subgroup '1'
#   'ФЛОЗ-М24-1-12'-> faculty-code 'ФЛОЗ-М', year 24, subgroup '1-12'
#   'Ю-СПО26'      -> faculty-code 'Ю-СПО', year 26, no subgroup
# The part after the year (the -1, -2, -12, ...) is the SUBGROUP:
# it must never be treated as part of the year.
def group_parts(group_name: str):
    """
    Split a group name into (faculty_code, year, subgroup).

        'АМ-Б25-1'    -> ('АМ-Б', 25, '1')
        'ДОЗ-Б23-1-1' -> ('ДОЗ-Б', 23, '1-1')
        'АМ-Б26'      -> ('АМ-Б', 26, '')
        'ИВТ22'       -> ('ИВТ', 22, '')
    Returns (None, None, '') if the name cannot be parsed.
    """
    if not group_name:
        return None, None, ""
    m = re.match(r'^(.*?[А-Яа-яA-Za-z])(\d{2})(?:-(.*))?$', group_name)
    if not m:
        return None, None, ""
    year = int(m.group(2))
    subgroup = m.group(3) if m.group(3) else ""
    return m.group(1), year, subgroup


def group_year(group_name: str) -> Optional[int]:
    """
    Extract the 2-digit year from a group name:
        'МОЗ-Б25'   -> 25
        'ПИ-Б21-1'  -> 21  (the '-1' is a subgroup, not the year)
        'ФЛОЗ-М25-12' -> 25 (the '-12' is a subgroup, not the year)
    Returns None if nothing found.
    """
    _, year, _ = group_parts(group_name)
    return year


def group_subgroup(group_name: str) -> str:
    """
    Extract the subgroup from a group name (the part after the year):
        'АМ-Б25-1'     -> '1'
        'ДОЗ-Б23-1-1'  -> '1-1'
        'ФЛОЗ-М25-12'  -> '12'
        'АМ-Б26'       -> ''
    """
    _, _, subgroup = group_parts(group_name)
    return subgroup


def is_older_than(group_name: str, current_year: int, max_age: int) -> bool:
    """
    True if the group's year is strictly more than `max_age` years
    older than `current_year`.
        current_year=26, max_age=5:
            25 → False   (1 year, keep)
            21 → False   (5 years, keep)
            20 → True    (6 years, delete)
    """
    y = group_year(group_name)
    if y is None:
        return False
    full_year = 2000 + y
    full_ref = 2000 + current_year
    return (full_ref - full_year) > max_age