from datetime import timedelta, timezone
from enum import Enum


UTC_TZ = timezone.utc
MSK_TZ = timezone(timedelta(hours=3))

ANNOUNCE_OFFER_CALLBACK = "ann_offer"
WEEK_ANNOUNCE_PAGE_URL = "https://t.me/s/WeekChgkSPB"

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

BTN_ADMIN_GAMES = "Игры"
BTN_ADMIN_POLLS = "Опросы"
BTN_ADMIN_PLAYERS = "Игроки"

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

PLAYERS_CALLBACK = "players"
PLACE_CALLBACK = "place"
POLL_CALLBACK = "poll"
ADD_PLAYER_CALLBACK = "add_player"
LINK_SUGGEST_CALLBACK = "link_s"
SHOW_POLL_CALLBACK = "show_poll"
LEGIONARY_CALLBACK = "legionary"
EDIT_GAME_CALLBACK = "edit"
EDIT_PLACE_CALLBACK = "edit_place"
EDIT_DATE_CALLBACK = "edit_date"
EDIT_DELETE_CALLBACK = "edit_delete"

ADMIN_CALLBACKS = {
    PLACE_CALLBACK,
    POLL_CALLBACK,
    ADD_PLAYER_CALLBACK,
    LINK_SUGGEST_CALLBACK,
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

ROSTER_MIN_PLAYERS = 6
ROSTER_BROKE_DELAY_SECONDS = 60
ROSTER_BROKE_JOB_PREFIX = "roster_broke:"


class AnnounceOfferStatus(str, Enum):
    OFFERED = "offered"
    ADDED = "added"
    IGNORED = "ignored"
