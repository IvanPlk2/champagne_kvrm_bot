import html
import re
from datetime import date, datetime
from typing import Optional

from const import MSK_TZ
from utils import normalize_name

MONTHS = {
    "января": 1,
    "февраля": 2,
    "марта": 3,
    "апреля": 4,
    "мая": 5,
    "июня": 6,
    "июля": 7,
    "августа": 8,
    "сентября": 9,
    "октября": 10,
    "ноября": 11,
    "декабря": 12,
}

_MONTH_PATTERN = "|".join(MONTHS)
DATE_RE = re.compile(
    rf"(\d{{1,2}})\s+({_MONTH_PATTERN})\s+\(([а-яё]{{2}})\)",
    re.IGNORECASE,
)
EVENT_RE = re.compile(
    r"(.+?)\s+-\s+(.+?)\s+\((\d{1,2}:\d{2})\)(?:\s+(\S+))?"
)
POST_UPDATED_RE = re.compile(
    r"Пост обновлён\s+(\d{2})\.(\d{2})\.(\d{4})",
    re.IGNORECASE,
)
MESSAGE_TEXT_RE = re.compile(
    r'<div class="[^"]*tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>',
    re.IGNORECASE | re.DOTALL,
)


def normalize_announce_name(value: str) -> str:
    text = normalize_name(value)
    text = text.strip().casefold()
    return text


def event_fingerprint(name: str, place: str, date_start: datetime) -> str:
    when = date_start.strftime("%Y-%m-%d %H:%M")
    return "|".join([
        when,
        normalize_announce_name(name),
        normalize_announce_name(place),
    ])


def html_fragment_to_text(fragment: str) -> str:
    text = re.sub(r"(?i)<br\s*/?>", "\n", fragment)
    text = re.sub(r"(?i)</p>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text)


def extract_channel_messages(page_html: str) -> list[str]:
    messages = []
    for match in MESSAGE_TEXT_RE.finditer(page_html or ""):
        text = html_fragment_to_text(match.group(1)).strip()
        if text:
            messages.append(text)
    return messages


def _parse_post_updated(text: str) -> tuple[Optional[int], Optional[int]]:
    match = POST_UPDATED_RE.search(text or "")
    if not match:
        return None, None
    return int(match.group(3)), int(match.group(2))


def _infer_year(
    month: int,
    post_year: Optional[int],
    post_month: Optional[int],
    today: date,
) -> int:
    if post_year is None:
        return today.year
    year = post_year
    if post_month is not None and month > post_month + 6:
        year -= 1
    elif post_month is not None and month < post_month - 6:
        year += 1
    return year


def parse_sync_list(text: str, today: Optional[date] = None) -> list[dict]:
    """
    Разбирает список вида:
      08 сентября (вт)
      Крафт-12 - Carrot (19:30) 2100₽
    """
    if not text:
        return []
    if today is None:
        today = datetime.now(MSK_TZ).date()

    post_year, post_month = _parse_post_updated(text)
    events = []
    date_matches = list(DATE_RE.finditer(text))
    for index, date_match in enumerate(date_matches):
        day = int(date_match.group(1))
        month = MONTHS[date_match.group(2).lower()]
        year = _infer_year(month, post_year, post_month, today)
        try:
            event_date = date(year, month, day)
        except ValueError:
            continue

        start = date_match.end()
        end = date_matches[index + 1].start() if index + 1 < len(date_matches) else len(text)
        chunk = text[start:end]
        for event_match in EVENT_RE.finditer(chunk):
            name = event_match.group(1).strip(" \n\t.,;")
            place = event_match.group(2).strip(" \n\t.,;")
            time_text = event_match.group(3)
            price = (event_match.group(4) or "").strip()
            if not name or not place:
                continue
            try:
                hours, minutes = (int(part) for part in time_text.split(":"))
                date_start = datetime(year, month, day, hours, minutes)
            except ValueError:
                continue
            events.append({
                "name": name,
                "place": place,
                "price": price,
                "date_start": date_start,
                "event_date": event_date,
                "fingerprint": event_fingerprint(name, place, date_start),
            })
    return events


def looks_like_sync_list(text: str) -> bool:
    lowered = (text or "").casefold()
    if "список синхронов" in lowered:
        return True
    return bool(DATE_RE.search(text or "") and EVENT_RE.search(text or ""))


def select_latest_sync_list(messages: list[str]) -> Optional[str]:
    for text in reversed(messages or []):
        if looks_like_sync_list(text):
            return text
    return None


def _name_match_score(query: str, tournament: dict) -> int:
    name = normalize_announce_name(tournament.get("name") or "")
    long_name = normalize_announce_name(tournament.get("long_name") or "")
    if not query:
        return 0
    if query == name or (long_name and query == long_name):
        return 3
    if name.startswith(query) or query.startswith(name):
        return 2
    if query in name or (long_name and query in long_name):
        return 1
    return 0


def match_event_to_existing_game(event: dict, games: list[dict]) -> Optional[dict]:
    query = normalize_announce_name(event.get("name") or "")
    if not query:
        return None

    scored = []
    for game in games:
        score = _name_match_score(
            query,
            {"name": game.get("name") or "", "long_name": ""},
        )
        if score >= 2:
            scored.append((score, game))
    if not scored:
        return None

    exact = [game for score, game in scored if score >= 3]
    candidates = exact or ([scored[0][1]] if len(scored) == 1 else [])
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]

    event_when = event.get("date_start")
    if event_when is None:
        return candidates[0]

    def _distance(game: dict) -> float:
        date_start = game.get("date_start")
        if date_start is None:
            return float("inf")
        return abs((date_start - event_when).total_seconds())

    return min(candidates, key=_distance)


def match_event_to_tournament(
    event: dict,
    tournaments: list[dict],
    covers_event,
) -> Optional[dict]:
    query = normalize_announce_name(event.get("name") or "")
    if not query:
        return None

    covering = [
        item for item in tournaments
        if item.get("id") is not None and covers_event(item, event["date_start"])
    ]
    pools = [covering, tournaments]
    for pool in pools:
        scored = []
        for item in pool:
            if item.get("id") is None:
                continue
            score = _name_match_score(query, item)
            if score:
                scored.append((score, item))
        if not scored:
            continue
        scored.sort(key=lambda row: (-row[0], row[1].get("id") or 0))
        best_score, best = scored[0]
        tied = [
            item for score, item in scored
            if score == best_score and item["id"] != best["id"]
        ]
        if tied:
            continue
        if best_score >= 2:
            return best
    return None
