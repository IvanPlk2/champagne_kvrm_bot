
import requests


class RatingChgkAPI:
    BASE_URL = "https://api.rating.chgk.net"

    def __init__(self, timeout: int = 10):
        self.timeout = timeout

    def get_tournament(self, id: int) -> dict:
        """
        Получает информацию о турнире.

        Возвращает:
        {
            "id": ...,
            "name": ...
        }

        При HTTP-коде, отличном от 200, выбрасывает исключение.
        """
        url = f"{self.BASE_URL}/tournaments/{id}"

        response = requests.get(
            url,
            timeout=self.timeout
        )

        if response.status_code != 200:
            raise RuntimeError(
                f"Rating CHGK API returned HTTP {response.status_code}"
            )

        data = response.json()
        return {
            "id": data.get("id"),
            "name": data.get("name"),
            "is_festival": (data.get("type") or {}).get('id') in {2, 6, "2", "6"}
        }

    def get_player(self, id: int) -> dict:
        """
        Получает информацию об игроке.

        Возвращает:
        {
            "id": ...,
            "name": ...,
            "surname": ...,
            "patronymic": ...
        }

        При HTTP-коде, отличном от 200, выбрасывает исключение.
        """
        url = f"{self.BASE_URL}/players/{id}"

        response = requests.get(
            url,
            timeout=self.timeout
        )

        if response.status_code != 200:
            raise RuntimeError(
                f"Rating CHGK API returned HTTP {response.status_code}"
            )

        data = response.json()

        return {
            "id": data.get("id"),
            "name": data.get("name"),
            "surname": data.get("surname"),
            "patronymic": data.get("patronymic")
        }