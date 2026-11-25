import sys
from pathlib import Path
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.utils.date_parser import parse_posting_age_days, is_posted_within_last_month

test_cases = [
    ("Today", True),
    ("2 hours ago", True),
    ("Yesterday", True),
    ("2 days ago", True),
    ("7 days ago", True),
    ("25 days ago", True),
    ("30+ days ago", False),
    ("1 month ago", False),
    ("2 months ago", False),
    ("24 Nov", True),
    ("17 Nov", True),
    ("10 Oct", False),
    ("3 September 2026", False),
    ("منذ يومين", True),
    ("منذ أسبوع", True),
    ("منذ شهرين", False),
    ("Aujourd'hui", True),
    ("Hier", True),
    ("Il y a 3 jours", True),
    ("Il y a 2 mois", False),
    ("오늘", True),
    ("3일 전", True),
    ("2개월 전", False),
    ("本日", True),
    ("5日前", True),
    ("2ヶ月前", False),
    ("今天", True),
    ("4天前", True),
    ("3个月前", False),
]

all_passed = True
for text, expected in test_cases:
    days = parse_posting_age_days(text)
    within = is_posted_within_last_month(text, max_days=30)
    passed = within == expected
    if not passed:
        all_passed = False
    print(f"[{'PASS' if passed else 'FAIL'}] '{text}' -> days={days}, within_month={within}")

if all_passed:
    print("\nALL DATE PARSING TESTS PASSED!")
else:
    print("\nSOME TESTS FAILED")
