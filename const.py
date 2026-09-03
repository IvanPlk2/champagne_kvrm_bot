from datetime import timedelta, timezone
from enum import Enum


UTC_TZ = timezone.utc
MSK_TZ = timezone(timedelta(hours=3))

ANNOUNCE_OFFER_CALLBACK = "ann_offer"
WEEK_ANNOUNCE_PAGE_URL = "https://t.me/s/WeekChgkSPB"


class AnnounceOfferStatus(str, Enum):
    OFFERED = "offered"
    ADDED = "added"
    IGNORED = "ignored"
