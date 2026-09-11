from datetime import timedelta, timezone
from enum import Enum


UTC_TZ = timezone.utc
MSK_TZ = timezone(timedelta(hours=3))

ANNOUNCE_OFFER_CALLBACK = "ann_offer"
WEEK_ANNOUNCE_PAGE_URL = "https://t.me/s/WeekChgkSPB"

BTN_TOURNAMENTS = "Показать мои турниры"
BTN_PLAYING_WITH = "Посмотреть с кем играю"
BTN_VIEW_ROSTER = "Посмотреть состав"

BTN_ADD_GAME = "Добавить игру"
BTN_ADD_FESTIVAL = "Добавить фестиваль"
BTN_EDIT_GAME = "Редактировать игру"
BTN_CREATE_POLL = "Создать опрос"
BTN_SHOW_POLL = "Показать опрос"
BTN_LINK_PLAYER = "Привязать к рейтингу"
BTN_MANAGE_RIGHTS = "Изменить права"
BTN_PICK_PLAYER_BY_ID = "Указать ID игрока"
BTN_GRANT_ADMIN = "Дать права админа"
BTN_REVOKE_ADMIN = "Забрать права админа"
BTN_ADD_TO_BASE = "Добавить в базу"
BTN_REMOVE_FROM_BASE = "Исключить из базы"
BTN_ALL_TOURNAMENTS = "Показать турниры"
BTN_LEGIONARY = "Создать сообщение для легчата"

BTN_ADMIN_GAMES = "Игры"
BTN_ADMIN_POLLS = "Опросы"
BTN_ADMIN_PLAYERS = "Игроки"

BTN_SETTINGS = "Настройки"
BTN_ENABLE_NOTIFICATIONS = "Включить уведомления"
BTN_DISABLE_NOTIFICATIONS = "Выключить уведомления"
BTN_ENABLE_ANNOUNCE_OFFERS = "Включить подписку на анонсы"
BTN_DISABLE_ANNOUNCE_OFFERS = "Выключить подписку на анонсы"

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
STATE_ADD_GAME_CREATE_POLL = "add_game_create_poll"

STATE_UPDATE_PLACE = "update_place"
STATE_EDIT_DATE = "edit_date"
STATE_EDIT_DELETE_CONFIRM = "edit_delete_confirm"

STATE_ADD_PLAYER_RATING_ID = "add_player_rating_id"
STATE_ADD_PLAYER_CONFIRM = "add_player_confirm"
STATE_RIGHTS_SELECT = "rights_select"
STATE_RIGHTS_PICK_BASE_ID = "rights_pick_base_id"
STATE_RIGHTS_ACTIONS = "rights_actions"
STATE_RIGHTS_CONFIRM = "rights_confirm"

RIGHTS_ACTION_GRANT_ADMIN = "grant_admin"
RIGHTS_ACTION_REVOKE_ADMIN = "revoke_admin"
RIGHTS_ACTION_ADD_BASE = "add_base"
RIGHTS_ACTION_REMOVE_BASE = "remove_base"

PLAYERS_CALLBACK = "players"
POLL_CALLBACK = "poll"
ADD_PLAYER_CALLBACK = "add_player"
LINK_SUGGEST_CALLBACK = "link_s"
SHOW_POLL_CALLBACK = "show_poll"
LEGIONARY_CALLBACK = "legionary"
RIGHTS_CALLBACK = "rights"
EDIT_GAME_CALLBACK = "edit"
EDIT_PLACE_CALLBACK = "edit_place"
EDIT_DATE_CALLBACK = "edit_date"
EDIT_DELETE_CALLBACK = "edit_delete"

BASE_CALLBACKS = {
    POLL_CALLBACK,
    EDIT_GAME_CALLBACK,
    EDIT_PLACE_CALLBACK,
    EDIT_DATE_CALLBACK,
    EDIT_DELETE_CALLBACK,
    LEGIONARY_CALLBACK,
}

ADMIN_CALLBACKS = {
    ADD_PLAYER_CALLBACK,
    LINK_SUGGEST_CALLBACK,
    RIGHTS_CALLBACK,
}

BASE_STATES = {
    STATE_ADD_GAME_SELECT,
    STATE_ADD_GAME_SEARCH_NAME,
    STATE_ADD_GAME_ID,
    STATE_ADD_GAME_CONFIRM,
    STATE_ADD_GAME_PLACE,
    STATE_ADD_GAME_DATE_START,
    STATE_ADD_GAME_DATE_END,
    STATE_ADD_GAME_CREATE_POLL,
    STATE_UPDATE_PLACE,
    STATE_EDIT_DATE,
    STATE_EDIT_DELETE_CONFIRM,
}

ADMIN_STATES = {
    STATE_ADD_PLAYER_RATING_ID,
    STATE_ADD_PLAYER_CONFIRM,
    STATE_RIGHTS_SELECT,
    STATE_RIGHTS_PICK_BASE_ID,
    STATE_RIGHTS_ACTIONS,
    STATE_RIGHTS_CONFIRM,
}

ACCESS_GAMES = "games"
ACCESS_ADMIN = "admin"

ROSTER_MIN_PLAYERS = 6
ROSTER_BROKE_DELAY_SECONDS = 60
ROSTER_BROKE_JOB_PREFIX = "roster_broke:"
GAME_REMIND_DAY_JOB_PREFIX = "game_remind_day:"
GAME_REMIND_HOUR_JOB_PREFIX = "game_remind_hour:"
POLL_UNPIN_JOB_PREFIX = "poll_unpin:"
POLL_UNPIN_HOUR = 10

HINT_RESET_KEYBOARD = "Сбросить клавиатуру можно командой /start."


class AnnounceOfferStatus(str, Enum):
    OFFERED = "offered"
    ADDED = "added"
    IGNORED = "ignored"
