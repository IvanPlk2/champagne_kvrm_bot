from telegram import Update


class SettingsHandlers:
    def _player_settings(self, tg_id: int) -> dict:
        return self.db.get_player_settings(tg_id) or {
            "is_base": False,
            "enable_notifications": True,
            "enable_announce_offers": False,
        }

    async def show_settings_menu(self, update: Update, text: str = "Настройки:"):
        tg_id = update.effective_user.id
        settings = self._player_settings(tg_id)
        await update.message.reply_text(
            text,
            reply_markup=self.settings_keyboard(
                settings["enable_notifications"],
                settings["is_base"],
                settings["enable_announce_offers"],
            ),
        )

    async def handle_toggle_notifications(self, update: Update):
        tg_id = update.effective_user.id
        settings = self._player_settings(tg_id)
        new_value = not settings["enable_notifications"]
        self.db.set_enable_notifications(tg_id, new_value)
        if new_value:
            await self.show_settings_menu(update, "Уведомления включены.")
        else:
            await self.show_settings_menu(update, "Уведомления выключены.")

    async def handle_toggle_announce_offers(self, update: Update):
        tg_id = update.effective_user.id
        settings = self._player_settings(tg_id)
        if not settings["is_base"]:
            await update.message.reply_text("Недостаточно прав.")
            await self.show_settings_menu(update)
            return

        new_value = not settings["enable_announce_offers"]
        self.db.set_enable_announce_offers(tg_id, new_value)
        if new_value:
            await self.show_settings_menu(update, "Подписка на анонсы включена.")
        else:
            await self.show_settings_menu(update, "Подписка на анонсы выключена.")
