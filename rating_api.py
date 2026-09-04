from datetime import date
from typing import Optional

import httpx

from utils import parse_rating_datetime, normalize_name

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
            "long_name": data.get("longName"),
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
            "order[lastEditDate]": "ASC"
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
            data = data.get("items") or []

        tournaments = [
            self._parse_tournament(item)
            for item in data
            if isinstance(item, dict)
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

    async def match_by_long_name(self, date_end_from: date, date_end_to: date, query: str) -> list[dict]:

        def remove_spaces_and_dashes(text: str) -> str:
            return text.replace(" ", "").replace("-", "")

        def get_matched(needle, haystack):
            matched = []
            for item, name in haystack:
                if needle in name:
                    matched.append(item)
            return matched

        candidates = await self.list_synchrons(
            date_end_from=date_end_from,
            date_end_to=date_end_to,
            items_per_page=100,
        )
        needle = normalize_name(query or "").casefold()
        if not needle:
            return []

        haystack = [
            (item, normalize_name(item.get("long_name")).casefold())
            for item in candidates
        ]
        matched = get_matched(needle, haystack)
        if matched:
            return matched

        # Попробуем поискать без пробелов и тире:
        needle = remove_spaces_and_dashes(needle)
        haystack = [(item, remove_spaces_and_dashes(name)) for item, name in haystack]

        if len(needle) < 3:
            return []

        return get_matched(needle, haystack)

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

    def _parse_result_list(self, data):
        if isinstance(data, dict):
            data = data.get("items") or []
        if not isinstance(data, list):
            return []
        return [item for item in data if isinstance(item, dict)]

    def _parse_roster_player(self, member: dict) -> Optional[dict]:
        player = member.get("player") or {}
        player_id = player.get("id")
        if player_id is None:
            return None
        return {
            "id": int(player_id),
            "name": player.get("name"),
            "surname": player.get("surname"),
            "patronymic": player.get("patronymic"),
        }

    async def get_team_roster_at_tournament(
        self,
        tournament_id: int,
        team_id: int,
    ) -> list[dict]:
        response = await self.client.get(
            f"/tournaments/{tournament_id}/results",
            params={"includeTeamMembers": 1},
            timeout=15.0,
        )
        response.raise_for_status()
        for row in self._parse_result_list(response.json()):
            team = row.get("team") or {}
            if team.get("id") != team_id:
                continue
            players = []
            for member in row.get("teamMembers") or []:
                if not isinstance(member, dict):
                    continue
                parsed = self._parse_roster_player(member)
                if parsed:
                    players.append(parsed)
            return players
        return []
