import logging
import os

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    PollAnswerHandler,
    ContextTypes,
    filters,
)

from announce_offers import AnnounceOffers
from config import API_KEY, SQLITE_DB_PATH
from const import (
    ACCESS_ADMIN,
    ACCESS_GAMES,
    ADD_PLAYER_CALLBACK,
    ADMIN_CALLBACKS,
    ADMIN_STATES,
    BASE_CALLBACKS,
    BASE_STATES,
    ANNOUNCE_OFFER_CALLBACK,
    BTN_ADD_FESTIVAL,
    BTN_ADD_GAME,
    BTN_ADMIN_GAMES,
    BTN_ADMIN_PLAYERS,
    BTN_ADMIN_POLLS,
    BTN_ALL_TOURNAMENTS,
    BTN_BACK,
    BTN_CREATE_POLL,
    BTN_EDIT_GAME,
    BTN_LEGIONARY,
    BTN_LINK_PLAYER,
    BTN_MANAGE_RIGHTS,
    BTN_PLAYING_WITH,
    BTN_SHOW_POLL,
    BTN_TOURNAMENTS,
    BTN_SETTINGS,
    BTN_ENABLE_NOTIFICATIONS,
    BTN_DISABLE_NOTIFICATIONS,
    BTN_ENABLE_ANNOUNCE_OFFERS,
    BTN_DISABLE_ANNOUNCE_OFFERS,
    EDIT_DATE_CALLBACK,
    EDIT_DELETE_CALLBACK,
    EDIT_GAME_CALLBACK,
    EDIT_PLACE_CALLBACK,
    LEGIONARY_CALLBACK,
    LINK_SUGGEST_CALLBACK,
    PLAYERS_CALLBACK,
    POLL_CALLBACK,
    RIGHTS_CALLBACK,
    SHOW_POLL_CALLBACK,
    STATE_ADD_GAME_CONFIRM,
    STATE_ADD_GAME_DATE_END,
    STATE_ADD_GAME_DATE_START,
    STATE_ADD_GAME_CREATE_POLL,
    STATE_ADD_GAME_ID,
    STATE_ADD_GAME_PLACE,
    STATE_ADD_GAME_SEARCH_NAME,
    STATE_ADD_GAME_SELECT,
    STATE_ADD_PLAYER_CONFIRM,
    STATE_ADD_PLAYER_RATING_ID,
    STATE_RIGHTS_ACTIONS,
    STATE_RIGHTS_CONFIRM,
    STATE_RIGHTS_PICK_BASE_ID,
    STATE_RIGHTS_SELECT,
    STATE_EDIT_DATE,
    STATE_EDIT_DELETE_CONFIRM,
    STATE_NONE,
    STATE_UPDATE_PLACE,
)
from handlers import (
    GameHandlers,
    GameReminderHandlers,
    KeyboardMixin,
    PlayerHandlers,
    PollHandlers,
    RosterHandlers,
    SettingsHandlers,
)
from rating_api import RatingAPI
from sqlite_db import SqliteDB
from utils import with_start_hint

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)


class KvrmBot(
    KeyboardMixin,
    GameHandlers,
    GameReminderHandlers,
    PollHandlers,
    PlayerHandlers,
    RosterHandlers,
    SettingsHandlers,
):
    def __init__(self):
        self.api_key = API_KEY
        os.makedirs(os.path.dirname(SQLITE_DB_PATH), exist_ok=True)
        self.db = SqliteDB(
            database=SQLITE_DB_PATH
        )
        self.rating_api = RatingAPI()
        self.announces = AnnounceOffers(
            self.db,
            self.rating_api,
            schedule_game_reminders=self.schedule_game_reminders,
            create_game_poll=self.send_game_poll,
        )

        self.application = (
            Application.builder()
            .token(self.api_key)
            .post_init(self._post_init)
            .post_shutdown(self._post_shutdown)
            .build()
        )

        self._register_handlers()

    def _register_handlers(self):
        self.application.add_handler(
            CommandHandler("start", self.start)
        )
        self.application.add_handler(
            CallbackQueryHandler(self.callback_handler)
        )
        self.application.add_handler(
            PollAnswerHandler(self.poll_answer_handler)
        )
        self.application.add_handler(
            MessageHandler(
                filters.TEXT & ~filters.COMMAND,
                self.text_handler,
            )
        )

    async def start(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ):
        tg_id = update.effective_user.id
        username = update.effective_user.username

        if update.effective_chat.type != "private":
            return

        self.db.add_player_by_tg_id(tg_id, username)
        await self.reset_keyboard_and_state(update, context)

    async def reset_keyboard_and_state(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ):
        context.user_data["state"] = STATE_NONE
        await self.show_main_menu(update)

    def _state_handlers(self):
        return {
            STATE_ADD_GAME_SELECT: self.handle_add_game_select,
            STATE_ADD_GAME_SEARCH_NAME: self.handle_add_game_search_name,
            STATE_ADD_GAME_ID: self.handle_add_game_id,
            STATE_ADD_GAME_CONFIRM: self.handle_add_game_confirm,
            STATE_ADD_GAME_PLACE: self.handle_add_game_place,
            STATE_ADD_GAME_DATE_START: self.handle_add_game_date_start,
            STATE_ADD_GAME_DATE_END: self.handle_add_game_date_end,
            STATE_ADD_GAME_CREATE_POLL: self.handle_add_game_create_poll,
            STATE_UPDATE_PLACE: self.handle_update_place,
            STATE_EDIT_DATE: self.handle_edit_date,
            STATE_EDIT_DELETE_CONFIRM: self.handle_edit_delete_confirm,
            STATE_ADD_PLAYER_RATING_ID: self.handle_add_player_rating_id,
            STATE_ADD_PLAYER_CONFIRM: self.handle_add_player_confirm,
            STATE_RIGHTS_SELECT: self.handle_rights_select,
            STATE_RIGHTS_PICK_BASE_ID: self.handle_rights_pick_base_id,
            STATE_RIGHTS_ACTIONS: self.handle_rights_actions,
            STATE_RIGHTS_CONFIRM: self.handle_rights_confirm,
        }

    def _menu_actions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        return (
            ((BTN_TOURNAMENTS,), None, lambda: self.show_my_tournaments(update)),
            ((BTN_PLAYING_WITH,), None, lambda: self.show_tournaments_for_players(update)),
            ((BTN_SETTINGS,), None, lambda: self.show_settings_menu(update)),
            (
                (BTN_ENABLE_NOTIFICATIONS, BTN_DISABLE_NOTIFICATIONS),
                None,
                lambda: self.handle_toggle_notifications(update),
            ),
            (
                (BTN_ENABLE_ANNOUNCE_OFFERS, BTN_DISABLE_ANNOUNCE_OFFERS),
                None,
                lambda: self.handle_toggle_announce_offers(update),
            ),
            ((BTN_SHOW_POLL,), None, lambda: self.show_games_with_polls(update)),
            ((BTN_BACK,), None, lambda: self.show_main_menu(update)),
            ((BTN_ADMIN_GAMES,), ACCESS_GAMES, lambda: self.show_admin_games_menu(update)),
            ((BTN_ADMIN_POLLS,), ACCESS_GAMES, lambda: self.show_admin_polls_menu(update)),
            ((BTN_ADD_GAME,), ACCESS_GAMES, lambda: self.start_add_game(update, context, False)),
            ((BTN_ADD_FESTIVAL,), ACCESS_GAMES, lambda: self.start_add_game(update, context, True)),
            ((BTN_EDIT_GAME,), ACCESS_GAMES, lambda: self.show_games_for_edit(update)),
            ((BTN_CREATE_POLL,), ACCESS_GAMES, lambda: self.show_games_for_poll(update)),
            ((BTN_ALL_TOURNAMENTS,), ACCESS_GAMES, lambda: self.show_tournaments(update)),
            ((BTN_LEGIONARY,), ACCESS_GAMES, lambda: self.legionary(update)),
            ((BTN_ADMIN_PLAYERS,), ACCESS_ADMIN, lambda: self.show_admin_players_menu(update)),
            ((BTN_LINK_PLAYER,), ACCESS_ADMIN, lambda: self.show_players_for_add(update)),
            ((BTN_MANAGE_RIGHTS,), ACCESS_ADMIN, lambda: self.start_manage_rights(update, context)),
        )

    async def _deny_state_access(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        tg_id: int,
        kind: str,
        state: str,
    ) -> None:
        logger.warning(
            "Пользователь %s попытался использовать %s-состояние %s",
            tg_id,
            kind,
            state,
        )
        await update.message.reply_text("Недостаточно прав.")
        await self.reset_keyboard_and_state(update, context)

    async def text_handler(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ):
        if update.message is None or update.effective_chat.type != "private":
            return

        text = update.message.text
        tg_id = update.effective_user.id
        state = context.user_data.get("state", STATE_NONE)

        logger.info(f"{tg_id}: {state} | {text}")

        if state in ADMIN_STATES and not self.db.is_admin(tg_id):
            await self._deny_state_access(update, context, tg_id, "админ", state)
            return

        if state in BASE_STATES and not self.can_manage_games(tg_id):
            await self._deny_state_access(update, context, tg_id, "игр", state)
            return

        state_handler = self._state_handlers().get(state)
        if state_handler is not None:
            await state_handler(update, context)
            return

        is_admin = self.db.is_admin(tg_id)
        can_manage_games = self.can_manage_games(tg_id)
        for buttons, need, action in self._menu_actions(update, context):
            if text not in buttons:
                continue
            if need == ACCESS_GAMES and not can_manage_games:
                break
            if need == ACCESS_ADMIN and not is_admin:
                break
            await action()
            return

        await update.message.reply_text(
            with_start_hint("Неизвестная команда.")
        )

    def can_manage_games(self, tg_id: int) -> bool:
        return self.db.is_admin(tg_id) or self.db.is_base(tg_id)

    async def show_main_menu(self, update: Update):
        tg_id = update.effective_user.id
        is_admin = self.db.is_admin(tg_id)
        is_base = self.db.is_base(tg_id)

        if update.message:
            await update.message.reply_text(
                "Выберите действие:",
                reply_markup=self.main_keyboard(is_admin, is_base),
            )
        elif update.callback_query:
            await update.callback_query.message.reply_text(
                "Выберите действие:",
                reply_markup=self.main_keyboard(is_admin, is_base),
            )

    async def show_admin_games_menu(self, update: Update):
        await update.message.reply_text(
            "Игры:",
            reply_markup=self.admin_games_keyboard(),
        )

    async def show_admin_polls_menu(self, update: Update):
        await update.message.reply_text(
            "Опросы:",
            reply_markup=self.admin_polls_keyboard(),
        )

    async def show_admin_players_menu(self, update: Update):
        await update.message.reply_text(
            "Игроки:",
            reply_markup=self.admin_player_keyboard(),
        )

    def _callback_handlers(self):
        return {
            PLAYERS_CALLBACK: lambda query, update, context, value: (
                self.show_players_for_game(query, value)
            ),
            EDIT_GAME_CALLBACK: lambda query, update, context, value: (
                self.show_edit_game_menu(query, value)
            ),
            EDIT_PLACE_CALLBACK: lambda query, update, context, value: (
                self.start_edit_place(query, context, value)
            ),
            EDIT_DATE_CALLBACK: lambda query, update, context, value: (
                self.start_edit_date(query, context, value)
            ),
            EDIT_DELETE_CALLBACK: lambda query, update, context, value: (
                self.start_edit_delete(query, context, value)
            ),
            POLL_CALLBACK: lambda query, update, context, value: (
                self.create_or_forward_poll(query, update, context, value)
            ),
            ADD_PLAYER_CALLBACK: lambda query, update, context, value: (
                self.ask_link_player_id(query, context, value)
            ),
            LINK_SUGGEST_CALLBACK: lambda query, update, context, value: (
                self.confirm_link_player_by_id(query.message, context, value)
            ),
            SHOW_POLL_CALLBACK: lambda query, update, context, value: (
                self.show_poll(query, context.bot, value)
            ),
            LEGIONARY_CALLBACK: lambda query, update, context, value: (
                self.create_msg_for_legionary_chat(query, context, value)
            ),
            RIGHTS_CALLBACK: lambda query, update, context, value: (
                self.handle_rights_player_callback(query, context, value)
            ),
        }

    async def _deny_callback(self, query, tg_id: int, reason: str) -> None:
        logger.warning(
            "Пользователь %s вызвал callback без прав: %s",
            tg_id,
            reason,
        )
        await query.answer("Недостаточно прав.", show_alert=True)

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

        callback_cmd, payload = parts[0], parts[1]
        tg_id = update.effective_user.id

        if callback_cmd in ADMIN_CALLBACKS and not self.db.is_admin(tg_id):
            await self._deny_callback(query, tg_id, callback_cmd)
            return

        if callback_cmd in BASE_CALLBACKS and not self.can_manage_games(tg_id):
            await self._deny_callback(query, tg_id, callback_cmd)
            return

        if callback_cmd == ANNOUNCE_OFFER_CALLBACK:
            if not self.db.can_receive_announce_offers(tg_id):
                await self._deny_callback(query, tg_id, callback_cmd)
                return
            await query.answer()
            await self.announces.handle_callback(query, context, parts)
            return

        try:
            value = int(payload)
        except ValueError:
            await query.answer()
            return

        if callback_cmd in (SHOW_POLL_CALLBACK, PLAYERS_CALLBACK):
            if not self.db.can_view_game_poll(tg_id, value):
                await self._deny_callback(
                    query,
                    tg_id,
                    f"{callback_cmd}:{value}",
                )
                return

        handler = self._callback_handlers().get(callback_cmd)
        if handler is None:
            await query.answer()
            return

        await query.answer()
        await handler(query, update, context, value)

    async def _post_init(self, application: Application) -> None:
        self.announces.schedule(application)
        self.schedule_all_game_reminders(application)
        self.schedule_pending_roster_broke_checks(application)
        self.schedule_all_poll_unpins(application)

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
