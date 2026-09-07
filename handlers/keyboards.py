from telegram import ReplyKeyboardMarkup

from const import (
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
    BTN_NO,
    BTN_PLAYING_WITH,
    BTN_SHOW_POLL,
    BTN_TOURNAMENTS,
    BTN_YES,
    BTN_SETTINGS,
    BTN_ENABLE_NOTIFICATIONS,
    BTN_DISABLE_NOTIFICATIONS,
    BTN_ENABLE_ANNOUNCE_OFFERS,
    BTN_DISABLE_ANNOUNCE_OFFERS,
)


class KeyboardMixin:
    def main_keyboard(self, is_admin: bool, is_base: bool):
        buttons = [
            [BTN_TOURNAMENTS],
            [BTN_PLAYING_WITH],
        ]

        if is_admin or is_base:
            buttons.extend([
                [BTN_ADMIN_POLLS],
                [BTN_ADMIN_GAMES],
            ])
        else:
            buttons.append([BTN_SHOW_POLL])

        if is_admin:
            buttons.append([BTN_ADMIN_PLAYERS])

        buttons.append([BTN_SETTINGS])

        return ReplyKeyboardMarkup(
            buttons,
            resize_keyboard=True,
        )

    def settings_keyboard(
        self,
        enable_notifications: bool,
        is_base: bool,
        enable_announce_offers: bool,
    ):
        buttons = [[
            BTN_DISABLE_NOTIFICATIONS
            if enable_notifications
            else BTN_ENABLE_NOTIFICATIONS
        ]]

        if is_base:
            buttons.append([
                BTN_DISABLE_ANNOUNCE_OFFERS
                if enable_announce_offers
                else BTN_ENABLE_ANNOUNCE_OFFERS
            ])

        buttons.append([BTN_BACK])
        return ReplyKeyboardMarkup(
            buttons,
            resize_keyboard=True,
        )

    def admin_games_keyboard(self):
        return ReplyKeyboardMarkup(
            [
                [BTN_ADD_GAME],
                [BTN_ADD_FESTIVAL],
                [BTN_EDIT_GAME],
                [BTN_ALL_TOURNAMENTS],
                [BTN_BACK],
            ],
            resize_keyboard=True,
        )

    def admin_polls_keyboard(self):
        return ReplyKeyboardMarkup(
            [
                [BTN_CREATE_POLL],
                [BTN_SHOW_POLL],
                [BTN_BACK],
            ],
            resize_keyboard=True,
        )

    def admin_player_keyboard(self):
        return ReplyKeyboardMarkup(
            [
                [BTN_LINK_PLAYER],
                [BTN_LEGIONARY],
                [BTN_BACK],
            ],
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
