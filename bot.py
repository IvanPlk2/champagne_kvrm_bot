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
    PLACE_CALLBACK,
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
            logger.warning(
                "Пользователь %s попытался использовать админ-состояние %s",
                tg_id,
                state,
            )
            await update.message.reply_text("Недостаточно прав.")
            await self.reset_keyboard_and_state(update, context)
            return

        if state in BASE_STATES and not self.can_manage_games(tg_id):
            logger.warning(
                "Пользователь %s попытался использовать состояние игр %s",
                tg_id,
                state,
            )
            await update.message.reply_text("Недостаточно прав.")
            await self.reset_keyboard_and_state(update, context)
            return

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

        if state == STATE_ADD_GAME_CREATE_POLL:
            await self.handle_add_game_create_poll(update, context)
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

        if state == STATE_RIGHTS_SELECT:
            await self.handle_rights_select(update, context)
            return

        if state == STATE_RIGHTS_PICK_BASE_ID:
            await self.handle_rights_pick_base_id(update, context)
            return

        if state == STATE_RIGHTS_ACTIONS:
            await self.handle_rights_actions(update, context)
            return

        if state == STATE_RIGHTS_CONFIRM:
            await self.handle_rights_confirm(update, context)
            return

        is_admin = self.db.is_admin(tg_id)
        can_manage_games = self.can_manage_games(tg_id)

        if text == BTN_TOURNAMENTS:
            await self.show_my_tournaments(update)
            return

        if text == BTN_PLAYING_WITH:
            await self.show_tournaments_for_players(update)
            return

        if text == BTN_SETTINGS:
            await self.show_settings_menu(update)
            return

        if text in (BTN_ENABLE_NOTIFICATIONS, BTN_DISABLE_NOTIFICATIONS):
            await self.handle_toggle_notifications(update)
            return

        if text in (BTN_ENABLE_ANNOUNCE_OFFERS, BTN_DISABLE_ANNOUNCE_OFFERS):
            await self.handle_toggle_announce_offers(update)
            return

        if can_manage_games and text == BTN_ADMIN_GAMES:
            await self.show_admin_games_menu(update)
            return

        if can_manage_games and text == BTN_ADMIN_POLLS:
            await self.show_admin_polls_menu(update)
            return

        if is_admin and text == BTN_ADMIN_PLAYERS:
            await self.show_admin_players_menu(update)
            return

        if can_manage_games and text == BTN_ADD_GAME:
            await self.start_add_game(update, context, False)
            return

        if can_manage_games and text == BTN_ADD_FESTIVAL:
            await self.start_add_game(update, context, True)
            return

        if can_manage_games and text == BTN_EDIT_GAME:
            await self.show_games_for_edit(update)
            return

        if can_manage_games and text == BTN_CREATE_POLL:
            await self.show_games_for_poll(update)
            return

        if text == BTN_SHOW_POLL:
            await self.show_games_with_polls(update)
            return

        if is_admin and text == BTN_LINK_PLAYER:
            await self.show_players_for_add(update)
            return

        if is_admin and text == BTN_MANAGE_RIGHTS:
            await self.start_manage_rights(update, context)
            return

        if can_manage_games and text == BTN_ALL_TOURNAMENTS:
            await self.show_tournaments(update)
            return

        if is_admin and text == BTN_LEGIONARY:
            await self.legionary(update)
            return

        if text == BTN_BACK:
            await self.show_main_menu(update)
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
        if callback_cmd in BASE_CALLBACKS and not self.can_manage_games(tg_id):
            logger.warning(
                "Пользователь %s вызвал callback игр %s",
                tg_id,
                callback_cmd,
            )
            await query.answer("Недостаточно прав.", show_alert=True)
            return
        elif callback_cmd in (SHOW_POLL_CALLBACK, PLAYERS_CALLBACK):
            try:
                game_id = int(text)
            except ValueError:
                await query.answer()
                return
            if not self.db.can_view_game_poll(tg_id, game_id):
                logger.warning(
                    "Пользователь %s запросил чужие данные игры %s (%s)",
                    tg_id,
                    game_id,
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
            await self.show_players_for_game(query, int(text))
            return

        if callback_cmd == PLACE_CALLBACK:
            await self.start_edit_place(query, context, int(text))
            return

        if callback_cmd == EDIT_GAME_CALLBACK:
            await self.show_edit_game_menu(query, int(text))
            return

        if callback_cmd == EDIT_PLACE_CALLBACK:
            await self.start_edit_place(query, context, int(text))
            return

        if callback_cmd == EDIT_DATE_CALLBACK:
            await self.start_edit_date(query, context, int(text))
            return

        if callback_cmd == EDIT_DELETE_CALLBACK:
            await self.start_edit_delete(query, context, int(text))
            return

        if callback_cmd == POLL_CALLBACK:
            await self.create_or_forward_poll(
                query, update, context, int(text)
            )
            return

        if callback_cmd == ADD_PLAYER_CALLBACK:
            await self.ask_link_player_id(query, context, int(text))
            return

        if callback_cmd == LINK_SUGGEST_CALLBACK:
            await self.confirm_link_player_by_id(
                query.message, context, int(text)
            )
            return

        if callback_cmd == SHOW_POLL_CALLBACK:
            await self.show_poll(query, context.bot, int(text))
            return

        if callback_cmd == LEGIONARY_CALLBACK:
            await self.create_msg_for_legionary_chat(
                query, context, int(text)
            )
            return

        if callback_cmd == RIGHTS_CALLBACK:
            try:
                rights_base_id = int(text)
            except ValueError:
                return
            await self.handle_rights_player_callback(query, context, rights_base_id)
            return

        if callback_cmd == ANNOUNCE_OFFER_CALLBACK:
            await self.announces.handle_callback(query, context, parts)
            return

    async def _post_init(self, application: Application) -> None:
        self.announces.schedule(application)
        self.schedule_all_game_reminders(application)
        self.schedule_pending_roster_broke_checks(application)

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
