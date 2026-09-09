import logging
from typing import Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from config import SUPER_ADMIN, TEAM_ID, TEAM_LINK, TEAM_NAME
from const import (
    ADD_PLAYER_CALLBACK,
    BTN_ADD_TO_BASE,
    BTN_BACK,
    BTN_GRANT_ADMIN,
    BTN_NO,
    BTN_PICK_PLAYER_BY_ID,
    BTN_REMOVE_FROM_BASE,
    BTN_REVOKE_ADMIN,
    BTN_YES,
    LEGIONARY_CALLBACK,
    LINK_SUGGEST_CALLBACK,
    PLAYERS_CALLBACK,
    RIGHTS_ACTION_ADD_BASE,
    RIGHTS_ACTION_GRANT_ADMIN,
    RIGHTS_ACTION_REMOVE_BASE,
    RIGHTS_ACTION_REVOKE_ADMIN,
    RIGHTS_CALLBACK,
    STATE_ADD_PLAYER_CONFIRM,
    STATE_ADD_PLAYER_RATING_ID,
    STATE_NONE,
    STATE_RIGHTS_ACTIONS,
    STATE_RIGHTS_CONFIRM,
    STATE_RIGHTS_PICK_BASE_ID,
    STATE_RIGHTS_SELECT,
)
from utils import get_when_text, with_start_hint

logger = logging.getLogger(__name__)


class PlayerHandlers:
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
                with_start_hint("ID рейтинга должен быть числом.")
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
                with_start_hint("Выберите Да или Нет."),
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

    def _player_rights_label(self, player: dict) -> str:
        name = " ".join(
            x for x in [player.get("surname"), player.get("name")]
            if x
        ).strip()
        return name or str(player["base_id"])

    def _is_protected_admin(self, player: dict) -> bool:
        if SUPER_ADMIN is None:
            return False
        return player.get("base_id") == SUPER_ADMIN

    def _rights_players_keyboard(self, players: list[dict]):
        used_labels: set[str] = set()
        keyboard = []
        for player in players:
            name = self._player_rights_label(player)
            label = name[:64]
            if label in used_labels:
                suffix = f" [{player['base_id']}]"
                label = (name[: max(0, 64 - len(suffix))] + suffix)[:64]
            used_labels.add(label)
            keyboard.append([
                InlineKeyboardButton(
                    text=label,
                    callback_data=f"{RIGHTS_CALLBACK}:{player['base_id']}",
                )
            ])
        return InlineKeyboardMarkup(keyboard) if keyboard else None

    async def start_manage_rights(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data["state"] = STATE_RIGHTS_SELECT
        context.user_data.pop("rights_base_id", None)
        context.user_data.pop("rights_action", None)

        players = self.db.get_recent_past_game_players(5)
        keyboard = self._rights_players_keyboard(players)

        await update.message.reply_text(
            "Выберите игрока или укажите его ID:",
            reply_markup=self.rights_select_keyboard(),
        )
        if keyboard:
            await update.message.reply_text(
                "Игроки за 5 последних игр:",
                reply_markup=keyboard,
            )

    async def ask_rights_player_id(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data["state"] = STATE_RIGHTS_PICK_BASE_ID
        await update.message.reply_text(
            "Введите ID игрока:",
            reply_markup=self.back_keyboard(),
        )

    async def show_rights_actions(
        self,
        message,
        context: ContextTypes.DEFAULT_TYPE,
        base_id: int,
        text: Optional[str] = None,
    ):
        player = self.db.get_player_by_base_id(base_id)
        if player is None:
            await message.reply_text("Игрок с таким ID не найден.")
            return False

        context.user_data["rights_base_id"] = base_id
        context.user_data["state"] = STATE_RIGHTS_ACTIONS
        context.user_data.pop("rights_action", None)

        label = self._player_rights_label(player)
        prompt = text or f"Игрок: {label}"
        await message.reply_text(
            prompt,
            reply_markup=self.rights_actions_keyboard(
                player["is_admin"],
                player["is_base"],
                self._is_protected_admin(player),
            ),
        )
        return True

    def _rights_confirm_prompt(self, action: str, label: str) -> str:
        if action == RIGHTS_ACTION_GRANT_ADMIN:
            return f"Дать права админа игроку {label}?"
        if action == RIGHTS_ACTION_REVOKE_ADMIN:
            return f"Забрать права админа у игрока {label}?"
        if action == RIGHTS_ACTION_ADD_BASE:
            return f"Добавить игрока {label} в базу?"
        return f"Исключить игрока {label} из базы?"

    async def start_rights_confirm(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        action: str,
    ):
        base_id = context.user_data.get("rights_base_id")
        player = self.db.get_player_by_base_id(base_id) if base_id is not None else None
        if player is None:
            await update.message.reply_text("Сначала выберите игрока.")
            await self.start_manage_rights(update, context)
            return

        if action == RIGHTS_ACTION_REVOKE_ADMIN and self._is_protected_admin(player):
            await update.message.reply_text(
                "Нельзя забрать права админа у суперадмина."
            )
            await self.show_rights_actions(update.message, context, player["base_id"])
            return

        context.user_data["rights_action"] = action
        context.user_data["state"] = STATE_RIGHTS_CONFIRM
        await update.message.reply_text(
            self._rights_confirm_prompt(action, self._player_rights_label(player)),
            reply_markup=self.yes_no_keyboard(),
        )

    async def handle_rights_select(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ):
        text = update.message.text
        if text == BTN_BACK:
            context.user_data["state"] = STATE_NONE
            await self.show_admin_players_menu(update)
            return
        if text == BTN_PICK_PLAYER_BY_ID:
            await self.ask_rights_player_id(update, context)
            return
        await update.message.reply_text(
            with_start_hint(
                "Выберите игрока на клавиатуре или укажите его ID."
            ),
            reply_markup=self.rights_select_keyboard(),
        )

    async def handle_rights_pick_base_id(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ):
        text = (update.message.text or "").strip()
        if text == BTN_BACK:
            await self.start_manage_rights(update, context)
            return

        try:
            base_id = int(text)
        except ValueError:
            await update.message.reply_text(
                with_start_hint("ID игрока должен быть числом.")
            )
            return

        found = await self.show_rights_actions(update.message, context, base_id)
        if not found:
            return

    async def handle_rights_actions(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ):
        text = update.message.text
        if text == BTN_BACK:
            await self.start_manage_rights(update, context)
            return
        if text == BTN_GRANT_ADMIN:
            await self.start_rights_confirm(update, context, RIGHTS_ACTION_GRANT_ADMIN)
            return
        if text == BTN_REVOKE_ADMIN:
            await self.start_rights_confirm(update, context, RIGHTS_ACTION_REVOKE_ADMIN)
            return
        if text == BTN_ADD_TO_BASE:
            await self.start_rights_confirm(update, context, RIGHTS_ACTION_ADD_BASE)
            return
        if text == BTN_REMOVE_FROM_BASE:
            await self.start_rights_confirm(update, context, RIGHTS_ACTION_REMOVE_BASE)
            return

        await update.message.reply_text(
            with_start_hint("Выберите действие.")
        )

    async def handle_rights_confirm(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ):
        text = update.message.text
        base_id = context.user_data.get("rights_base_id")
        action = context.user_data.get("rights_action")

        if text == BTN_NO or text == BTN_BACK:
            if base_id is None:
                await self.start_manage_rights(update, context)
                return
            await self.show_rights_actions(update.message, context, base_id)
            return

        if text != BTN_YES:
            await update.message.reply_text(
                with_start_hint("Выберите Да или Нет."),
                reply_markup=self.yes_no_keyboard(),
            )
            return

        player = self.db.get_player_by_base_id(base_id) if base_id is not None else None
        if player is None or not action:
            await update.message.reply_text("Сначала выберите игрока.")
            await self.start_manage_rights(update, context)
            return

        if action == RIGHTS_ACTION_REVOKE_ADMIN and self._is_protected_admin(player):
            await update.message.reply_text(
                "Нельзя забрать права админа у суперадмина."
            )
            await self.show_rights_actions(update.message, context, player["base_id"])
            return

        if action == RIGHTS_ACTION_GRANT_ADMIN:
            success = self.db.set_is_admin_by_base_id(base_id, True)
            result_text = "Права админа выданы." if success else "Не удалось изменить права."
        elif action == RIGHTS_ACTION_REVOKE_ADMIN:
            success = self.db.set_is_admin_by_base_id(base_id, False)
            result_text = "Права админа сняты." if success else "Не удалось изменить права."
        elif action == RIGHTS_ACTION_ADD_BASE:
            success = self.db.set_is_base_by_base_id(base_id, True)
            result_text = "Игрок добавлен в базу." if success else "Не удалось изменить права."
        else:
            success = self.db.set_is_base_by_base_id(base_id, False)
            result_text = "Игрок исключён из базы." if success else "Не удалось изменить права."

        logger.info(
            "%s изменил права игрока %s: %s (%s)",
            update.effective_user.id,
            base_id,
            action,
            success,
        )
        await self.show_rights_actions(
            update.message,
            context,
            base_id,
            result_text,
        )

    async def handle_rights_player_callback(
        self,
        query,
        context: ContextTypes.DEFAULT_TYPE,
        base_id: int,
    ):
        await self.show_rights_actions(query.message, context, base_id)

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
