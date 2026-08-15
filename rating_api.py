

import httpx


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

    async def get_tournament(self, tournament_id: int):
        response = await self.client.get(
            f"/tournaments/{tournament_id}"
        )
        response.raise_for_status()
        data = response.json()
        return {
            "id": data.get("id"),
            "name": data.get("name"),
            "is_festival": (data.get("type") or {}).get('id') in {2, 6, "2", "6"}
        }


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
