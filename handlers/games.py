import logging
from datetime import datetime, timedelta
from typing import Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import ContextTypes

from config import ANOTHER_CHAT_ID, TEAM_CHAT_ID
from const import (
    BTN_ADD_GAME_BY_ID,
    BTN_BACK,
    BTN_FIND_OTHER_GAME,
    BTN_NO,
    BTN_YES,
    EDIT_DATE_CALLBACK,
    EDIT_DELETE_CALLBACK,
    EDIT_GAME_CALLBACK,
    EDIT_PLACE_CALLBACK,
    MSK_TZ,
    STATE_ADD_GAME_CONFIRM,
    STATE_ADD_GAME_DATE_START,
    STATE_ADD_GAME_ID,
    STATE_ADD_GAME_PLACE,
    STATE_ADD_GAME_SEARCH_NAME,
    STATE_ADD_GAME_SELECT,
    STATE_EDIT_DATE,
    STATE_EDIT_DELETE_CONFIRM,
    STATE_NONE,
    STATE_UPDATE_PLACE,
)
from utils import (
    add_months,
    format_msk_window,
    get_when_text,
    is_datetime_in_rating_window,
    to_msk_naive,
)

logger = logging.getLogger(__name__)


class GameHandlers:
    def _tournament_button_label(self, tournament: dict, used: set[str]) -> str:
        name = tournament.get("name") or str(tournament.get("id") or "")
        label = name[:64]
        if label in used:
            suffix = f" [{tournament.get('id')}]"
            label = (name[: max(0, 64 - len(suffix))] + suffix)[:64]
        return label or str(tournament.get("id"))

    def _build_add_game_choices(
        self,
        tournaments: list[dict],
        *,
        exclude_existing: bool,
    ) -> tuple[list[str], dict]:
        available = [
            tournament
            for tournament in tournaments
            if tournament.get("id") is not None
        ]
        if exclude_existing:
            existing_ids = self.db.get_all_game_base_ids()
            available = [
                tournament
                for tournament in available
                if tournament["id"] not in existing_ids
            ]
        available = available[:9]

        used_labels: set[str] = set()
        labels = []
        choices = {}
        for tournament in available:
            label = self._tournament_button_label(tournament, used_labels)
            used_labels.add(label)
            labels.append(label)
            choices[label] = tournament["id"]
        return labels, choices

    async def _show_add_game_choices(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        labels: list[str],
        choices: dict,
        prompt: str,
        extra_button: str,
    ):
        context.user_data["add_game_choices"] = choices
        context.user_data["add_game_extra_button"] = extra_button
        context.user_data["state"] = STATE_ADD_GAME_SELECT
        await update.message.reply_text(
            prompt,
            reply_markup=self.add_game_select_keyboard(labels, extra_button),
        )

    async def start_add_game(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        is_festival: bool
    ):
        context.user_data["is_festival"] = is_festival

        if is_festival:
            context.user_data["state"] = STATE_ADD_GAME_ID
            await update.message.reply_text("Введите id:")
            return

        await self.show_add_game_menu(update, context)

    async def ask_add_game_id(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        reply_markup=None,
    ):
        context.user_data["state"] = STATE_ADD_GAME_ID
        kwargs = {}
        if reply_markup is not None:
            kwargs["reply_markup"] = reply_markup
        await update.message.reply_text("Введите id:", **kwargs)

    async def show_add_game_menu(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ):
        today = datetime.now(MSK_TZ).date()
        date_end_to = today + timedelta(weeks=2)

        try:
            tournaments = await self.rating_api.list_synchrons(
                date_end_from=today,
                date_end_to=date_end_to,
            )
        except Exception as exc:
            logger.exception(exc)
            await update.message.reply_text(
                "Не удалось получить список турниров."
            )
            await self.ask_add_game_id(update, context)
            return

        labels, choices = self._build_add_game_choices(
            tournaments,
            exclude_existing=True,
        )

        if labels:
            prompt = "Выберите турнир:"
        else:
            prompt = (
                "Ближайших синхронов, которых ещё нет в списке, нет.\n"
                "Можно найти другой турнир."
            )

        await self._show_add_game_choices(
            update,
            context,
            labels,
            choices,
            prompt,
            BTN_FIND_OTHER_GAME,
        )

    async def ask_add_game_search_name(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ):
        context.user_data["state"] = STATE_ADD_GAME_SEARCH_NAME
        await update.message.reply_text(
            "Введите часть названия турнира:",
            reply_markup=ReplyKeyboardRemove(),
        )

    async def handle_add_game_select(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ):
        text = update.message.text
        extra_button = context.user_data.get(
            "add_game_extra_button",
            BTN_FIND_OTHER_GAME,
        )

        if text == BTN_FIND_OTHER_GAME:
            await self.ask_add_game_search_name(update, context)
            return

        if text == BTN_ADD_GAME_BY_ID:
            await self.ask_add_game_id(
                update,
                context,
                reply_markup=ReplyKeyboardRemove(),
            )
            return

        if text == BTN_BACK:
            await self.reset_keyboard_and_state(update, context)
            return

        choices = context.user_data.get("add_game_choices") or {}
        game_id = choices.get(text)

        if game_id is None:
            await update.message.reply_text(
                "Выберите турнир с клавиатуры.",
                reply_markup=self.add_game_select_keyboard(
                    list(choices),
                    extra_button,
                ),
            )
            return

        await self.confirm_add_game_by_id(update, context, game_id)

    async def handle_add_game_search_name(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ):
        text = update.message.text.strip()

        if text == BTN_BACK:
            await self.reset_keyboard_and_state(update, context)
            return

        if not text:
            await update.message.reply_text(
                "Введите название турнира:"
            )
            return

        today = datetime.now(MSK_TZ).date()
        date_end_to = add_months(today, 1)

        try:
            tournaments = await self.rating_api.list_synchrons(
                date_end_from=today,
                date_end_to=date_end_to,
                name=text,
                items_per_page=100,
            )
            if not tournaments:
                tournaments = await self.rating_api.match_by_long_name(
                    today,
                    date_end_to,
                    text
                )
        except Exception as exc:
            logger.exception(exc)
            await update.message.reply_text(
                "Не удалось найти турниры."
            )
            await self._show_add_game_choices(
                update,
                context,
                [],
                {},
                "Можно ввести турнир через ID сайта рейтинга.",
                BTN_ADD_GAME_BY_ID,
            )
            return

        labels, choices = self._build_add_game_choices(
            tournaments,
            exclude_existing=True,
        )

        if not labels:
            await update.message.reply_text("Турниров не найдено.")
            await self.ask_add_game_id(
                update,
                context,
                reply_markup=ReplyKeyboardRemove(),
            )
            return

        await self._show_add_game_choices(
            update,
            context,
            labels,
            choices,
            "Выберите турнир:",
            BTN_ADD_GAME_BY_ID,
        )

    async def handle_add_game_id(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ):
        try:
            game_id = int(update.message.text)
        except ValueError:
            await update.message.reply_text(
                "ID должен быть числом. Введите id:"
            )
            return

        await self.confirm_add_game_by_id(update, context, game_id)

    async def confirm_add_game_by_id(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        game_id: int,
    ):
        try:
            rating_data = await self.rating_api.get_tournament(game_id)
        except Exception as exc:
            logger.exception(exc)

            await update.message.reply_text(
                "Не удалось получить информацию о турнире."
            )
            await self.reset_keyboard_and_state(update, context)
            return

        if context.user_data["is_festival"] and not rating_data.get('is_festival'):

            await update.message.reply_text(
                "Это обычная игра. Используйте кнопку \"Добавить игру\""
            )
            await self.reset_keyboard_and_state(update, context)
            return

        if not context.user_data["is_festival"] and rating_data.get('is_festival'):
            await update.message.reply_text(
                "Это фестиваль. Используйте кнопку \"Добавить фестиваль\""
            )
            await self.reset_keyboard_and_state(update, context)
            return

        if context.user_data["is_festival"] and not rating_data.get("date_start"):
            await update.message.reply_text(
                "На сайте рейтинга нет дат проведения. "
                "Фестиваль нельзя добавить."
            )
            await self.reset_keyboard_and_state(update, context)
            return

        context.user_data["new_game"] = {
            "base_id": rating_data["id"],
            "name": rating_data["name"],
            "difficulty_level": rating_data.get("difficulty_level"),
            "date_start": rating_data.get("date_start"),
            "date_end": rating_data.get("date_end"),
        }
        context.user_data["state"] = STATE_ADD_GAME_CONFIRM

        confirm_text = f"Добавить {rating_data.get('name')}?"
        rating_start = rating_data.get("date_start")
        rating_end = rating_data.get("date_end")
        if rating_start or rating_end:
            if context.user_data["is_festival"]:
                when_text = get_when_text(
                    to_msk_naive(rating_start),
                    to_msk_naive(rating_end),
                    True,
                )
            else:
                when_text = format_msk_window(rating_start, rating_end)
            if when_text:
                confirm_text += f"\nСроки: {when_text}"

        await update.message.reply_text(
            confirm_text,
            reply_markup=self.yes_no_keyboard(),
        )

    async def handle_add_game_confirm(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ):
        text = update.message.text

        if text == BTN_NO:
            await self.reset_keyboard_and_state(update, context)
            return

        if text != BTN_YES:
            await update.message.reply_text(
                "Выберите Да или Нет.",
                reply_markup=self.yes_no_keyboard(),
            )
            return

        data = context.user_data.get("new_game")

        if not data:
            await self.reset_keyboard_and_state(update, context)
            return

        if self.db.get_game(data["base_id"]):
            await update.message.reply_text(
                "Игра уже добавлена."
            )
            await self.reset_keyboard_and_state(update, context)
            return

        context.user_data["new_game_base_id"] = data["base_id"]
        context.user_data["new_game_name"] = data.get("name")
        context.user_data["new_game_difficulty_level"] = data.get("difficulty_level")
        context.user_data["new_game_date_start"] = data.get("date_start")
        context.user_data["new_game_date_end"] = data.get("date_end")
        context.user_data["state"] = STATE_ADD_GAME_PLACE

        await self.ask_place(update.message, "Введите место:")

    async def handle_add_game_place(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ):
        if update.message.text == BTN_BACK:
            await self.reset_keyboard_and_state(update, context)
            return

        game_id = context.user_data.get("new_game_base_id")

        if game_id is None:
            await self.reset_keyboard_and_state(update, context)
            return

        context.user_data["new_game_place"] = update.message.text

        if context.user_data["is_festival"]:
            await self.save_festival_from_rating(update, context)
            return

        context.user_data["state"] = STATE_ADD_GAME_DATE_START

        prompt = "Введите дату в формате ДД.ММ.ГГ ЧЧ:ММ"
        window = format_msk_window(
            context.user_data.get("new_game_date_start"),
            context.user_data.get("new_game_date_end"),
        )
        if window:
            prompt += f"\nСрок проведения (GMT+3): {window}"
        await update.message.reply_text(
            prompt,
            reply_markup=ReplyKeyboardRemove(),
        )

    async def handle_add_game_date_start(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ):
        game_id = context.user_data.get("new_game_base_id")

        tg_id = update.effective_user.id

        if tg_id is None:
            await update.message.reply_text(
                "Пользователь не найден в базе."
            )
            context.user_data["state"] = STATE_NONE
            return

        if not context.user_data["is_festival"]:

            try:
                game_when = datetime.strptime(
                    update.message.text,
                    "%d.%m.%y %H:%M"
                )
            except ValueError:
                await update.message.reply_text(
                    "Неверный формат даты.\n"
                    "Используйте ДД.ММ.ГГ ЧЧ:ММ"
                )
                return

            rating_start = context.user_data.get("new_game_date_start")
            rating_end = context.user_data.get("new_game_date_end")
            if not is_datetime_in_rating_window(
                game_when,
                rating_start,
                rating_end,
            ):
                window = format_msk_window(rating_start, rating_end) or "не указан"
                await update.message.reply_text(
                    "Введённая дата не входит в сроки проведения турнира "
                    f"({window}, GMT+3).\n"
                    "Исправьте дату."
                )
                return

            if not self.db.add_game(
                game_id,
                context.user_data.get("new_game_name"),
                tg_id,
                context.user_data.get("new_game_place"),
                game_when,
                context.user_data.get("new_game_difficulty_level"),
            ):
                await update.message.reply_text(
                    "Не удалось добавить игру."
                )
                return

            await update.message.reply_text(
                "Игра добавлена."
            )

            await self.reset_keyboard_and_state(update, context)
            return

        await self.save_festival_from_rating(update, context)

    async def handle_add_game_date_end(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ):
        await self.save_festival_from_rating(update, context)

    async def save_festival_from_rating(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ):
        game_id = context.user_data.get("new_game_base_id")
        tg_id = update.effective_user.id
        date_start = to_msk_naive(context.user_data.get("new_game_date_start"))
        date_end = to_msk_naive(context.user_data.get("new_game_date_end"))

        if date_start is None:
            await update.message.reply_text(
                "На сайте рейтинга нет дат проведения. "
                "Фестиваль нельзя добавить."
            )
            await self.reset_keyboard_and_state(update, context)
            return

        if date_end is None:
            date_end = date_start

        await self.finish_add_festival(
            update,
            context,
            game_id,
            tg_id,
            date_start,
            date_end,
        )

    async def finish_add_festival(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        game_id,
        tg_id,
        date_start,
        date_end,
    ):
        if not self.db.add_festival(
            game_id,
            context.user_data.get("new_game_name"),
            tg_id,
            context.user_data.get("new_game_place"),
            date_start,
            date_end,
            context.user_data.get("new_game_difficulty_level"),
        ):
            await update.message.reply_text(
                "Не удалось добавить фестиваль."
            )
        else:
            await update.message.reply_text(
                "Фестиваль добавлен."
            )

        await self.reset_keyboard_and_state(update, context)

    # =================================================================
    # РЕДАКТИРОВАНИЕ ИГРЫ
    # =================================================================

    def _game_summary(self, game: dict) -> str:
        when_text = get_when_text(
            game["date_start"],
            game["date_end"],
            game["is_festival"],
        )
        kind = "фестиваль" if game["is_festival"] else "игра"
        return "\n".join([
            game["name"] or str(game["base_id"]),
            f"Тип: {kind}",
            f"Место: {game['place'] or 'не указано'}",
            f"Когда: {when_text or 'не указано'}",
        ])

    async def _fetch_rating_window(self, base_id: int):
        try:
            rating_data = await self.rating_api.get_tournament(base_id)
        except Exception:
            logger.exception(
                "Не удалось получить турнир %s с сайта рейтинга",
                base_id,
            )
            return None
        return rating_data.get("date_start"), rating_data.get("date_end")

    async def notify_ready_players(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        game_id: int,
        text: str,
        players=None,
    ):
        if players is None:
            players = self.db.get_ready_players_for_game(game_id)
        for player in players:
            tg_username = player[5]
            tg_id = player[6]
            notif = player[7]
            if not notif:
                continue
            try:
                await context.bot.send_message(
                    chat_id=tg_id,
                    text=text,
                )
            except Exception:
                logger.exception(
                    "Не удалось отправить уведомление игроку %s.",
                    tg_username,
                )

    async def _delete_game_poll_message(self, bot, game: dict) -> None:
        message_id = game.get("poll")
        if message_id is None:
            return
        for chat_id in (TEAM_CHAT_ID, ANOTHER_CHAT_ID):
            try:
                await bot.delete_message(
                    chat_id=chat_id,
                    message_id=message_id,
                )
                return
            except Exception:
                logger.debug(
                    "Не удалось удалить опрос игры %s из чата %s",
                    game.get("base_id"),
                    chat_id,
                    exc_info=True,
                )
        logger.warning(
            "Не удалось удалить опрос для игры %s",
            game.get("base_id"),
        )

    async def show_games_for_edit(self, update: Update):
        games = self.db.get_future_games(10, None)

        if not games:
            await update.message.reply_text(
                "Будущих игр нет."
            )
            return

        keyboard = []

        for game in games:
            game_id, name, place, date_start = game

            keyboard.append([
                InlineKeyboardButton(
                    text=name or str(game_id),
                    callback_data=f"{EDIT_GAME_CALLBACK}:{game_id}",
                )
            ])

        await update.message.reply_text(
            "Выберите игру:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    async def show_edit_game_menu(self, query, game_id: int):
        game = self.db.get_game(game_id)

        if game is None:
            await query.message.reply_text("Игра не найдена.")
            return

        date_label = "Обновить дату" if game["is_festival"] else "Изменить дату"
        keyboard = [
            [InlineKeyboardButton(
                "Изменить место",
                callback_data=f"{EDIT_PLACE_CALLBACK}:{game_id}",
            )],
            [InlineKeyboardButton(
                date_label,
                callback_data=f"{EDIT_DATE_CALLBACK}:{game_id}",
            )],
            [InlineKeyboardButton(
                "Удалить",
                callback_data=f"{EDIT_DELETE_CALLBACK}:{game_id}",
            )],
        ]

        await query.message.reply_text(
            self._game_summary(game),
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    async def start_edit_place(self, query, context, game_id: int):
        game = self.db.get_game(game_id)

        if game is None:
            await query.message.reply_text("Игра не найдена.")
            return

        context.user_data["state"] = STATE_UPDATE_PLACE
        context.user_data["game_id"] = game_id

        prompt = "Введите новое место:"
        if game.get("place"):
            prompt += f"\nСейчас: {game['place']}"

        await self.ask_place(query.message, prompt)

    async def handle_update_place(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ):
        if update.message.text == BTN_BACK:
            await self.reset_keyboard_and_state(update, context)
            return

        game_id = context.user_data.get("game_id")

        if game_id is None:
            await self.reset_keyboard_and_state(update, context)
            return

        new_place = update.message.text
        success = self.db.add_place_for_game(
            game_id,
            new_place
        )

        if success:
            await update.message.reply_text(
                "Место обновлено.",
                reply_markup=ReplyKeyboardRemove(),
            )

            logger.info(
                "%s изменил место игры %s",
                update.effective_user.id,
                game_id,
            )

            game = self.db.get_game(game_id)
            if game:
                await self.notify_ready_players(
                    context,
                    game_id,
                    (
                        f"Место проведения игры «{game['name']}» изменено.\n"
                        f"Новое место: {new_place}"
                    ),
                )

        else:
            await update.message.reply_text(
                "Не удалось обновить место.",
                reply_markup=ReplyKeyboardRemove(),
            )

        await self.reset_keyboard_and_state(update, context)

    def _calendar_date(self, value):
        if value is None:
            return None
        return value.date()

    def _festival_dates_equal(self, old_start, old_end, new_start, new_end) -> bool:
        old_end = old_end or old_start
        new_end = new_end or new_start
        return (
            self._calendar_date(old_start) == self._calendar_date(new_start)
            and self._calendar_date(old_end) == self._calendar_date(new_end)
        )

    def _telegram_message_link(self, chat_id, message_id) -> Optional[str]:
        if chat_id is None or message_id is None:
            return None
        try:
            chat_id = int(chat_id)
        except (TypeError, ValueError):
            return None
        chat_text = str(chat_id)
        if chat_text.startswith("-100"):
            return f"https://t.me/c/{chat_text[4:]}/{message_id}"
        return None

    async def _poll_message_link_for_chat(self, bot, chat_id, message_id) -> Optional[str]:
        link = self._telegram_message_link(chat_id, message_id)
        if link:
            return link
        try:
            chat = await bot.get_chat(chat_id)
        except Exception:
            return None
        if getattr(chat, "username", None):
            return f"https://t.me/{chat.username}/{message_id}"
        return self._telegram_message_link(chat.id, message_id)

    async def start_edit_date(self, query, context, game_id: int):
        game = self.db.get_game(game_id)

        if game is None:
            await query.message.reply_text("Игра не найдена.")
            return

        if game["is_festival"]:
            await self.refresh_festival_dates(query, context, game)
            return

        window = await self._fetch_rating_window(game_id)
        if window is None:
            await query.message.reply_text(
                "Не удалось получить сроки с сайта рейтинга. Дата не изменена."
            )
            return

        context.user_data["game_id"] = game_id
        context.user_data["is_festival"] = False
        context.user_data["rating_date_start"] = window[0]
        context.user_data["rating_date_end"] = window[1]
        context.user_data["state"] = STATE_EDIT_DATE

        prompt = "Введите дату в формате ДД.ММ.ГГ ЧЧ:ММ"

        current = get_when_text(
            game["date_start"],
            game["date_end"],
            False,
        )
        if current:
            prompt += f"\nСейчас: {current}"

        window_txt = format_msk_window(window[0], window[1])
        if window_txt:
            prompt += f"\nСрок проведения (GMT+3): {window_txt}"

        await query.message.reply_text(
            prompt,
            reply_markup=self.back_keyboard(),
        )

    async def refresh_festival_dates(self, query, context, game: dict):
        game_id = game["base_id"]
        try:
            rating_data = await self.rating_api.get_tournament(game_id)
        except Exception:
            logger.exception(
                "Не удалось получить турнир %s с сайта рейтинга",
                game_id,
            )
            await query.message.reply_text(
                "Не удалось получить даты с сайта рейтинга."
            )
            return

        date_start = to_msk_naive(rating_data.get("date_start"))
        date_end = to_msk_naive(rating_data.get("date_end"))

        if date_start is None:
            await query.message.reply_text(
                "На сайте рейтинга нет дат проведения. Дата не изменена."
            )
            return

        if date_end is None:
            date_end = date_start

        old_when = get_when_text(game["date_start"], game["date_end"], True)
        new_when = get_when_text(date_start, date_end, True)

        if self._festival_dates_equal(
            game["date_start"],
            game["date_end"],
            date_start,
            date_end,
        ):
            await query.message.reply_text(
                f"Даты не изменились: {new_when or 'не указаны'}."
            )
            return

        if not self.db.add_dates_for_game(game_id, date_start, date_end):
            await query.message.reply_text("Не удалось обновить дату.")
            return

        await query.message.reply_text(
            f"Дата обновлена: {new_when}."
        )
        logger.info(
            "%s обновил даты фестиваля %s",
            query.from_user.id if query.from_user else "?",
            game_id,
        )

        await self.notify_team_festival_dates_changed(
            context,
            game,
            old_when,
            new_when,
        )
        self.db.clear_game_poll(game_id)

    async def notify_team_festival_dates_changed(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        game: dict,
        old_when: str,
        new_when: str,
    ):
        name = game.get("name") or str(game.get("base_id"))
        lines = [
            f"Даты фестиваля «{name}» изменились.",
            f"Было: {old_when or 'не указано'}",
            f"Стало: {new_when or 'не указано'}",
        ]

        poll_id = game.get("poll")
        chat_ids = (TEAM_CHAT_ID, ANOTHER_CHAT_ID)

        if poll_id is not None:
            for chat_id in chat_ids:
                poll_link = await self._poll_message_link_for_chat(
                    context.bot,
                    chat_id,
                    poll_id,
                )
                text_lines = list(lines)
                if poll_link:
                    text_lines.append(
                        f"Старый опрос больше не актуален: {poll_link}"
                    )
                else:
                    text_lines.append("Старый опрос больше не актуален.")
                try:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text="\n".join(text_lines),
                        reply_to_message_id=poll_id,
                        disable_web_page_preview=True,
                    )
                    return
                except Exception:
                    logger.debug(
                        "Не удалось ответить на опрос в чате %s об изменении дат фестиваля %s",
                        chat_id,
                        game.get("base_id"),
                        exc_info=True,
                    )

            fallback_link = None
            for chat_id in chat_ids:
                fallback_link = await self._poll_message_link_for_chat(
                    context.bot,
                    chat_id,
                    poll_id,
                )
                if fallback_link:
                    break
            if fallback_link:
                lines.append(
                    f"Старый опрос больше не актуален: {fallback_link}"
                )
            else:
                lines.append("Старый опрос больше не актуален.")

        text = "\n".join(lines)
        for chat_id in chat_ids:
            try:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    disable_web_page_preview=True,
                )
                return
            except Exception:
                logger.debug(
                    "Не удалось оповестить чат %s об изменении дат фестиваля %s",
                    chat_id,
                    game.get("base_id"),
                    exc_info=True,
                )

        logger.warning(
            "Не удалось оповестить команду об изменении дат фестиваля %s",
            game.get("base_id"),
        )

    def _rating_window_error(self, context) -> str:
        window = format_msk_window(
            context.user_data.get("rating_date_start"),
            context.user_data.get("rating_date_end"),
        ) or "не указан"
        return (
            "Введённая дата не входит в сроки проведения турнира "
            f"({window}, GMT+3).\n"
            "Исправьте дату."
        )

    async def handle_edit_date(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ):
        if update.message.text == BTN_BACK:
            await self.reset_keyboard_and_state(update, context)
            return

        game_id = context.user_data.get("game_id")
        if game_id is None:
            await self.reset_keyboard_and_state(update, context)
            return

        try:
            game_when = datetime.strptime(
                update.message.text.strip(),
                "%d.%m.%y %H:%M",
            )
        except ValueError:
            await update.message.reply_text(
                "Неверный формат даты.\n"
                "Используйте ДД.ММ.ГГ ЧЧ:ММ"
            )
            return

        if not is_datetime_in_rating_window(
            game_when,
            context.user_data.get("rating_date_start"),
            context.user_data.get("rating_date_end"),
        ):
            await update.message.reply_text(self._rating_window_error(context))
            return

        await self._save_edited_dates(update, context, game_id, game_when, None)

    async def _save_edited_dates(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        game_id: int,
        date_start,
        date_end,
    ):
        success = self.db.add_dates_for_game(
            game_id,
            date_start,
            date_end,
        )

        if not success:
            await update.message.reply_text("Не удалось обновить дату.")
            await self.reset_keyboard_and_state(update, context)
            return

        game = self.db.get_game(game_id)
        when_text = ""
        if game:
            when_text = get_when_text(
                game["date_start"],
                game["date_end"],
                game["is_festival"],
            )

        await update.message.reply_text("Дата обновлена.")
        logger.info(
            "%s изменил дату игры %s",
            update.effective_user.id,
            game_id,
        )

        if game and when_text:
            await self.notify_ready_players(
                context,
                game_id,
                (
                    f"Дата проведения игры «{game['name']}» изменена.\n"
                    f"Новая дата: {when_text}"
                ),
            )

        await self.reset_keyboard_and_state(update, context)

    async def start_edit_delete(self, query, context, game_id: int):
        game = self.db.get_game(game_id)

        if game is None:
            await query.message.reply_text("Игра не найдена.")
            return

        context.user_data["state"] = STATE_EDIT_DELETE_CONFIRM
        context.user_data["game_id"] = game_id

        await query.message.reply_text(
            f"Удалить {game['name']}?",
            reply_markup=self.yes_no_keyboard(),
        )

    async def handle_edit_delete_confirm(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ):
        text = update.message.text

        if text == BTN_NO or text == BTN_BACK:
            await self.reset_keyboard_and_state(update, context)
            return

        if text != BTN_YES:
            await update.message.reply_text(
                "Выберите Да или Нет.",
                reply_markup=self.yes_no_keyboard(),
            )
            return

        game_id = context.user_data.get("game_id")
        game = self.db.get_game(game_id) if game_id is not None else None

        if game_id is None or game is None:
            await update.message.reply_text("Игра не найдена.")
            await self.reset_keyboard_and_state(update, context)
            return

        notify_text = f"Игра «{game['name']}» отменена."
        players = self.db.get_ready_players_for_game(game_id)
        success = self.db.delete_game(game_id)

        if not success:
            await update.message.reply_text("Не удалось удалить игру.")
            await self.reset_keyboard_and_state(update, context)
            return

        await self._delete_game_poll_message(context.bot, game)
        await self.notify_ready_players(
            context,
            game_id,
            notify_text,
            players=players,
        )

        logger.info(
            "%s удалил игру %s",
            update.effective_user.id,
            game_id,
        )
        await update.message.reply_text("Игра удалена.")
        await self.reset_keyboard_and_state(update, context)
