import logging
from datetime import datetime, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, ContextTypes

from const import (
    BTN_VIEW_ROSTER,
    GAME_REMIND_DAY_JOB_PREFIX,
    GAME_REMIND_HOUR_JOB_PREFIX,
    MSK_TZ,
    PLAYERS_CALLBACK,
)
from utils import get_when_text

logger = logging.getLogger(__name__)


class GameReminderHandlers:
    def _aware_msk(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=MSK_TZ)
        return value.astimezone(MSK_TZ)

    def _game_remind_job_name(self, kind: str, game_id: int) -> str:
        prefix = (
            GAME_REMIND_DAY_JOB_PREFIX
            if kind == "day"
            else GAME_REMIND_HOUR_JOB_PREFIX
        )
        return f"{prefix}{game_id}"

    def unschedule_game_reminders(self, job_queue, game_id: int) -> None:
        if job_queue is None:
            return
        for kind in ("day", "hour"):
            name = self._game_remind_job_name(kind, game_id)
            for job in job_queue.get_jobs_by_name(name):
                job.schedule_removal()

    def schedule_game_reminders(self, job_queue, game: dict) -> None:
        if job_queue is None or not game:
            return

        game_id = game.get("base_id")
        date_start = game.get("date_start")
        if game_id is None or date_start is None:
            return

        self.unschedule_game_reminders(job_queue, game_id)

        now = datetime.now(MSK_TZ)
        start = self._aware_msk(date_start)
        reminders = [("day", start - timedelta(days=1))]
        if not game.get("is_festival"):
            reminders.append(("hour", start - timedelta(hours=2)))
        for kind, when in reminders:
            if when <= now:
                continue
            job_queue.run_once(
                self.send_game_reminder,
                when=when,
                data={"game_id": game_id, "kind": kind},
                name=self._game_remind_job_name(kind, game_id),
            )

    def schedule_all_game_reminders(self, application: Application) -> None:
        job_queue = application.job_queue
        if job_queue is None:
            logger.error("JobQueue недоступен, напоминания об играх не запланированы")
            return
        for game in self.db.get_games_for_reminders():
            self.schedule_game_reminders(job_queue, game)

    def _game_reminder_text(self, game: dict) -> str:
        when_text = get_when_text(
            game.get("date_start"),
            game.get("date_end"),
            game.get("is_festival"),
        ) or "не указано"
        place = game.get("place") or "не указано"
        name = game.get("name") or str(game.get("base_id"))
        return "\n".join([
            name,
            f"Время: {when_text}",
            f"Место: {place}",
            "",
            f'Для того, чтобы посмотреть состав нажмите «{BTN_VIEW_ROSTER}».',
            "Для отключения уведомлений зайдите в настройки.",
        ])

    def _game_reminder_keyboard(self, game_id: int) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    BTN_VIEW_ROSTER,
                    callback_data=f"{PLAYERS_CALLBACK}:{game_id}",
                )
            ]
        ])

    async def send_game_reminder(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        job = context.job
        if job is None or not job.data:
            return

        game_id = job.data.get("game_id")
        game = self.db.get_game(game_id) if game_id is not None else None
        if game is None:
            return

        text = self._game_reminder_text(game)
        keyboard = self._game_reminder_keyboard(game["base_id"])
        await self.notify_ready_players(
            context,
            game["base_id"],
            text,
            reply_markup=keyboard,
        )
