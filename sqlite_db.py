from contextlib import closing
from datetime import datetime
from typing import Optional
import sqlite3
from sqlite3 import Error


def _adapt_datetime(value: datetime) -> str:
    return value.isoformat(sep=" ", timespec="seconds")


def _convert_timestamp(value: bytes) -> datetime:
    text = value.decode()
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return datetime.strptime(text, "%Y-%m-%d %H:%M:%S")


sqlite3.register_adapter(datetime, _adapt_datetime)
sqlite3.register_converter("TIMESTAMP", _convert_timestamp)


class SqliteDB:
    def __init__(
        self,
        host: str,
        port: int,
        database: str,
        user: str,
        password: str
    ):
        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password
        self.connection = None
        self._connect()
        self._create_tables()

    def _connect(self):
        if self.connection is not None:
            try:
                self.connection.close()
            except Exception:
                pass

        # host/port/user/password сохранены для совместимости API;
        # database — путь к файлу SQLite (или ":memory:").
        self.connection = sqlite3.connect(
            self.database,
            detect_types=sqlite3.PARSE_DECLTYPES,
            check_same_thread=False,
        )
        self.connection.row_factory = None
        self.connection.execute("PRAGMA foreign_keys = ON")

    def check_connection(self):
        try:
            if self.connection is None:
                self._connect()
                return

            with closing(self.connection.cursor()) as cursor:
                cursor.execute("SELECT 1")

        except (sqlite3.ProgrammingError, sqlite3.OperationalError):
            self._connect()

    def _create_tables(self) -> None:
        """
        Создаёт таблицы и индексы, если они ещё не существуют.
        """
        try:
            with closing(self.connection.cursor()) as cursor:

                # =========================================================
                # games
                # =========================================================
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS games (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        base_id INTEGER NOT NULL,
                        name TEXT,
                        place TEXT,
                        date_start TIMESTAMP,
                        date_end TIMESTAMP,
                        who_added INTEGER,
                        poll INTEGER,
                        poll_id TEXT,
                        team_notified INTEGER DEFAULT 0,
                        is_festival INTEGER NOT NULL DEFAULT 0,
                        difficulty_level REAL
                    );
                """)

                cursor.execute("PRAGMA table_info(games)")
                games_columns = {row[1] for row in cursor.fetchall()}
                if "difficulty_level" not in games_columns:
                    cursor.execute("""
                        ALTER TABLE games
                        ADD COLUMN difficulty_level REAL;
                    """)

                cursor.execute("""
                    CREATE UNIQUE INDEX IF NOT EXISTS
                    idx_games_base_id
                    ON games (base_id);
                """)

                cursor.execute("""
                    CREATE UNIQUE INDEX IF NOT EXISTS
                    idx_games_poll_id
                    ON games (poll_id);
                """)

                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS
                    idx_games_date_start
                    ON games (date_start);
                """)

                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS
                    idx_games_date_start_non_festival
                    ON games (date_start)
                    WHERE is_festival IS NOT TRUE;
                """)

                # =========================================================
                # players
                # =========================================================
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS players (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        base_id INTEGER,
                        tg_id INTEGER,
                        name TEXT,
                        surname TEXT,
                        patronymic TEXT,
                        rating REAL NOT NULL DEFAULT 0,
                        is_base INTEGER NOT NULL DEFAULT 0,
                        is_admin INTEGER NOT NULL DEFAULT 0,
                        tg_username TEXT,
                        enable_notifications INTEGER DEFAULT 1
                    );
                """)

                cursor.execute("""
                    CREATE UNIQUE INDEX IF NOT EXISTS
                    idx_players_tg_id
                    ON players (tg_id);
                """)

                cursor.execute("""
                    CREATE UNIQUE INDEX IF NOT EXISTS
                    idx_players_base_id
                    ON players (base_id);
                """)

                # =========================================================
                # ready_to_play
                # =========================================================
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS ready_to_play (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        game INTEGER NOT NULL,
                        player INTEGER NOT NULL,
                        ready INTEGER NOT NULL
                    );
                """)

                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS
                    idx_ready_to_play_game
                    ON ready_to_play (game);
                """)

                cursor.execute("""
                    CREATE UNIQUE INDEX IF NOT EXISTS
                    idx_ready_to_play_player_game
                    ON ready_to_play (player, game);
                """)

            self.connection.commit()

        except Error:
            self.connection.rollback()
            raise

    def set_team_notified(self, game_base_id: int, value: bool) -> bool:
        try:
            self.check_connection()
            with closing(self.connection.cursor()) as cursor:
                cursor.execute("""
                    UPDATE games
                    SET team_notified = ?
                    WHERE base_id = ?
                """, (int(value), game_base_id))

                updated = cursor.rowcount > 0

            self.connection.commit()
            return updated

        except Error:
            self.connection.rollback()
            return False

    # =====================================================================
    # GAMES
    # =====================================================================

    def add_game(
        self,
        base_id: int,
        name: str,
        who_added: int,
        place: str,
        date_start: datetime,
        difficulty_level: Optional[float] = None,
    ) -> bool:
        try:
            self.check_connection()
            with closing(self.connection.cursor()) as cursor:
                cursor.execute("""
                    INSERT INTO games (
                        base_id,
                        name,
                        who_added,
                        place,
                        date_start,
                        is_festival,
                        difficulty_level
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    base_id,
                    name,
                    who_added,
                    place,
                    date_start,
                    0,
                    difficulty_level,
                ))

            self.connection.commit()
            return True

        except Error:
            self.connection.rollback()
            return False

    def add_festival(
        self,
        base_id: int,
        name: str,
        who_added: int,
        place: str,
        date_start: datetime,
        date_end: datetime,
        difficulty_level: Optional[float] = None,
    ) -> bool:
        try:
            self.check_connection()
            with closing(self.connection.cursor()) as cursor:
                cursor.execute("""
                    INSERT INTO games (
                        base_id,
                        name,
                        who_added,
                        place,
                        date_start,
                        date_end,
                        is_festival,
                        difficulty_level
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    base_id,
                    name,
                    who_added,
                    place,
                    date_start,
                    date_end,
                    1,
                    difficulty_level,
                ))

            self.connection.commit()
            return True

        except Error:
            self.connection.rollback()
            return False

    def add_place_for_game(self, id: int, place: str) -> bool:
        """
        Устанавливает место проведения игры.
        """
        try:
            self.check_connection()
            with closing(self.connection.cursor()) as cursor:
                cursor.execute("""
                    UPDATE games
                    SET place = ?
                    WHERE base_id = ?
                """, (place, id))

                updated = cursor.rowcount > 0

            self.connection.commit()
            return updated

        except Error:
            self.connection.rollback()
            return False

    def add_dates_for_game(
        self,
        id: int,
        date_start: datetime,
        date_end: Optional[datetime] = None
    ) -> bool:
        """
        Устанавливает дату и время проведения игры.
        """
        try:
            self.check_connection()
            with closing(self.connection.cursor()) as cursor:
                if date_end:
                    cursor.execute("""
                        UPDATE games
                        SET "date_start" = ?, date_end = ?
                        WHERE base_id = ?
                    """, (date_start, date_end, id))
                else:
                    cursor.execute("""
                        UPDATE games
                        SET "date_start" = ?
                        WHERE base_id = ?
                    """, (date_start, id))

                updated = cursor.rowcount > 0

            self.connection.commit()
            return updated

        except Error:
            self.connection.rollback()
            return False

    def delete_game(self, base_id: int) -> bool:
        """
        Удаляет игру и ответы о готовности к ней.
        """
        try:
            self.check_connection()
            with closing(self.connection.cursor()) as cursor:
                cursor.execute("""
                    DELETE FROM ready_to_play
                    WHERE game = ?
                """, (base_id,))
                cursor.execute("""
                    DELETE FROM games
                    WHERE base_id = ?
                """, (base_id,))
                deleted = cursor.rowcount > 0

            self.connection.commit()
            return deleted

        except Error:
            self.connection.rollback()
            return False

    def get_my_tournaments(self, tg_id: int):
        """
        Возвращает первые 10 будущих турниров,
        где пользователь ready=True.
        """

        query = """
            SELECT
                g.id,
                g.base_id,
                g.name,
                g.place,
                g."date_start",
                g."date_end",
                g.is_festival
            FROM ready_to_play r
            JOIN games g
                ON g.base_id = r.game
            WHERE r.player = ?
              AND r.ready = 1
              AND g."date_start" >= CURRENT_DATE
            ORDER BY g."date_start"
            LIMIT 10
        """

        return self.fetch_all(query, (tg_id,))

    # =====================================================================
    # PLAYERS
    # =====================================================================

    def add_player_by_tg_id(self, tg_id: int, tg_username: str) -> bool:
        """
        Добавляет игрока, указывая только Telegram ID.
        """
        try:
            self.check_connection()
            with closing(self.connection.cursor()) as cursor:
                cursor.execute("""
                    SELECT tg_username
                    FROM players
                    WHERE tg_id = ?
                """, (tg_id, ))

                result = cursor.fetchone()
                if result:
                    # уже добален
                    if result[0] != tg_username:
                        cursor.execute("""
                            UPDATE players
                            SET tg_username = ?
                            WHERE tg_id = ?
                        """, (tg_username, tg_id, ))

                        self.connection.commit()
                    return True

                cursor.execute("""
                    INSERT INTO players (tg_id, tg_username)
                    VALUES (?, ?)
                """, (tg_id, tg_username,))

            self.connection.commit()
            return True

        except Error:
            self.connection.rollback()
            return False

    def get_base_id(self, tg_id: int) -> Optional[int]:
        """
        Возвращает base_id игрока по tg_id.

        Если игрок не найден — None.
        """
        try:
            self.check_connection()
            with closing(self.connection.cursor()) as cursor:
                cursor.execute("""
                    SELECT base_id
                    FROM players
                    WHERE tg_id = ?
                """, (tg_id,))

                result = cursor.fetchone()

            if result is None:
                return None

            return result[0]

        except Error:
            self.connection.rollback()
            return None

    def is_admin(self, tg_id: int) -> bool:
        """
        Возвращает значение is_admin по tg_id.

        Если игрок не найден — False.
        """
        try:
            self.check_connection()
            with closing(self.connection.cursor()) as cursor:
                cursor.execute("""
                    SELECT is_admin
                    FROM players
                    WHERE tg_id = ?
                """, (tg_id,))

                result = cursor.fetchone()

            if result is None:
                return False

            return bool(result[0])

        except Error:
            self.connection.rollback()
            return False

    def set_rating(self, tg_id: int, value: float) -> bool:
        """
        Изменяет рейтинг игрока по base_id.
        """
        try:
            self.check_connection()
            with closing(self.connection.cursor()) as cursor:
                cursor.execute("""
                    UPDATE players
                    SET rating = ?
                    WHERE tg_id = ?
                """, (value, tg_id))

                updated = cursor.rowcount > 0

            self.connection.commit()
            return updated

        except Error:
            self.connection.rollback()
            return False

    # =====================================================================
    # READY TO PLAY
    # =====================================================================

    def set_ready_to_play(
        self,
        game: int,
        player: int,
        value: bool
    ) -> bool:
        """
        Устанавливает готовность игрока к игре.

        Если запись существует:
            изменяет ready.

        Если записи нет и value=True:
            создаёт запись.

        Если записи нет и value=False:
            ничего не делает.
        """
        try:
            self.check_connection()
            with closing(self.connection.cursor()) as cursor:
                cursor.execute("""
                    SELECT id
                    FROM ready_to_play
                    WHERE game = ? AND player = ?
                """, (game, player))

                result = cursor.fetchone()

                if result is not None:
                    cursor.execute("""
                        UPDATE ready_to_play
                        SET ready = ?
                        WHERE game = ? AND player = ?
                    """, (int(value), game, player))

                    self.connection.commit()
                    return True

                if value:
                    cursor.execute("""
                        INSERT INTO ready_to_play (
                            game,
                            player,
                            ready
                        )
                        VALUES (?, ?, ?)
                    """, (game, player, int(value)))

                    self.connection.commit()
                    return True

                self.connection.commit()
                return True

        except Error:
            self.connection.rollback()
            return False

    def fetch_all(self, query: str, params=None):
        try:
            self.check_connection()
            with closing(self.connection.cursor()) as cursor:
                cursor.execute(query, params)
                result = cursor.fetchall()

            self.connection.commit()
            return result

        except Error:
            self.connection.rollback()
            raise

    def is_player_in_db(self, tg_id: int) -> bool:
        try:
            self.check_connection()
            with closing(self.connection.cursor()) as cursor:
                cursor.execute("""
                    SELECT tg_id
                    FROM players
                    WHERE tg_id = ?
                """, (tg_id,))

                result = cursor.fetchone()
            return result is not None

        except Error:
            self.connection.rollback()
            return False

    def get_future_games(self, limit: int = 10, has_poll: bool=None):
        """
        has_poll:
            None  - все игры;
            True  - poll и poll_id заполнены;
            False - хотя бы одно из poll/poll_id не заполнено.
        """
        try:
            poll = ''
            if has_poll is False:
                poll = ' and (poll_id is NULL or poll is NULL)'
            elif has_poll is True:
                poll = ' and not (poll_id is NULL or poll is NULL)'
            self.check_connection()
            with closing(self.connection.cursor()) as cursor:
                cursor.execute("""
                    SELECT
                        base_id,
                        name,
                        place,
                        "date_start"
                    FROM games
                    WHERE COALESCE("date_end", "date_start") >= CURRENT_DATE""" + poll + """
                    ORDER BY "date_start"
                    LIMIT ?
                """, (limit,))

                result = cursor.fetchall()

            self.connection.commit()
            return result

        except Error:
            self.connection.rollback()
            return []

    def get_recent_non_festival_places(self, limit: int = 15) -> list[str]:
        """
        Уникальные места из последних обычных (не фестиваль) игр,
        в порядке от более новых к более старым.
        """
        try:
            self.check_connection()
            with closing(self.connection.cursor()) as cursor:
                cursor.execute("""
                    SELECT place
                    FROM games
                    WHERE is_festival IS NOT TRUE
                      AND date_start IS NOT NULL
                    ORDER BY date_start DESC
                    LIMIT ?
                """, (limit,))
                rows = cursor.fetchall()

            self.connection.commit()
            places = []
            seen = set()
            for (place,) in rows:
                value = (place or "").strip()
                if not value or value in seen:
                    continue
                seen.add(value)
                places.append(value)
            return places

        except Error:
            self.connection.rollback()
            return []

    def get_all_game_base_ids(self) -> set:
        try:
            self.check_connection()
            with closing(self.connection.cursor()) as cursor:
                cursor.execute("""
                    SELECT base_id
                    FROM games
                """)
                result = cursor.fetchall()

            self.connection.commit()
            return {row[0] for row in result}

        except Error:
            self.connection.rollback()
            return set()

    def get_game(self, game_id: int):
        try:
            self.check_connection()
            with closing(self.connection.cursor()) as cursor:
                cursor.execute("""
                    SELECT
                        id,
                        base_id,
                        name,
                        place,
                        date_start,
                        date_end,
                        who_added,
                        poll,
                        poll_id,
                        is_festival,
                        difficulty_level
                    FROM games
                    WHERE base_id = ?
                """, (game_id,))

                result = cursor.fetchone()

            if result is None:
                return None

            return {
                "id": result[0],
                "base_id": result[1],
                "name": result[2],
                "place": result[3],
                "date_start": result[4],
                "date_end": result[5],
                "who_added": result[6],
                "poll": result[7],
                "poll_id": result[8],
                "is_festival": bool(result[9]),
                "difficulty_level": result[10],
            }

        except Error:
            self.connection.rollback()
            return None

    def set_game_poll(
        self,
        game_id: int,
        message_id: int,
        poll_id: str
    ) -> bool:
        try:
            self.check_connection()
            with closing(self.connection.cursor()) as cursor:
                cursor.execute("""
                    UPDATE games
                    SET
                        poll = ?,
                        poll_id = ?
                    WHERE base_id = ?
                """, (
                    message_id,
                    poll_id,
                    game_id
                ))

                updated = cursor.rowcount > 0

            self.connection.commit()
            return updated

        except Error:
            self.connection.rollback()
            return False

    def clear_game_poll(self, game_id: int) -> bool:
        try:
            self.check_connection()
            with closing(self.connection.cursor()) as cursor:
                cursor.execute("""
                    UPDATE games
                    SET
                        poll = NULL,
                        poll_id = NULL,
                        team_notified = 0
                    WHERE base_id = ?
                """, (game_id,))

                updated = cursor.rowcount > 0

            self.connection.commit()
            return updated

        except Error:
            self.connection.rollback()
            return False

    def get_game_by_poll_id(self, poll_id: str):
        try:
            self.check_connection()
            with closing(self.connection.cursor()) as cursor:


                cursor.execute("""
                        SELECT
                            id,
                            base_id,
                            name,
                            place,
                            "date_start",
                            who_added,
                            poll,
                            poll_id,
                            team_notified
                        FROM games
                        WHERE poll_id = ?
                    """, (poll_id,))

                result = cursor.fetchone()

                if result is None:
                    return None

                return {
                    "id": result[0],
                    "base_id": result[1],
                    "name": result[2],
                    "place": result[3],
                    "date_start": result[4],
                    "who_added": result[5],
                    "poll": result[6],
                    "poll_id": result[7],
                    'team_notified': bool(result[8])
                }

        except Error:
            self.connection.rollback()
            return None

    def get_unlinked_players(self, limit: int = 10):
        try:
            self.check_connection()
            with closing(self.connection.cursor()) as cursor:
                cursor.execute("""
                    SELECT
                        id,
                        tg_id,
                        name,
                        surname,
                        tg_username
                    FROM players
                    WHERE tg_id IS NOT NULL AND base_id IS NULL
                    LIMIT ?
                """, (limit,))

                result = cursor.fetchall()

            self.connection.commit()
            return result

        except Error:
            self.connection.rollback()
            return []

    def update_player_by_tg_id(
        self,
        player_id: int,
        base_id: int,
        name: str,
        surname: str,
        patronimyc: str
    ) -> bool:


        """
        Обновляет данные игрока по Telegram ID.
        """
        try:
            self.check_connection()
            with closing(self.connection.cursor()) as cursor:
                cursor.execute("""
                    UPDATE players
                    SET
                        base_id = ?,
                        name = ?,
                        surname = ?,
                        patronymic = ?
                    WHERE tg_id = ?
                """, (
                    base_id,
                    name,
                    surname,
                    patronimyc,
                    player_id
                ))

                updated = cursor.rowcount > 0

            self.connection.commit()
            return updated

        except Error:
            self.connection.rollback()
            return False

    def get_ready_players_for_game(
        self,
        base_id: int
    ):
        try:
            self.check_connection()
            with closing(self.connection.cursor()) as cursor:
                cursor.execute("""
                    SELECT
                        p.base_id,
                        p.surname,
                        p.name,
                        p.patronymic,
                        (case when p.is_base = 1 then 'Б' else 'Л' end) flag,
                        tg_username,
                        p.tg_id,
                        p.enable_notifications
                    FROM ready_to_play r
                    JOIN players p
                         ON p.tg_id = r.player
                    WHERE r.game = ?
                    AND r.ready = 1
                    ORDER BY p.is_base desc, p.base_id
                """, (base_id,))

                result = cursor.fetchall()

            self.connection.commit()
            return result

        except Error:
            self.connection.rollback()
            return []

    # Проверка числа играющих
    def get_ready_players_count(self, game_base_id: int) -> int:
        try:
            self.check_connection()
            with closing(self.connection.cursor()) as cursor:
                cursor.execute("""
                    SELECT COUNT(*)
                    FROM ready_to_play
                    WHERE game = ?
                    AND ready = 1
                """, (game_base_id,))

                result = cursor.fetchone()

            self.connection.commit()
            return result[0] if result else 0

        except Error:
            self.connection.rollback()
            return 0

    # =====================================================================
    # CONNECTION
    # =====================================================================

    def close(self) -> None:
        """
        Закрывает соединение с БД.
        """
        if self.connection is not None:
            self.connection.close()
            self.connection = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
