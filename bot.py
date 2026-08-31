import os
import logging
from datetime import datetime, timedelta
from typing import Optional

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardRemove
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    PollAnswerHandler,
    ContextTypes,
    filters,
)

from sqlite_db import SqliteDB
from rating_api import RatingAPI
from utils import (
    MSK_TZ,
    add_months,
    format_msk_window,
    get_when_text,
    is_datetime_in_rating_window,
    to_msk_naive,
)

SQLITE_DB_PATH = os.environ["SQLITE_PATH"]


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)

# =====================================================================
# КОНСТАНТЫ
# =====================================================================

TEAM_CHAT_ID = os.environ["TEAM_CHAT_ID"]
ANOTHER_CHAT_ID = os.environ["ANOTHER_CHAT_ID"]

BTN_TOURNAMENTS = "Показать мои турниры"
BTN_PLAYING_WITH = "Посмотреть с кем играю"

BTN_ADD_GAME = "Добавить игру"
BTN_ADD_FESTIVAL = "Добавить фестиваль"
BTN_UPDATE_PLACE = "Обновить место"
BTN_CREATE_POLL = "Создать опрос"
BTN_SHOW_POLL = "Показать опрос"
BTN_LINK_PLAYER = "Привязать к рейтингу"
BTN_ALL_TOURNAMENTS = "Показать турниры"
BTN_LEGIONARY = "Создать сообщение для легчата"

BTN_YES = "Да"
BTN_NO = "Нет"
BTN_BACK = "Назад"
BTN_FIND_OTHER_GAME = "Найти другой турнир"
BTN_ADD_GAME_BY_ID = "Ввести турнир через ID"

STATE_NONE = "none"
STATE_ADD_GAME_SELECT = "add_game_select"
STATE_ADD_GAME_SEARCH_NAME = "add_game_search_name"
STATE_ADD_GAME_ID = "add_game_id"
STATE_ADD_GAME_CONFIRM = "add_game_confirm"
STATE_ADD_GAME_PLACE = "add_game_place"
STATE_ADD_GAME_DATE_START = "add_game_date_start"
STATE_ADD_GAME_DATE_END = "add_game_date_end"

STATE_UPDATE_PLACE = "update_place"

STATE_ADD_PLAYER_RATING_ID = "add_player_rating_id"
STATE_ADD_PLAYER_CONFIRM = "add_player_confirm"

PLAYERS_CALLBACK = 'players'
PLACE_CALLBACK = 'place'
POLL_CALLBACK = 'poll'
ADD_PLAYER_CALLBACK = 'add_player'
SHOW_POLL_CALLBACK = 'show_poll'
LEGIONARY_CALLBACK = 'legionary'

TEAM_NAME = "Советское Шампанское"
TEAM_LINK = "https://rating.pecheny.me/teams/85915"


class KvrmBot:
    def __init__(self):
        # =============================================================
        # Конфигурация из environment
        # =============================================================

        self.api_key = os.environ['API_KEY']
        os.makedirs(os.path.dirname(SQLITE_DB_PATH), exist_ok=True)
        self.db = SqliteDB(
            host="",
            port=0,
            database=SQLITE_DB_PATH,
            user="",
            password="",
        )
        self.rating_api = RatingAPI()

        self.application = (
            Application.builder()
            .token(self.api_key)
            .build()
        )

        self._register_handlers()

    # =================================================================
    # HANDLERS
    # =================================================================

    def _register_handlers(self):
        self.application.add_handler(
            CommandHandler("start", self.start)
        )

        self.application.add_handler(
            CallbackQueryHandler(
                self.callback_handler
            )
        )

        self.application.add_handler(
            PollAnswerHandler(
                self.poll_answer_handler
            )
        )

        self.application.add_handler(
            MessageHandler(
                filters.TEXT & ~filters.COMMAND,
                self.text_handler
            )
        )

    # =================================================================
    # КЛАВИАТУРЫ
    # =================================================================

    def main_keyboard(self, is_admin: bool):
        buttons = [
            [BTN_TOURNAMENTS],
            [BTN_PLAYING_WITH],
        ]

        if is_admin:
            buttons.extend([
                [BTN_ADD_GAME],
                [BTN_ADD_FESTIVAL],
                [BTN_UPDATE_PLACE],
                [BTN_CREATE_POLL],
                [BTN_SHOW_POLL],
                [BTN_LINK_PLAYER],
                [BTN_ALL_TOURNAMENTS],
                [BTN_LEGIONARY],
            ])

        return ReplyKeyboardMarkup(
            buttons,
            resize_keyboard=True,
        )

    def yes_no_keyboard(self):
        return ReplyKeyboardMarkup(
            [
                [BTN_YES, BTN_NO],
            ],
            resize_keyboard=True,
        )

    def add_game_select_keyboard(self, labels: list[str], extra_button: str):
        buttons = [[label] for label in labels]
        buttons.append([extra_button])
        return ReplyKeyboardMarkup(
            buttons,
            resize_keyboard=True,
        )

    # =================================================================
    # START
    # =================================================================

    async def start(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ):
        tg_id = update.effective_user.id
        username = update.effective_user.username

        #await update.message.reply_text(
        #            "Айдишник чата:" + str(update.effective_chat.id)
        #        )

        if update.effective_chat.type != 'private':
            return

        # Если пользователя ещё нет в players,
        # добавляем его туда.
        self.db.add_player_by_tg_id(tg_id, username)
        await self.reset_keyboard_and_state(update, context)

    async def reset_keyboard_and_state(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ):
        # Сброс клавиатуры и состояния
        context.user_data["state"] = STATE_NONE
        await self.show_main_menu(update)

    # =================================================================
    # TEXT HANDLER
    # =================================================================

    async def text_handler(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ):
        if update.message is None or update.effective_chat.type != 'private':
            return

        text = update.message.text
        tg_id = update.effective_user.id

        state = context.user_data.get(
            "state",
            STATE_NONE
        )

        logger.info(f'{tg_id}: {state} | {text}')

        # -------------------------------------------------------------
        # Состояния
        # -------------------------------------------------------------

        if state == STATE_ADD_GAME_SELECT:
            await self.handle_add_game_select(update, context)
            return

        if state == STATE_ADD_GAME_SEARCH_NAME:
            await self.handle_add_game_search_name(update, context)
            return

        if state == STATE_ADD_GAME_ID:
            await self.handle_add_game_id(update, context)
            return

        if state == STATE_ADD_GAME_CONFIRM:
            await self.handle_add_game_confirm(update, context)
            return

        if state == STATE_ADD_GAME_PLACE:
            await self.handle_add_game_place(update, context)
            return

        if state == STATE_ADD_GAME_DATE_START:
            await self.handle_add_game_date_start(update, context)
            return

        if state == STATE_ADD_GAME_DATE_END:
            await self.handle_add_game_date_end(update, context)
            return

        if state == STATE_UPDATE_PLACE:
            await self.handle_update_place(update, context)
            return

        if state == STATE_ADD_PLAYER_RATING_ID:
            await self.handle_add_player_rating_id(update, context)
            return

        if state == STATE_ADD_PLAYER_CONFIRM:
            await self.handle_add_player_confirm(update, context)
            return

        # -------------------------------------------------------------
        # Главное меню
        # -------------------------------------------------------------

        is_admin = self.db.is_admin(tg_id)

        if text == BTN_TOURNAMENTS:
            await self.show_my_tournaments(update)
            return

        if text == BTN_PLAYING_WITH:
            await self.show_tournaments_for_players(update)
            return

        if is_admin and text == BTN_ADD_GAME:
            await self.start_add_game(update, context, False)
            return

        if is_admin and text == BTN_ADD_FESTIVAL:
            await self.start_add_game(update, context, True)
            return

        if is_admin and text == BTN_UPDATE_PLACE:
            await self.show_games_for_place_update(update, context)
            return

        if is_admin and text == BTN_CREATE_POLL:
            await self.show_games_for_poll(update)
            return

        if is_admin and text == BTN_SHOW_POLL:
            await self.show_games_with_polls(update)
            return

        if is_admin and text == BTN_LINK_PLAYER:
            await self.show_players_for_add(update)
            return

        if is_admin and text == BTN_ALL_TOURNAMENTS:
            await self.show_tournaments(update)
            return

        if is_admin and text == BTN_LEGIONARY:
            await self.legionary(update)
            return

        if text == BTN_BACK:
            await self.show_main_menu(update)
            return

        await update.message.reply_text(
            "Неизвестная команда."
        )

    # =================================================================
    # ГЛАВНОЕ МЕНЮ
    # =================================================================

    async def show_main_menu(self, update: Update):
        tg_id = update.effective_user.id
        is_admin = self.db.is_admin(tg_id)

        if update.message:
            await update.message.reply_text(
                "Выберите действие:",
                reply_markup=self.main_keyboard(is_admin),
            )
        elif update.callback_query:
            await update.callback_query.message.reply_text(
                "Выберите действие:",
                reply_markup=self.main_keyboard(is_admin),
            )

    # =================================================================
    # ТУРНИРЫ ПОЛЬЗОВАТЕЛЯ
    # =================================================================

    async def show_my_tournaments(self, update: Update):
        tg_id = update.effective_user.id

        games = self.db.get_my_tournaments(tg_id)

        if not games:
            await update.message.reply_text(
                "Турниров нет."
            )
            return

        lines = []

        try:
            for game in games:
                game_id, base_id, name, place, date_start, date_end, is_fest = game

                when_text = get_when_text(date_start, date_end, is_fest)
                lines.append(
                    f"{base_id}. {name} — "
                    f"{place or 'Место не указано'} — "
                    f"{when_text}"
                )

            await update.message.reply_text(
                "\n".join(lines)
            )
        except Exception:
            await update.message.reply_text("Произошла ошибка при попытке показать мои турниры.")

    # =================================================================
    # С КЕМ ИГРАЮ
    # =================================================================

    async def show_tournaments_for_players(
        self,
        update: Update
    ):
        tg_id = update.effective_user.id

        games = self.db.get_my_tournaments(tg_id)

        if not games:
            await update.message.reply_text(
                "Турниров нет."
            )
            return

        keyboard = []

        for game in games:
            game_id, base_id, name, place, date_start, date_end, is_fest = game

            keyboard.append([
                InlineKeyboardButton(
                    text=name or str(base_id),
                    callback_data=f"{PLAYERS_CALLBACK}:{base_id}",
                )
            ])

        await update.message.reply_text(
            "Выберите турнир:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    async def show_players_for_game(
        self,
        query,
        game_id: int
    ):

        players = self.db.get_ready_players_for_game(game_id)

        if not players:
            text = "Игроков нет."
        else:
            lines = []

            for base_id, surname, name, patronymic, flag, tg_username, tg_id, notif in players:
                if base_id:
                    new_line = ' '.join([str(base_id), ':', flag, surname or '',
                        name or '', patronymic or '']).strip()
                else:
                    new_line = ' '.join([flag, ':', tg_username or '']).strip()
                lines.append(new_line)

            text = "\n".join(lines)

        await query.message.reply_text(text)

    # =================================================================
    # CALLBACK QUERY
    # =================================================================

    async def callback_handler(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ):
        query = update.callback_query

        await query.answer()

        data = query.data

        callback_cmd, text = data.split(':')[:2]

        if callback_cmd == PLAYERS_CALLBACK:
            game_id = int(text)

            await self.show_players_for_game(
                query,
                game_id
            )
            return

        if callback_cmd == PLACE_CALLBACK:
            game_id = int(text)

            context.user_data["state"] = STATE_UPDATE_PLACE
            context.user_data["game_id"] = game_id
            await query.message.reply_text(
                "Новое место:"
            )
            return

        if callback_cmd == POLL_CALLBACK:
            game_id = int(text)
            await self.create_or_forward_poll(
                query,
                update,
                context,
                game_id
            )
            return

        if callback_cmd == ADD_PLAYER_CALLBACK:
            player_id = int(text)

            context.user_data["player_id"] = player_id
            context.user_data["state"] = STATE_ADD_PLAYER_RATING_ID
            await query.message.reply_text(
                "Введите id рейтинга:"
            )
            return

        if callback_cmd == SHOW_POLL_CALLBACK:
            game_id = int(text)
            await self.show_poll(
                query,
                context.bot,
                game_id
            )
            return

        if callback_cmd == LEGIONARY_CALLBACK:
            game_id = int(text)
            await self.create_msg_for_legionary_chat(
                query,
                context,
                game_id
            )
            return

    # =================================================================
    # ДОБАВЛЕНИЕ ИГРЫ
    # =================================================================

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
        date_end_to = add_months(today, 2)

        try:
            tournaments = await self.rating_api.list_synchrons(
                date_end_from=today,
                date_end_to=date_end_to,
                name=text,
                items_per_page=100,
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

        await update.message.reply_text(
            "Введите место:"
        )

    async def handle_add_game_place(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ):
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
        await update.message.reply_text(prompt)

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
    # ОБНОВЛЕНИЕ МЕСТА
    # =================================================================

    async def show_games_for_place_update(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ):
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
                    callback_data=f"{PLACE_CALLBACK}:{game_id}",
                )
            ])

        await update.message.reply_text(
            "Выберите игру:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    async def handle_update_place(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ):
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
                "Место обновлено."
            )

            await self.notify_update_place(update, context, game_id, new_place)

        else:
            await update.message.reply_text(
                "Не удалось обновить место."
            )

        await self.reset_keyboard_and_state(update, context)

    async def notify_update_place(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        game_id: int,
        new_place: str
    ):

        players = self.db.get_ready_players_for_game(game_id)
        game = self.db.get_game(game_id)

        logger.info(
                    "%s изменил место игры",
                    update.effective_user.id
                )

        for player in players:
            tg_username = player[5]
            tg_id = player[6]
            notif = player[7]
            if not notif:
                continue
            try:
                await context.bot.send_message(
                    chat_id=tg_id,
                    text=(
                        f"Место проведения игры «{game['name']}» изменено.\n"
                        f"Новое место: {new_place}"
                    ),
                )
            except Exception:
                logger.exception(
                    "Не удалось отправить уведомление игроку %s.",
                    tg_username
                )

    # =================================================================
    # ОПРОС
    # =================================================================

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
        games = self.db.get_future_games(
            limit=10,
            has_poll=True,
        )

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
                # type="quiz",
                is_anonymous=False,
                allows_multiple_answers=True,
                correct_option_id=0,
                allows_revoting=True
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

    # =================================================================
    # ДОБАВЛЕНИЕ ИГРОКА
    # =================================================================

    async def show_players_for_add(
        self,
        update: Update
    ):
        players = self.db.get_unlinked_players(10)

        if not players:
            await update.message.reply_text(
                "Нет игроков, которых можно добавить."
            )
            return

        keyboard = []

        for player in players:
            player_id, tg_id, name, surname, nickname = player

            player_name = (
                f"{surname or ''} {name or ''}"
            ).strip()

            keyboard.append([
                InlineKeyboardButton(
                    text=nickname or player_name or str(tg_id),
                    callback_data=f"{ADD_PLAYER_CALLBACK}:{tg_id}",
                )
            ])

        await update.message.reply_text(
            "Выберите игрока:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    async def handle_add_player_rating_id(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ):
        try:
            rating_id = int(update.message.text)
        except ValueError:
            await update.message.reply_text(
                "ID рейтинга должен быть числом."
            )
            return

        try:
            data = await self.rating_api.get_player(rating_id)
        except Exception as exc:
            logger.exception(exc)

            await update.message.reply_text(
                "Не удалось получить данные игрока."
            )
            return

        context.user_data["rating_player"] = data
        context.user_data["state"] = STATE_ADD_PLAYER_CONFIRM

        full_name = " ".join(
            x for x in [
                data.get("surname"),
                data.get("name"),
                data.get("patronymic"),
            ]
            if x
        )

        await update.message.reply_text(
            f"Это {full_name}?",
            reply_markup=self.yes_no_keyboard(),
        )

    async def handle_add_player_confirm(
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

        player_id = context.user_data.get("player_id")
        data = context.user_data.get("rating_player")

        if player_id is None or not data:
            await self.reset_keyboard_and_state(update, context)
            return

        success = self.db.update_player_by_tg_id(
            player_id=player_id,
            base_id=data.get("id"),
            name=data.get("name"),
            surname=data.get("surname"),
            patronimyc=data.get("patronymic"),
        )

        if success:
            await update.message.reply_text(
                "Игрок добавлен."
            )
        else:
            await update.message.reply_text(
                "Не удалось добавить игрока."
            )

        await self.reset_keyboard_and_state(update, context)

    # =================================================================
    # ВСЕ ТУРНИРЫ
    # =================================================================

    async def show_tournaments(
        self,
        update: Update
    ):
        games = self.db.get_future_games(10, None)

        if not games:
            await update.message.reply_text(
                "Турниров нет."
            )
            return

        keyboard = []

        for game in games:
            game_id, name, place, date_start = game

            keyboard.append([
                InlineKeyboardButton(
                    text=name or str(game_id),
                    callback_data=f"players:{game_id}",
                )
            ])

        await update.message.reply_text(
            "Все турниры:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    # =================================================================
    # СООБЩЕНИЕ ДЛЯ ЧАТА ЛЕГИОНЕРОВ
    # =================================================================

    async def legionary(self, update):

        games = self.db.get_future_games(10, None)

        if not games:
            await update.message.reply_text(
                "Турниров нет."
            )
            return

        keyboard = []

        for game in games:
            game_id, name, place, date_start = game

            keyboard.append([
                InlineKeyboardButton(
                    text=name or str(game_id),
                    callback_data=f"{LEGIONARY_CALLBACK}:{game_id}",
                )
            ])

        await update.message.reply_text(
            "Выберите турнир:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    async def create_msg_for_legionary_chat(
            self,
            update: Update,
            context: ContextTypes.DEFAULT_TYPE,
            game_id: int) -> None:

        game = self.db.get_game(game_id)

        if not game:
            text = "Игра не найдена."
        else:
            lines = []

            when_text = get_when_text(game["date_start"], game["date_end"], game["is_festival"])
            lines.extend([
                "#ищуигрока",
                game["name"],
                game["place"],
                when_text,
                TEAM_NAME,
                TEAM_LINK
            ])

            text = "\n".join(lines)

        await update.message.reply_text(text)

    # =================================================================
    # POLL ANSWER
    # =================================================================

    async def poll_answer_handler(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ):
        answer = update.poll_answer

        if answer is None or answer.user is None:
            return

        tg_id = answer.user.id

        # option 0 = "Да"
        ready = 0 in answer.option_ids

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

        # Проверяем состав только если пользователь выбрал "Да"
        if ready and not game["team_notified"]:
            ready_count = self.db.get_ready_players_count(
                game["base_id"]
            )

            if ready_count >= 6:

                await context.bot.send_message(
                    chat_id=TEAM_CHAT_ID,
                    text=f"Собран состав на {game['name']}",
                )

                self.db.set_team_notified(
                    game["base_id"],
                    True,
                )

    # =================================================================
    # RUN
    # =================================================================

    def run(self):
        logger.info("Бот запускается...")

        try:
            self.application.run_polling()
        finally:
            self.db.close()
            self.shutdown()

    async def shutdown(self):
        await self.rating_api.close()

if __name__ == "__main__":
    bot = KvrmBot()
    bot.run()
