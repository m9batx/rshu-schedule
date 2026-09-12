import re
import os
import pdfplumber
from collections import OrderedDict
from datetime import datetime, timedelta
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
    return re.sub(r'[\x00-\x1f\x7f-\x9f]', '', text)


# ================= Group name from filename =================
def extract_group(pdf_path: str) -> Optional[str]:
    filename = os.path.splitext(os.path.basename(pdf_path))[0]
    for pattern in [
        r'([А-Яа-я]{2,4}-\d?[А-Яа-я]?\d{2,3})',
        r'([A-Za-z]{2,4}-\d?[A-Za-z]?\d{2,3})',
    ]:
        m = re.search(pattern, filename)
        if m:
            return m.group(1).strip()
    return filename


# ================= Dates expansion =================
def _expand_dates(date_strings: List[str], weekday: int) -> List[str]:
    expanded = []
    for item in date_strings:
        item = item.strip()
        if '–' in item or '-' in item:
            parts = re.split(r'\s*[–-]\s*', item)
            if len(parts) == 2:
                try:
                    start = datetime.strptime(parts[0].strip(), "%d.%m.%y")
                    end = datetime.strptime(parts[1].strip(), "%d.%m.%y")
                except ValueError:
                    expanded.append(item)
                    continue
                current = start
                days_ahead = weekday - current.weekday()
                if days_ahead < 0:
                    days_ahead += 7
                current += timedelta(days=days_ahead)
                while current <= end:
                    expanded.append(current.strftime("%d.%m.%y"))
                    current += timedelta(days=7)
            else:
                expanded.append(item)
        else:
            expanded.append(item)
    return expanded


# ================= Class block parser =================
def _parse_classes(block_text: str, weekday: int) -> List[Dict]:
    block_text = re.sub(r'\s*Верхняя\s*|\s*Нижняя\s*', ' ', block_text)
    block_text = re.sub(r'\s+', ' ', block_text).strip()

    class_pattern = re.compile(
        r'([А-Яа-я\s\-\.]+?)\s*\((лек|прак|сем|лаб|срс|конс|экз|зач)\)'
    )
    matches = list(class_pattern.finditer(block_text))
    if not matches:
        return []

    classes = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(block_text)
        raw = re.sub(r'\s+', ' ', block_text[start:end].strip())

        instr = re.search(
            r'(проф\.|доц\.|ст\.\s*преп\.|асс\.|преп\.)\s+([А-Я][а-я]+\s+[А-Я][а-я]+\s+[А-Я][а-я]+)',
            raw
        )
        loc = re.search(
            r'(Ауд\.\s+\d+\s+\d+\s+корпус\s*\([^)]+\)|Дистанционная\s+поддержка)',
            raw
        )

        raw_dates = []
        for d_str in re.findall(
            r'\((\d{2}\.\d{2}\.\d{2}(?:\s*[–-]\s*\d{2}\.\d{2}\.\d{2})?|\d{2}\.\d{2}\.\d{2}(?:,\s*\d{2}\.\d{2}\.\d{2})*)\)',
            raw
        ):
            if '–' in d_str or '-' in d_str:
                raw_dates.append(d_str.strip())
            else:
                raw_dates.extend([x.strip() for x in d_str.split(',') if x.strip()])

        classes.append({
            "discipline": m.group(1).strip(),
            "type": m.group(2).strip(),
            "instructor": instr.group(0).strip() if instr else "",
            "location": loc.group(0).strip() if loc else "",
            "dates": _expand_dates(raw_dates, weekday),
        })
    return classes


# ================= Full schedule =================
def extract_schedule(pdf_path: str) -> Dict:
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
        times = list(time_pattern.finditer(content))
        if not times:
            continue

        for i, tm in enumerate(times):
            t_str = tm.group(1)
            s = tm.start()
            e = times[i + 1].start() if i + 1 < len(times) else len(content)
            block = content[s:e].strip()

            brk = re.search(r'перерыв\s+(\d{2}\.\d{2}-\d{2}\.\d{2})', block)
            break_time = brk.group(1) if brk else ""

            class_text = re.sub(r'^\s*\d{2}\.\d{2}-\d{2}\.\d{2}', '', block)
            class_text = re.sub(r'перерыв\s+\d{2}\.\d{2}-\d{2}\.\d{2}', '', class_text).strip()

            schedule[day_en]["time_slots"][t_str] = {
                "break": break_time,
                "classes": _parse_classes(class_text, weekday),
            }

    return schedule


# ================= Group-year helpers =================
def group_year(group_name: str) -> Optional[int]:
    """
    Extract the 2-digit year from a group name:
        'МОЗ-Б25' -> 25
        'ПИ-Б21'  -> 21
        'ИВТ22'   -> 22
    Returns None if nothing found.
    """
    if not group_name:
        return None
    matches = re.findall(r'(\d{2})', group_name)
    if not matches:
        return None
    try:
        return int(matches[-1])
    except ValueError:
        return None


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