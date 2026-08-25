from datetime import datetime, timedelta, timezone
from typing import Optional


UTC_TZ = timezone.utc
MSK_TZ = timezone(timedelta(hours=3))


def parse_rating_datetime(value) -> Optional[datetime]:
    """Парсит dateStart/dateEnd с сайта рейтинга (время в GMT)."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC_TZ)
    return dt.astimezone(UTC_TZ)


def to_msk_naive(dt: Optional[datetime]) -> Optional[datetime]:
    """Переводит GMT-время сайта рейтинга в наивное локальное GMT+3."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC_TZ)
    return dt.astimezone(MSK_TZ).replace(tzinfo=None)


def format_msk_window(
    date_start: Optional[datetime],
    date_end: Optional[datetime],
) -> Optional[str]:
    start = to_msk_naive(date_start)
    end = to_msk_naive(date_end)
    if start is None and end is None:
        return None
    start_txt = start.strftime("%d.%m.%y %H:%M") if start else "?"
    end_txt = end.strftime("%d.%m.%y %H:%M") if end else "?"
    return f"{start_txt} — {end_txt}"


def is_datetime_in_rating_window(
    local_naive: datetime,
    date_start: Optional[datetime],
    date_end: Optional[datetime],
) -> bool:
    """
    Проверяет, что локальное время игры (GMT+3) попадает
    в интервал dateStart..dateEnd сайта рейтинга (GMT).
    """
    if date_start is None and date_end is None:
        return True

    local_aware = local_naive.replace(tzinfo=MSK_TZ)

    if date_start is not None:
        start = date_start if date_start.tzinfo else date_start.replace(tzinfo=UTC_TZ)
        if local_aware < start:
            return False

    if date_end is not None:
        end = date_end if date_end.tzinfo else date_end.replace(tzinfo=UTC_TZ)
        if local_aware > end:
            return False

    return True


def get_when_text(date_start, date_end, is_festival):
    if date_start is None:
        return ""

    if is_festival:
        if date_end is None or date_start.date() == date_end.date():
            return date_start.strftime("%d.%m.%y")
        start_txt = date_start.strftime("%d.%m.%y")
        end_txt = date_end.strftime("%d.%m.%y")
        return "-".join([start_txt, end_txt])

    return date_start.strftime("%d.%m.%y %H:%M")
