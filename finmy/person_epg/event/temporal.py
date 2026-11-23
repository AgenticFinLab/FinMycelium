"""Civil-time comparisons for evidence-backed Action occurrences."""
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from itertools import combinations


PARTS = ('morning', 'noon', 'afternoon', 'evening')
CLOCK = r'(?:[01][0-9]|2[0-3]):[0-5][0-9](?::[0-5][0-9])?'
OFFSET = r'(?:Z|(?:\+|-(?!00:00))(?:(?:0[0-9]|1[0-3]):[0-5][0-9]|14:00))'
_PART_WORDS = {
    'morning': r'\bmorning\b|上午|早晨|早上',
    'noon': r'\bnoon\b|中午|正午',
    'afternoon': r'\bafternoon\b|下午',
    'evening': r'\b(?:evening|tonight)\b|傍晚|晚上|当晚|今晚|昨晚',
}
_QUALIFIED = re.compile(
    r'\b(?:before|after|until|since|between|by|from|not|prior to|around|about)\b'
    r'|之前|之后|以前|以后|截至|大约|直到', re.I)
_METADATA = re.compile(r'\b(?:published|updated|retrieved|posted)\b|发布时间|更新时间', re.I)
_ZONE = re.compile(r'\b(?:UTC|GMT|EST|EDT|CST|CDT|MST|MDT|PST|PDT|BST|CET|CEST)\b|[+-]\d\d:\d\d', re.I)


def single_day(time, bounds):
    return bool(bounds and (bounds[1] - bounds[0]).days == 1 and
                time.get('kind') == 'occurrence_window' and time.get('text') and
                time.get('start_precision') == time.get('end_precision') == 'day')


def quoted_daypart(text):
    """Legacy display only. Ignore bounds, datelines, zones and mixed expressions."""
    if not text or _QUALIFIED.search(text) or _METADATA.search(text) or _ZONE.search(text):
        return None
    found = [p for p, pattern in _PART_WORDS.items() if re.search(pattern, text, re.I)]
    return found[0] if len(found) == 1 else None


def publication_day(text, published_at):
    """Resolve a single publisher-relative civil day; never use an update or fetch date."""
    if not isinstance(published_at, str) or not re.match(r'^\d{4}-\d\d-\d\d(?:$|[ T])', published_at):
        return None
    try:
        day = datetime.fromisoformat(published_at.replace("Z", "+00:00")).date()
        relative = relative_days(text)
        if len(relative) == 1:
            return day + timedelta(days=relative.pop())
    except (ValueError, OverflowError):
        pass
    return None


def relative_days(text):
    words = ((0, r'\b(?:today|tonight|this (?:morning|afternoon|evening))\b|今天|今日|今晚|今早'),
             (-1, r'\b(?:yesterday|last night)\b|昨天|昨日|昨晚|昨夜'))
    return {n for n, pattern in words if re.search(pattern, text or '', re.I)}


def solely_relative(text):
    """A standalone deictic expression needs an inference to acquire a calendar date."""
    return bool(re.fullmatch(
        r'(?:today|yesterday)(?: (?:morning|afternoon|evening))?|tonight|last night|'
        r'this (?:morning|afternoon|evening)|(?:今天|今日|昨天|昨日)(?:上午|下午|晚上)?|今早|今晚|昨晚|昨夜',
        (text or '').strip(), re.I))


def _offset_seconds(offset):
    if offset == 'Z':
        return 0
    hours, minutes = map(int, offset[1:].split(':'))
    return (1 if offset[0] == '+' else -1) * (hours * 60 + minutes) * 60


def _clock_window(value):
    hh, mm, *ss = map(int, value.split(':'))
    start = hh * 3600 + mm * 60 + (ss[0] if ss else 0)
    return start, start + (1 if ss else 60)


@dataclass(frozen=True)
class ActionWindow:
    start: date
    end: date
    intraday: str | None = None
    offset: str | None = None

    def before(self, other):
        """Compare only disjoint supported windows; labels never imply a made-up hour."""
        a, b = self.intraday, other.intraday
        offset_a = _offset_seconds(self.offset) if self.offset else None
        offset_b = _offset_seconds(other.offset) if other.offset else None
        same_frame = offset_a == offset_b
        clock_a, clock_b = a and a not in PARTS, b and b not in PARTS
        # On one civil clock, compare named parts and the unambiguous sides of
        # midday. Afternoon/evening have no source-independent boundary hour.
        midday = 12 * 3600
        if same_frame and self.start == other.start:
            if a in PARTS and b in PARTS:
                return PARTS.index(a) < PARTS.index(b)
            if clock_a and b in PARTS:
                return b != 'morning' and _clock_window(a)[1] <= midday
            if a in PARTS and clock_b:
                start = _clock_window(b)[0]
                return (a == 'morning' and start >= midday) or (a == 'noon' and start > midday)

        def bound(window, clock, offset, end):
            if clock:
                value = window.start.toordinal() * 86400 + _clock_window(window.intraday)[int(end)]
            else:
                value = (window.end if end else window.start).toordinal() * 86400
            if same_frame:
                return value
            # An unstated zone cannot settle order near midnight in another frame.
            adjustment = offset if offset is not None else (-14 if end else 14) * 3600
            return value - adjustment

        return bound(self, clock_a, offset_a, True) <= bound(other, clock_b, offset_b, False)

    def label(self, time):
        if self.intraday:
            return ' · '.join(filter(None, (self.start.isoformat(), self.intraday, self.offset)))
        precision = time.get('start_precision')
        if precision == time.get('end_precision'):
            if (precision == 'year' and self.end.year == self.start.year + 1
                    and self.start.month == self.end.month == self.start.day == self.end.day == 1):
                return str(self.start.year)
            months = (self.end.year - self.start.year) * 12 + self.end.month - self.start.month
            if precision == 'month' and self.start.day == self.end.day == 1 and months == 1:
                return self.start.strftime('%Y-%m')
        if (self.end - self.start).days == 1:
            return self.start.isoformat()
        return time.get('text') or f'[{self.start}, {self.end})'


def time_pairs(windows):
    for a, b in combinations(windows, 2):
        first, second = windows[a], windows[b]
        if first and second:
            if first.before(second):
                yield a, b
            elif second.before(first):
                yield b, a


def descendants(edges, start):
    seen = set()
    stack = list(edges.get(start, ()))
    while stack:
        node = stack.pop()
        if node not in seen:
            seen.add(node)
            stack.extend(edges.get(node, ()))
    return seen
