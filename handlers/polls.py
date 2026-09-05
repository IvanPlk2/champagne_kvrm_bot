import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from config import ANOTHER_CHAT_ID, TEAM_CHAT_ID
from const import POLL_CALLBACK, SHOW_POLL_CALLBACK
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
        # -------------------------------------------------------------
        # Создаём новый опрос
        # -------------------------------------------------------------

        try:

            when_text = get_when_text(
                game['date_start'],
                game['date_end'],
                game['is_festival'],
            )
            question_parts = [game["name"]]
            difficulty_level = game.get("difficulty_level")
            if difficulty_level is not None:
                question_parts.append(f"DL {difficulty_level}")
            if game.get("place"):
                question_parts.append(game["place"])
            if when_text:
                question_parts.append(when_text)
            question = '. '.join(question_parts)

            message = await context.bot.send_poll(
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

            await query.message.reply_text(
                "Не удалось создать опрос."
            )
            await self.reset_keyboard_and_state(update, context)
            return

        await query.message.reply_text(
            "Опрос создан."
        )

        self.db.set_game_poll(
            game_id=game_id,
            message_id=message.message_id,
            poll_id=message.poll.id,
        )

        try:
            await context.bot.pin_chat_message(
                chat_id=TEAM_CHAT_ID,
                message_id=message.message_id,
                disable_notification=True,
            )
        except Exception:
            logger.exception(
                "Не удалось закрепить опрос для игры %s",
                game_id,
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
