from datetime import date
from typing import Optional

import httpx

from utils import parse_rating_datetime

# В текущем API рейтинга: 3 — «Синхрон».
TOURNAMENT_TYPE_SYNCHRON = 3


class RatingAPI:
    BASE_URL = "https://api.rating.chgk.net"

    def __init__(self, timeout: float = 10.0):
        self.timeout = timeout
        self.client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            timeout=timeout,
        )

    async def close(self):
        await self.client.aclose()

    def _parse_tournament(self, data: dict):
        return {
            "id": data.get("id"),
            "name": data.get("name"),
            "is_festival": (data.get("type") or {}).get('id') in {2, 6, "2", "6"},
            "difficulty_level": data.get("difficultyForecast"),
            "date_start": parse_rating_datetime(data.get("dateStart")),
            "date_end": parse_rating_datetime(data.get("dateEnd")),
        }

    async def get_tournament(self, tournament_id: int):
        response = await self.client.get(
            f"/tournaments/{tournament_id}"
        )
        response.raise_for_status()
        return self._parse_tournament(response.json())

    async def list_synchrons(
        self,
        date_end_from: date,
        date_end_to: date,
        language: str = "ru",
        items_per_page: int = 50,
        name: Optional[str] = None,
    ):
        params = {
            "type": TOURNAMENT_TYPE_SYNCHRON,
            "language": language,
            "dateEnd[after]": date_end_from.isoformat(),
            "dateEnd[before]": date_end_to.isoformat(),
            "itemsPerPage": items_per_page,
        }
        if name:
            params["name"] = name

        response = await self.client.get(
            "/tournaments.json",
            params=params,
        )
        response.raise_for_status()
        data = response.json()
        if isinstance(data, dict):
            data = data.get("hydra:member") or data.get("items") or []

        tournaments = [
            self._parse_tournament(item)
            for item in data
            if isinstance(item, dict)
        ]
        if name:
            needle = name.casefold()
            tournaments = [
                item
                for item in tournaments
                if needle in (item.get("name") or "").casefold()
            ]
        tournaments.sort(
            key=lambda item: (
                item.get("date_start") is None,
                item.get("date_start"),
                item.get("date_end") is None,
                item.get("date_end"),
                item.get("id") or 0,
            )
        )
        return tournaments

    async def get_player(self, player_id: int):
        response = await self.client.get(
            f"/players/{player_id}"
        )
        response.raise_for_status()
        data = response.json()

        return {
            "id": data.get("id"),
            "name": data.get("name"),
            "surname": data.get("surname"),
            "patronymic": data.get("patronymic")
        }
