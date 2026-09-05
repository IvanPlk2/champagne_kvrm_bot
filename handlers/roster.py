import logging

from telegram import Update
from telegram.ext import ContextTypes

from config import TEAM_CHAT_ID
from const import (
    ROSTER_BROKE_DELAY_SECONDS,
    ROSTER_BROKE_JOB_PREFIX,
    ROSTER_MIN_PLAYERS,
)

logger = logging.getLogger(__name__)


class RosterHandlers:
    async def poll_answer_handler(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ):
        answer = update.poll_answer

        if answer is None or answer.user is None:
            return

        tg_id = answer.user.id

        # Пустой option_ids — пользователь снял голос в опросе.
        option_ids = tuple(answer.option_ids or ())
        ready = 0 in option_ids

        game = self.db.get_game_by_poll_id(
            answer.poll_id
        )
        if game is None:
            logger.warning(
                "Получен ответ неизвестного опроса: %s",
                answer.poll_id
            )
            return

        game_id = game["base_id"]

        if not self.db.is_player_in_db(tg_id):

            self.db.add_player_by_tg_id(
                tg_id=answer.user.id,
                tg_username=answer.user.username
            )

            if not self.db.is_player_in_db(tg_id):
                logger.warning(
                    "Telegram user %s не найден в players, создать игрока не получилось",
                    tg_id
                )
                return

        self.db.set_ready_to_play(
            game=game_id,
            player=tg_id,
            value=ready,
        )

        ready_count = self.db.get_ready_players_count(game_id)

        if ready and not game["team_notified"] and ready_count >= ROSTER_MIN_PLAYERS:
            await context.bot.send_message(
                chat_id=TEAM_CHAT_ID,
                text=f"Собран состав на {game['name']}",
            )
            self.db.set_team_notified(game_id, True)
            return

        if (
            not ready
            and game["team_notified"]
            and ready_count < ROSTER_MIN_PLAYERS
        ):
            self._schedule_roster_broke_check(context, game_id)

    def _roster_broke_job_name(self, game_id: int) -> str:
        return f"{ROSTER_BROKE_JOB_PREFIX}{game_id}"

    def _schedule_roster_broke_check(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        game_id: int,
    ) -> None:
        job_queue = context.job_queue
        if job_queue is None:
            logger.error("JobQueue недоступен, проверка разбора состава не запланирована")
            return

        job_name = self._roster_broke_job_name(game_id)
        if job_queue.get_jobs_by_name(job_name):
            return

        job_queue.run_once(
            self.check_roster_broke,
            when=ROSTER_BROKE_DELAY_SECONDS,
            data=game_id,
            name=job_name,
        )

    async def check_roster_broke(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        job = context.job

        if job is None or job.data is None:
            return

        game_id = job.data
        game = self.db.get_game(game_id)

        if game is None or not game.get("team_notified"):
            return

        ready_count = self.db.get_ready_players_count(game_id)
        if ready_count >= ROSTER_MIN_PLAYERS:
            return

        await context.bot.send_message(
            chat_id=TEAM_CHAT_ID,
            text=f"Разобрался состав на {game['name']}",
        )
        self.db.set_team_notified(game_id, False)
