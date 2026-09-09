import logging
from datetime import datetime, timedelta
from typing import Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, ContextTypes

from config import ANOTHER_CHAT_ID, TEAM_CHAT_ID
from const import (
    MSK_TZ,
    POLL_CALLBACK,
    POLL_UNPIN_HOUR,
    POLL_UNPIN_JOB_PREFIX,
    SHOW_POLL_CALLBACK,
)
from utils import get_when_text

logger = logging.getLogger(__name__)


class PollHandlers:
    async def show_games_for_poll(
        self,
        update: Update
    ):
        games = self.db.get_future_games(10, False)

        if not games:
            await update.message.reply_text(
                "Игр без опроса нет."
            )
            return

        keyboard = []

        for game in games:
            game_id, name, place, date_start = game

            keyboard.append([
                InlineKeyboardButton(
                    text=name or str(game_id),
                    callback_data=f"{POLL_CALLBACK}:{game_id}",
                )
            ])

        await update.message.reply_text(
            "Выберите игру:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    async def show_games_with_polls(self, update):
        tg_id = update.effective_user.id
        games = self.db.get_visible_poll_games(tg_id, limit=10)

        if not games:
            await update.message.reply_text(
                "Будущих игр с опросами нет."
            )
            return

        keyboard = []

        for base_id, name, place, date_start in games:
            keyboard.append([
                InlineKeyboardButton(
                    name or str(base_id),
                    callback_data=f"{SHOW_POLL_CALLBACK}:{base_id}",
                )
            ])

        await update.message.reply_text(
            "Выберите игру:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    async def create_or_forward_poll(
        self,
        query,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        game_id: int
    ):
        game = self.db.get_game(game_id)

        if game is None:
            await query.message.reply_text(
                "Игра не найдена."
            )
            return

        # -------------------------------------------------------------
        # Опрос уже существует
        # -------------------------------------------------------------
        if game["poll"] is not None and game["poll_id"] is not None:
            await query.message.reply_text(
                "Опрос для этой игры уже создан."
            )
            return

        created = await self.send_game_poll(
            context.bot, game, context.job_queue
        )
        if not created:
            await query.message.reply_text(
                "Не удалось создать опрос."
            )
            await self.reset_keyboard_and_state(update, context)
            return

        await query.message.reply_text("Опрос создан.")

    async def send_game_poll(self, bot, game: dict, job_queue=None) -> bool:
        if not game:
            return False
        if game.get("poll") is not None and game.get("poll_id") is not None:
            return False

        game_id = game["base_id"]
        try:
            when_text = get_when_text(
                game["date_start"],
                game["date_end"],
                game["is_festival"],
            )
            question_parts = [game["name"]]
            difficulty_level = game.get("difficulty_level")
            if difficulty_level is not None:
                question_parts.append(f"DL {difficulty_level}")
            if game.get("place"):
                question_parts.append(game["place"])
            if when_text:
                question_parts.append(when_text)
            question = ". ".join(question_parts)

            message = await bot.send_poll(
                chat_id=TEAM_CHAT_ID,
                question=question,
                options=[
                    "Да",
                    "Нет",
                    "Окститесь",
                    "Я - томат",
                ],
                is_anonymous=False,
                allows_multiple_answers=True,
                allows_revoting=True,
            )
        except Exception:
            logger.exception(
                "Не удалось создать опрос для игры %s",
                game_id,
            )
            return False

        self.db.set_game_poll(
            game_id=game_id,
            message_id=message.message_id,
            poll_id=message.poll.id,
        )
        game = {**game, "poll": message.message_id, "poll_id": message.poll.id}

        try:
            await bot.pin_chat_message(
                chat_id=TEAM_CHAT_ID,
                message_id=message.message_id,
                disable_notification=True,
            )
        except Exception:
            logger.exception(
                "Не удалось закрепить опрос для игры %s",
                game_id,
            )

        self.schedule_poll_unpin(job_queue, game)
        return True

    def _aware_msk(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=MSK_TZ)
        return value.astimezone(MSK_TZ)

    def _poll_unpin_at(self, game: dict) -> Optional[datetime]:
        if game.get("is_festival"):
            when = game.get("date_end") or game.get("date_start")
        else:
            when = game.get("date_start") or game.get("date_end")
        if when is None:
            return None
        next_day = self._aware_msk(when).date() + timedelta(days=1)
        return datetime(
            next_day.year,
            next_day.month,
            next_day.day,
            POLL_UNPIN_HOUR,
            tzinfo=MSK_TZ,
        )

    def _poll_unpin_job_name(self, game_id: int) -> str:
        return f"{POLL_UNPIN_JOB_PREFIX}{game_id}"

    def unschedule_poll_unpin(self, job_queue, game_id: int) -> None:
        if job_queue is None:
            return
        name = self._poll_unpin_job_name(game_id)
        for job in job_queue.get_jobs_by_name(name):
            job.schedule_removal()

    def schedule_poll_unpin(self, job_queue, game: dict) -> None:
        if not game:
            return
        game_id = game.get("base_id")
        if game_id is None or game.get("poll") is None:
            return

        self.unschedule_poll_unpin(job_queue, game_id)
        if job_queue is None:
            logger.error("JobQueue недоступен, открепление опроса не запланировано")
            return

        when = self._poll_unpin_at(game)
        if when is None:
            return

        now = datetime.now(MSK_TZ)
        job_queue.run_once(
            self.unpin_game_poll_job,
            when=0 if when <= now else when,
            data=game_id,
            name=self._poll_unpin_job_name(game_id),
        )

    def schedule_all_poll_unpins(self, application: Application) -> None:
        job_queue = application.job_queue
        if job_queue is None:
            logger.error("JobQueue недоступен, открепление опросов не запланировано")
            return
        for game in self.db.get_games_with_polls():
            self.schedule_poll_unpin(job_queue, game)

    async def unpin_game_poll_job(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        job = context.job
        if job is None or job.data is None:
            return
        game = self.db.get_game(job.data)
        if game is None:
            return
        await self.unpin_game_poll(context.bot, game)

    async def unpin_game_poll(self, bot, game: dict) -> None:
        message_id = game.get("poll")
        if message_id is None:
            return
        for chat_id in (TEAM_CHAT_ID, ANOTHER_CHAT_ID):
            try:
                await bot.unpin_chat_message(
                    chat_id=chat_id,
                    message_id=message_id,
                )
                return
            except Exception:
                logger.debug(
                    "Не удалось открепить опрос игры %s в чате %s",
                    game.get("base_id"),
                    chat_id,
                    exc_info=True,
                )

    # ===========================================================
    # Показать опрос
    # ===========================================================

    async def show_poll(self, query, bot, base_id: int):

        game = self.db.get_game(base_id)

        if game is None:
            await query.message.reply_text(
                "Игра не найдена."
            )
            return

        if game["poll"] is None:
            await query.message.reply_text(
                "У этой игры нет опроса."
            )
            return

        try:
            await bot.forward_message(
                chat_id=query.message.chat_id,
                from_chat_id=TEAM_CHAT_ID,
                message_id=game["poll"],
            )

        except Exception:

            # Если не смогли пробуем другой ИД чата

            try:
                await bot.forward_message(
                    chat_id=query.message.chat_id,
                    from_chat_id=ANOTHER_CHAT_ID,
                    message_id=game["poll"],
                )

            except Exception:

                logger.exception(
                    "Не удалось переслать опрос для игры %s",
                    base_id,
                )

                await query.message.reply_text(
                    "Не удалось переслать опрос."
                )
