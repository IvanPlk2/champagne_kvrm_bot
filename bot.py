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
from announce_offers import AnnounceOffers
from const import ANNOUNCE_OFFER_CALLBACK, MSK_TZ
from utils import (
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
BTN_EDIT_GAME = "Редактировать игру"
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
STATE_EDIT_DATE = "edit_date"
STATE_EDIT_DELETE_CONFIRM = "edit_delete_confirm"

STATE_ADD_PLAYER_RATING_ID = "add_player_rating_id"
STATE_ADD_PLAYER_CONFIRM = "add_player_confirm"

PLAYERS_CALLBACK = 'players'
PLACE_CALLBACK = 'place'
POLL_CALLBACK = 'poll'
ADD_PLAYER_CALLBACK = 'add_player'
LINK_SUGGEST_CALLBACK = 'link_s'
SHOW_POLL_CALLBACK = 'show_poll'
LEGIONARY_CALLBACK = 'legionary'
EDIT_GAME_CALLBACK = 'edit'
EDIT_PLACE_CALLBACK = 'edit_place'
EDIT_DATE_CALLBACK = 'edit_date'
EDIT_DELETE_CALLBACK = 'edit_delete'

ADMIN_CALLBACKS = {
    PLACE_CALLBACK,
    POLL_CALLBACK,
    ADD_PLAYER_CALLBACK,
    LINK_SUGGEST_CALLBACK,
    SHOW_POLL_CALLBACK,
    LEGIONARY_CALLBACK,
    EDIT_GAME_CALLBACK,
    EDIT_PLACE_CALLBACK,
    EDIT_DATE_CALLBACK,
    EDIT_DELETE_CALLBACK,
    ANNOUNCE_OFFER_CALLBACK,
}

ADMIN_STATES = {
    STATE_ADD_GAME_SELECT,
    STATE_ADD_GAME_SEARCH_NAME,
    STATE_ADD_GAME_ID,
    STATE_ADD_GAME_CONFIRM,
    STATE_ADD_GAME_PLACE,
    STATE_ADD_GAME_DATE_START,
    STATE_ADD_GAME_DATE_END,
    STATE_UPDATE_PLACE,
    STATE_EDIT_DATE,
    STATE_EDIT_DELETE_CONFIRM,
    STATE_ADD_PLAYER_RATING_ID,
    STATE_ADD_PLAYER_CONFIRM,
}

TEAM_NAME = "Советское Шампанское"
TEAM_ID = 85915
TEAM_LINK = "https://rating.pecheny.me/teams/85915"

ROSTER_MIN_PLAYERS = 6
ROSTER_BROKE_DELAY_SECONDS = 60
ROSTER_BROKE_JOB_PREFIX = "roster_broke:"


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
        self.announces = AnnounceOffers(self.db, self.rating_api)

        self.application = (
            Application.builder()
            .token(self.api_key)
            .post_init(self._post_init)
            .post_shutdown(self._post_shutdown)
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
                [BTN_EDIT_GAME],
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

    def back_keyboard(self):
        return ReplyKeyboardMarkup(
            [
                [BTN_BACK],
            ],
            resize_keyboard=True,
        )

    def place_keyboard(self, places: list[str]):
        buttons = [[place] for place in places]
        buttons.append([BTN_BACK])
        return ReplyKeyboardMarkup(
            buttons,
            resize_keyboard=True,
        )

    async def ask_place(self, message, prompt: str):
        places = self.db.get_recent_non_festival_places(15)
        await message.reply_text(
            prompt,
            reply_markup=self.place_keyboard(places),
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

        if state in ADMIN_STATES and not self.db.is_admin(tg_id):
            logger.warning(
                "Пользователь %s попытался использовать админ-состояние %s",
                tg_id,
                state,
            )
            await update.message.reply_text("Недостаточно прав.")
            await self.reset_keyboard_and_state(update, context)
            return

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

        if state == STATE_EDIT_DATE:
            await self.handle_edit_date(update, context)
            return

        if state == STATE_EDIT_DELETE_CONFIRM:
            await self.handle_edit_delete_confirm(update, context)
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

        if is_admin and text == BTN_EDIT_GAME:
            await self.show_games_for_edit(update)
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
        data = query.data or ""
        parts = data.split(":")

        if len(parts) < 2:
            await query.answer()
            return

        callback_cmd, text = parts[0], parts[1]
        tg_id = update.effective_user.id

        if callback_cmd in ADMIN_CALLBACKS and not self.db.is_admin(tg_id):
            logger.warning(
                "Пользователь %s вызвал админ-callback %s",
                tg_id,
                callback_cmd,
            )
            await query.answer("Недостаточно прав.", show_alert=True)
            return
        elif callback_cmd == ANNOUNCE_OFFER_CALLBACK:
            if not self.db.can_receive_announce_offers(tg_id):
                logger.warning(
                    "Пользователь %s вызвал callback анонса без флага",
                    tg_id,
                )
                await query.answer("Недостаточно прав.", show_alert=True)
                return

        await query.answer()

        if callback_cmd == PLAYERS_CALLBACK:
            game_id = int(text)

            await self.show_players_for_game(
                query,
                game_id
            )
            return

        if callback_cmd == PLACE_CALLBACK:
            game_id = int(text)

            await self.start_edit_place(query, context, game_id)
            return

        if callback_cmd == EDIT_GAME_CALLBACK:
            game_id = int(text)
            await self.show_edit_game_menu(query, game_id)
            return

        if callback_cmd == EDIT_PLACE_CALLBACK:
            game_id = int(text)
            await self.start_edit_place(query, context, game_id)
            return

        if callback_cmd == EDIT_DATE_CALLBACK:
            game_id = int(text)
            await self.start_edit_date(query, context, game_id)
            return

        if callback_cmd == EDIT_DELETE_CALLBACK:
            game_id = int(text)
            await self.start_edit_delete(query, context, game_id)
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
            await self.ask_link_player_id(query, context, player_id)
            return

        if callback_cmd == LINK_SUGGEST_CALLBACK:
            rating_id = int(text)
            await self.confirm_link_player_by_id(query.message, context, rating_id)
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

        if callback_cmd == ANNOUNCE_OFFER_CALLBACK:
            await self.announces.handle_callback(query, context, parts)
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

    def _player_full_name(self, data: dict) -> str:
        return " ".join(
            x for x in [
                data.get("surname"),
                data.get("name"),
                data.get("patronymic"),
            ]
            if x
        )

    def _link_suggestion_keyboard(self, suggestions: list[dict]):
        used_labels: set[str] = set()
        keyboard = []
        for player in suggestions:
            name = " ".join(
                x for x in [player.get("surname"), player.get("name")]
                if x
            ).strip() or str(player["id"])
            label = name[:64]
            if label in used_labels:
                suffix = f" [{player['id']}]"
                label = (name[: max(0, 64 - len(suffix))] + suffix)[:64]
            used_labels.add(label)
            keyboard.append([
                InlineKeyboardButton(
                    text=label,
                    callback_data=f"{LINK_SUGGEST_CALLBACK}:{player['id']}",
                )
            ])
        return InlineKeyboardMarkup(keyboard) if keyboard else None

    async def ask_link_player_id(self, query, context, player_id: int):
        context.user_data["player_id"] = player_id
        context.user_data["state"] = STATE_ADD_PLAYER_RATING_ID
        context.user_data["link_suggestions"] = {}

        await query.message.reply_text(
            "Введите id рейтинга:",
            reply_markup=self.back_keyboard(),
        )

        game = self.db.get_last_ready_game(player_id)
        if game is None:
            return

        try:
            roster = await self.rating_api.get_team_roster_at_tournament(
                game["base_id"],
                TEAM_ID,
            )
        except Exception:
            logger.exception(
                "Не удалось получить состав команды на турнире %s",
                game["base_id"],
            )
            return

        linked_ids = self.db.get_linked_base_ids()
        suggestions = [
            player for player in roster
            if player["id"] not in linked_ids
        ]
        context.user_data["link_suggestions"] = {
            player["id"]: player for player in suggestions
        }

        keyboard = self._link_suggestion_keyboard(suggestions)
        if not keyboard:
            return

        game_name = game.get("name") or str(game["base_id"])
        await query.message.reply_text(
            f"По составу «{game_name}» это может быть:",
            reply_markup=keyboard,
        )

    async def confirm_link_player_by_id(
        self,
        message,
        context: ContextTypes.DEFAULT_TYPE,
        rating_id: int,
    ):
        if context.user_data.get("player_id") is None:
            await message.reply_text(
                "Сначала выберите игрока Telegram."
            )
            return

        suggestions = context.user_data.get("link_suggestions") or {}
        data = suggestions.get(rating_id)

        if not data:
            try:
                data = await self.rating_api.get_player(rating_id)
            except Exception as exc:
                logger.exception(exc)
                await message.reply_text(
                    "Не удалось получить данные игрока."
                )
                return

        if data.get("id") in self.db.get_linked_base_ids():
            await message.reply_text("Этот игрок уже привязан.")
            return

        context.user_data["rating_player"] = {
            "id": data.get("id"),
            "name": data.get("name"),
            "surname": data.get("surname"),
            "patronymic": data.get("patronymic"),
        }
        context.user_data["state"] = STATE_ADD_PLAYER_CONFIRM

        full_name = self._player_full_name(data) or str(data.get("id"))
        await message.reply_text(
            f"Это {full_name}?",
            reply_markup=self.yes_no_keyboard(),
        )

    async def handle_add_player_rating_id(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ):
        text = (update.message.text or "").strip()
        if text == BTN_BACK:
            await self.reset_keyboard_and_state(update, context)
            return

        try:
            rating_id = int(text)
        except ValueError:
            await update.message.reply_text(
                "ID рейтинга должен быть числом."
            )
            return

        await self.confirm_link_player_by_id(
            update.message,
            context,
            rating_id,
        )

    async def handle_add_player_confirm(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ):
        text = update.message.text

        if text == BTN_NO or text == BTN_BACK:
            context.user_data["state"] = STATE_ADD_PLAYER_RATING_ID
            suggestions = list(
                (context.user_data.get("link_suggestions") or {}).values()
            )
            keyboard = self._link_suggestion_keyboard(suggestions)
            await update.message.reply_text(
                "Введите id рейтинга:",
                reply_markup=self.back_keyboard(),
            )
            if keyboard:
                await update.message.reply_text(
                    "По составу последней игры это может быть:",
                    reply_markup=keyboard,
                )
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

    # =================================================================
    # RUN
    # =================================================================

    async def _post_init(self, application: Application) -> None:
        self.announces.schedule(application)

    async def _post_shutdown(self, application: Application) -> None:
        await self.rating_api.close()
        await self.announces.close()
        self.db.close()

    def run(self):
        logger.info("Бот запускается...")
        self.application.run_polling()

if __name__ == "__main__":
    bot = KvrmBot()
    bot.run()
