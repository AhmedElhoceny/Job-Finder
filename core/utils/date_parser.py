from datetime import datetime, timedelta
import re
from typing import Optional

# Current reference date (November 2026)
REFERENCE_DATE = datetime(2026, 11, 24)

MONTHS_MAP = {
    "jan": 1, "january": 1, "يناير": 1, "janvier": 1,
    "feb": 2, "february": 2, "فبراير": 2, "février": 2, "fevrier": 2,
    "mar": 3, "march": 3, "مارس": 3, "mars": 3,
    "apr": 4, "april": 4, "أبريل": 4, "ابريل": 4, "avril": 4,
    "may": 5, "مايو": 5, "mai": 5,
    "jun": 6, "june": 6, "يونيو": 6, "juin": 6,
    "jul": 7, "july": 7, "يوليو": 7, "juillet": 7,
    "aug": 8, "august": 8, "أغسطس": 8, "اغسطس": 8, "août": 8, "aout": 8,
    "sep": 9, "september": 9, "سبتمبر": 9, "septembre": 9,
    "oct": 10, "october": 10, "أكتوبر": 10, "اكتوبر": 10, "octobre": 10,
    "nov": 11, "november": 11, "نوفمبر": 11, "novembre": 11,
    "dec": 12, "december": 12, "ديسمبر": 12, "décembre": 12, "decembre": 12,
}


def parse_posting_age_days(date_text: Optional[str], ref_date: Optional[datetime] = None) -> Optional[int]:
    """Parses relative or absolute date string and returns estimated age in days.

    Returns None if date could not be parsed.
    """
    if not date_text or not date_text.strip():
        return None

    ref = ref_date or REFERENCE_DATE
    text = date_text.strip().lower()

    # 1. Immediate / same-day
    if any(k in text for k in [
        "today", "just now", "hour", "hr", "minute", "min", "اليوم", "الآن", "ساعة", "دقيقة",
        "aujourd'hui", "aujourdhui", "오늘", "本日", "今天"
    ]):
        return 0

    # 2. Yesterday / 1 day
    if any(k in text for k in ["yesterday", "أمس", "امس", "hier", "어제", "昨日", "昨天"]):
        return 1

    # 3. Explicit "30+ days ago" or "over a month ago"
    if "30+" in text or "أكثر من شهر" in text or "اكثر من شهر" in text or "+ de 30 jours" in text:
        return 35

    # 4. French relative days / weeks / months
    fr_days = re.search(r"(?:il y a\s*)?(\d+)\s*jour", text)
    if fr_days:
        return int(fr_days.group(1))
    fr_weeks = re.search(r"(?:il y a\s*)?(\d+)\s*semaine", text)
    if fr_weeks:
        return int(fr_weeks.group(1)) * 7
    fr_months = re.search(r"(?:il y a\s*)?(\d+)\s*mois", text)
    if fr_months:
        return int(fr_months.group(1)) * 30

    # 5. Korean relative days / weeks / months
    kr_days = re.search(r"(\d+)\s*일\s*전", text)
    if kr_days:
        return int(kr_days.group(1))
    kr_weeks = re.search(r"(\d+)\s*주\s*전", text)
    if kr_weeks:
        return int(kr_weeks.group(1)) * 7
    kr_months = re.search(r"(\d+)\s*개월\s*전", text)
    if kr_months:
        return int(kr_months.group(1)) * 30

    # 6. Japanese relative days / weeks / months
    jp_days = re.search(r"(\d+)\s*日\s*前", text)
    if jp_days:
        return int(jp_days.group(1))
    jp_weeks = re.search(r"(\d+)\s*週間\s*前", text)
    if jp_weeks:
        return int(jp_weeks.group(1)) * 7
    jp_months = re.search(r"(\d+)\s*(?:か月|ヶ月)\s*前", text)
    if jp_months:
        return int(jp_months.group(1)) * 30

    # 7. Chinese relative days / weeks / months
    cn_days = re.search(r"(\d+)\s*天前", text)
    if cn_days:
        return int(cn_days.group(1))
    cn_weeks = re.search(r"(\d+)\s*周前", text)
    if cn_weeks:
        return int(cn_weeks.group(1)) * 7
    cn_months = re.search(r"(\d+)\s*个月前", text)
    if cn_months:
        return int(cn_months.group(1)) * 30

    # 4. English relative days: e.g. '2 days ago', '7 days ago'
    day_match = re.search(r"(\d+)\s*(?:day|d\b)", text)
    if day_match:
        return int(day_match.group(1))

    # 5. English relative weeks: e.g. '2 weeks ago', '1 week ago'
    week_match = re.search(r"(\d+)\s*week", text)
    if week_match:
        return int(week_match.group(1)) * 7

    # 6. English relative months: e.g. '1 month ago' (typically >30 days), '2 months ago'
    month_match = re.search(r"(\d+)\s*month", text)
    if month_match:
        m_count = int(month_match.group(1))
        # '1 month ago' on job boards represents between 31 and 59 days
        return 32 if m_count == 1 else m_count * 30

    # 7. English relative years: e.g. '1 year ago'
    year_match = re.search(r"(\d+)\s*year", text)
    if year_match:
        return int(year_match.group(1)) * 365

    # 8. Arabic relative days: e.g. 'منذ يومين' (2), 'منذ 3 أيام', 'منذ 5 يوم'
    if "يومين" in text:
        return 2
    ar_days = re.search(r"منذ\s*(\d+)\s*(?:يوم|أيام|ايام)", text)
    if ar_days:
        return int(ar_days.group(1))

    # 9. Arabic relative weeks: e.g. 'منذ أسبوع' (7), 'منذ أسبوعين' (14), 'منذ 3 أسابيع'
    if "أسبوعين" in text or "اسبوعين" in text:
        return 14
    if "أسبوع" in text or "اسبوع" in text:
        return 7
    ar_weeks = re.search(r"منذ\s*(\d+)\s*(?:أسابيع|اسابيع|أسبوع|اسبوع)", text)
    if ar_weeks:
        return int(ar_weeks.group(1)) * 7

    # 10. Arabic relative months: e.g. 'منذ شهر', 'منذ شهرين'
    if "شهرين" in text:
        return 60
    if "شهر" in text:
        return 30
    ar_months = re.search(r"منذ\s*(\d+)\s*(?:أشهر|اشهر|شهور|شهر)", text)
    if ar_months:
        return int(ar_months.group(1)) * 30

    # 11. Absolute date: e.g. '17 Nov', '24 Nov' (GulfTalent style)
    day_month_match = re.search(r"(\d{1,2})\s+([a-zA-Z\u0621-\u064A]+)", text)
    if day_month_match:
        day_num = int(day_month_match.group(1))
        month_str = day_month_match.group(2).lower()
        if month_str in MONTHS_MAP:
            m_num = MONTHS_MAP[month_str]
            # Check for year e.g. '3 September 2026'
            yr_match = re.search(r"\b(202\d)\b", text)
            yr = int(yr_match.group(1)) if yr_match else ref.year

            try:
                dt = datetime(yr, m_num, day_num)
                delta = (ref - dt).days
                if delta >= 0:
                    return delta
            except ValueError:
                pass

    # 12. ISO format: '2026-11-20'
    iso_match = re.search(r"(\d{4})-(\d{2})-(\d{2})", text)
    if iso_match:
        try:
            dt = datetime(int(iso_match.group(1)), int(iso_match.group(2)), int(iso_match.group(3)))
            delta = (ref - dt).days
            if delta >= 0:
                return delta
        except ValueError:
            pass

    return None


def is_posted_within_last_month(date_text: Optional[str], max_days: int = 30) -> bool:
    """Returns True if the job was posted within max_days (default 30 days / 1 month).

    Returns False if posted > 30 days ago (e.g. '30+ days ago', '2 months ago').
    Defaults to True only if date is completely unparseable to avoid false drops.
    """
    days = parse_posting_age_days(date_text)
    if days is None:
        return True  # Give benefit of doubt if date is missing/unspecified
    return days <= max_days
