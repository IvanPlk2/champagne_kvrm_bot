import logging
import httpx
from datetime import datetime, timedelta
from typing import Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, ContextTypes

from const import (
    ANNOUNCE_OFFER_CALLBACK,
    MSK_TZ,
    WEEK_ANNOUNCE_PAGE_URL,
    AnnounceOfferStatus,
)
from rating_api import RatingAPI
from sqlite_db import SqliteDB
from utils import (
    add_months,
    format_msk_window,
    is_datetime_in_rating_window,
)
from week_announces import (
    extract_channel_messages,
    match_event_to_existing_game,
    match_event_to_tournament,
    normalize_announce_name,
    parse_sync_list,
    select_latest_sync_list,
)

logger = logging.getLogger(__name__)

WEEK_ANNOUNCE_POLL_SECONDS = 5 * 60
WEEK_ANNOUNCE_JOB_NAME = "week_announces"


class AnnounceOffers:
    def __init__(self, db, rating_api: RatingAPI):
        self.db: SqliteDB = db
        self.rating_api: RatingAPI = rating_api
        self.httpx_client = httpx.AsyncClient(
            timeout=10
        )

    async def close(self):
        await self.httpx_client.aclose()

    def schedule(self, application: Application) -> None:
        job_queue = application.job_queue
        if job_queue is None:
            logger.error("JobQueue недоступен, опрос анонсов не запланирован")
            return
        if job_queue.get_jobs_by_name(WEEK_ANNOUNCE_JOB_NAME):
            return
        job_queue.run_repeating(
            self.poll_week_announces,
            interval=WEEK_ANNOUNCE_POLL_SECONDS,
            first=15,
            name=WEEK_ANNOUNCE_JOB_NAME,
        )

    def _tournament_button_label(self, tournament: dict, used: set[str]) -> str:
        name = tournament.get("name") or str(tournament.get("id") or "")
        label = name[:64]
        if label in used:
            suffix = f" [{tournament.get('id')}]"
            label = (name[: max(0, 64 - len(suffix))] + suffix)[:64]
        return label or str(tournament.get("id"))

    def _announce_offer_keyboard(self, offer_id: int) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "Добавить?",
                    callback_data=f"{ANNOUNCE_OFFER_CALLBACK}:add:{offer_id}",
                ),
            ]
        ])

    def _announce_confirm_keyboard(self, offer_id: int) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "Да",
                    callback_data=f"{ANNOUNCE_OFFER_CALLBACK}:yes:{offer_id}",
                ),
            ]
        ])

    def _announce_pick_keyboard(
        self,
        offer_id: int,
        tournaments: list[dict],
    ) -> InlineKeyboardMarkup:
        used: set[str] = set()
        rows = []
        for tournament in tournaments[:8]:
            label = self._tournament_button_label(tournament, used)
            used.add(label)
            rows.append([
                InlineKeyboardButton(
                    label,
                    callback_data=(
                        f"{ANNOUNCE_OFFER_CALLBACK}:pick:{offer_id}:"
                        f"{tournament['id']}"
                    ),
                )
            ])
        return InlineKeyboardMarkup(rows)

    def _format_announce_offer_text(self, event: dict) -> str:
        when_text = event["date_start"].strftime("%d.%m.%y %H:%M")
        lines = [
            "Новый анонс из @WeekChgkSPB",
            "",
            event["name"],
            event["place"],
            when_text,
        ]
        if event.get("price"):
            lines.append(event["price"])
        return "\n".join(lines)

    def _format_announce_confirm_text(self, offer: dict, tournament: dict) -> str:
        when_text = offer["date_start"].strftime("%d.%m.%y %H:%M")
        name = tournament.get("name") or offer["name"]
        return "\n".join([
            name,
            offer["place"] or "",
            when_text,
            "",
            "Добавить турнир?",
        ])

    def _event_is_future(self, event: dict) -> bool:
        now = datetime.now(MSK_TZ).replace(tzinfo=None)
        return event["date_start"] >= now

    def _tournament_covers_event(self, tournament: dict, event_when: datetime) -> bool:
        return is_datetime_in_rating_window(
            event_when,
            tournament.get("date_start"),
            tournament.get("date_end"),
        )

    def _tracked_announce_names(self) -> set[str]:
        names = self.db.get_announce_offer_names((
            AnnounceOfferStatus.OFFERED,
            AnnounceOfferStatus.ADDED,
        ))
        return {
            normalize_announce_name(name)
            for name in names
            if normalize_announce_name(name)
        }

    async def _clear_announce_button(self, query, offer_id: int) -> None:
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            logger.debug(
                "Не удалось убрать кнопку анонса %s",
                offer_id,
                exc_info=True,
            )

    async def read_announce_page(self) -> httpx.Response:
        response: httpx.Response = await self.httpx_client.get(
                WEEK_ANNOUNCE_PAGE_URL,
                headers={"User-Agent": "Mozilla/5.0 (compatible; KvrmBot/1.0)"},
                follow_redirects=True,
        )
        response.raise_for_status()
        return response

    async def poll_week_announces(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        try:
            response = await self.read_announce_page()
        except Exception:
            logger.exception("Не удалось получить ленту @WeekChgkSPB")
            return

        list_text = select_latest_sync_list(
            extract_channel_messages(response.text)
        )
        if not list_text:
            logger.warning("В ленте @WeekChgkSPB нет списка синхронов")
            return

        events = [
            event for event in parse_sync_list(list_text)
            if self._event_is_future(event)
        ]
        if not events:
            return

        seed_mode = not self.db.has_announce_offers()
        recipients = [] if seed_mode else self.db.get_announce_offer_admin_tg_ids()
        existing_games = self.db.get_games_for_announce_match()
        tracked_names = self._tracked_announce_names()
        sent = 0

        for event in events:
            known = self.db.get_announce_offer_by_fingerprint(event["fingerprint"])
            if known:
                continue

            existing = match_event_to_existing_game(event, existing_games)
            name_key = normalize_announce_name(event["name"])
            already_named = bool(name_key) and name_key in tracked_names

            if existing:
                self.db.add_announce_offer(
                    event["fingerprint"],
                    existing["base_id"],
                    event["name"],
                    event["place"],
                    event["date_start"],
                    event.get("price") or "",
                    AnnounceOfferStatus.ADDED,
                )
                if name_key:
                    tracked_names.add(name_key)
                continue

            should_mail = (
                not seed_mode
                and bool(recipients)
                and not already_named
            )
            status = (
                AnnounceOfferStatus.OFFERED
                if should_mail
                else AnnounceOfferStatus.IGNORED
            )
            offer = self.db.add_announce_offer(
                event["fingerprint"],
                None,
                event["name"],
                event["place"],
                event["date_start"],
                event.get("price") or "",
                status,
            )
            if offer is None:
                continue
            if name_key:
                tracked_names.add(name_key)
            if status != AnnounceOfferStatus.OFFERED:
                continue

            text = self._format_announce_offer_text(event)
            keyboard = self._announce_offer_keyboard(offer["id"])
            for tg_id in recipients:
                try:
                    await context.bot.send_message(
                        chat_id=tg_id,
                        text=text,
                        reply_markup=keyboard,
                    )
                    sent += 1
                except Exception:
                    logger.exception(
                        "Не удалось отправить анонс %s админу %s",
                        event["fingerprint"],
                        tg_id,
                    )

        if seed_mode:
            logger.info(
                "Первый опрос @WeekChgkSPB: запомнено %s анонсов без рассылки",
                len(events),
            )
        elif sent:
            logger.info("Разослано предложений по анонсам: %s", sent)

    async def handle_callback(self, query, context: ContextTypes.DEFAULT_TYPE, parts: list[str]) -> None:
        if len(parts) < 3:
            return
        try:
            offer_id = int(parts[2])
        except ValueError:
            return
        tournament_id = None
        if len(parts) >= 4:
            try:
                tournament_id = int(parts[3])
            except ValueError:
                return
        await self.handle_announce_offer_callback(
            query,
            context,
            parts[1],
            offer_id,
            tournament_id,
        )

    async def handle_announce_offer_callback(
        self,
        query,
        context: ContextTypes.DEFAULT_TYPE,
        action: str,
        offer_id: int,
        tournament_id: Optional[int] = None,
    ) -> None:
        offer = self.db.get_announce_offer(offer_id)
        if offer is None:
            await query.edit_message_text("Анонс уже неактуален.")
            return

        if action == "add":
            await self.search_announce_offer_tournament(query, offer)
            return

        if action == "pick":
            if tournament_id is None:
                return
            await self.propose_announce_offer_tournament(query, offer, tournament_id)
            return

        if action == "yes":
            await self.add_game_from_announce_offer(query, offer)
            return

    async def search_announce_offer_tournament(self, query, offer: dict) -> None:
        if offer["status"] == AnnounceOfferStatus.ADDED:
            await query.edit_message_text("Игра уже добавлена.")
            return

        today = datetime.now(MSK_TZ).date()
        event_day = offer["date_start"].date() if offer.get("date_start") else today
        date_end_to = add_months(today, 1)
        if event_day > date_end_to:
            date_end_to = event_day + timedelta(days=7)

        try:
            tournaments = await self.rating_api.list_synchrons(
                date_end_from=today,
                date_end_to=date_end_to,
                name=offer["name"],
                items_per_page=100,
            )
            if not tournaments:
                tournaments = await self.rating_api.match_by_long_name(
                    today,
                    date_end_to,
                    offer["name"],
                )
        except Exception:
            logger.exception(
                "Не удалось найти турнир по анонсу %s",
                offer["fingerprint"],
            )
            await self._clear_announce_button(query, offer["id"])
            await query.message.reply_text("Не удалось найти турнир на сайте рейтинга.")
            return

        tournaments = [
            item for item in tournaments
            if item.get("id") is not None and not item.get("is_festival")
        ]
        if not tournaments:
            await self._clear_announce_button(query, offer["id"])
            await query.message.reply_text("Турнир на сайте рейтинга не найден.")
            return

        covering = [
            item for item in tournaments
            if self._tournament_covers_event(item, offer["date_start"])
        ]
        candidates = covering or tournaments
        matched = None
        if len(candidates) == 1:
            matched = candidates[0]
        else:
            matched = match_event_to_tournament(
                offer,
                candidates,
                self._tournament_covers_event,
            )

        if matched:
            await self.propose_announce_offer_tournament(
                query,
                offer,
                matched["id"],
                tournament=matched,
            )
            return

        await query.message.reply_text(
            "Нашлось несколько турниров. Выберите:",
            reply_markup=self._announce_pick_keyboard(offer["id"], candidates),
        )

    async def propose_announce_offer_tournament(
        self,
        query,
        offer: dict,
        tournament_id: int,
        tournament: Optional[dict] = None,
    ) -> None:
        existing = self.db.get_game(tournament_id)
        self.db.set_announce_offer_tournament(offer["id"], tournament_id)
        offer = self.db.get_announce_offer(offer["id"]) or offer

        if existing or offer["status"] == AnnounceOfferStatus.ADDED:
            self.db.set_announce_offers_status_for_tournament(
                tournament_id,
                AnnounceOfferStatus.ADDED,
            )
            await self._clear_announce_button(query, offer["id"])
            await query.message.reply_text("Игра уже добавлена.")
            return

        if tournament is None:
            try:
                tournament = await self.rating_api.get_tournament(tournament_id)
            except Exception:
                logger.exception(
                    "Не удалось получить турнир %s для анонса",
                    tournament_id,
                )
                await self._clear_announce_button(query, offer["id"])
                await query.message.reply_text(
                    "Не удалось получить информацию о турнире."
                )
                return

        if tournament.get("is_festival"):
            await self._clear_announce_button(query, offer["id"])
            await query.message.reply_text(
                "Это фестиваль. Добавьте его через «Добавить фестиваль»."
            )
            return

        if offer.get("date_start") and not is_datetime_in_rating_window(
            offer["date_start"],
            tournament.get("date_start"),
            tournament.get("date_end"),
        ):
            window = format_msk_window(
                tournament.get("date_start"),
                tournament.get("date_end"),
            ) or "не указан"
            await query.message.reply_text(
                "Дата из анонса не входит в сроки турнира "
                f"({window}, GMT+3).\n"
                "Добавьте игру вручную."
            )
            return

        await self._clear_announce_button(query, offer["id"])
        await query.message.reply_text(
            self._format_announce_confirm_text(offer, tournament),
            reply_markup=self._announce_confirm_keyboard(offer["id"]),
        )

    async def add_game_from_announce_offer(self, query, offer: dict) -> None:
        fresh = self.db.get_announce_offer(offer["id"])
        if fresh:
            offer = fresh
        tournament_id = offer.get("tournament_id")
        if tournament_id is None:
            await query.edit_message_text(
                (query.message.text or "")
                + "\n\nСначала найдите турнир кнопкой «Добавить?»."
            )
            return

        existing = self.db.get_game(tournament_id)
        if existing or offer["status"] == AnnounceOfferStatus.ADDED:
            self.db.set_announce_offers_status_for_tournament(
                tournament_id,
                AnnounceOfferStatus.ADDED,
            )
            await query.edit_message_text("Игра уже добавлена.")
            return

        try:
            rating_data = await self.rating_api.get_tournament(tournament_id)
        except Exception:
            logger.exception(
                "Не удалось получить турнир %s для анонса",
                tournament_id,
            )
            await query.edit_message_text(
                "Не удалось получить информацию о турнире."
            )
            return

        if rating_data.get("is_festival"):
            await query.edit_message_text(
                "Это фестиваль. Добавьте его через «Добавить фестиваль»."
            )
            return

        date_start = offer["date_start"]
        if not is_datetime_in_rating_window(
            date_start,
            rating_data.get("date_start"),
            rating_data.get("date_end"),
        ):
            window = format_msk_window(
                rating_data.get("date_start"),
                rating_data.get("date_end"),
            ) or "не указан"
            await query.edit_message_text(
                "Дата из анонса не входит в сроки турнира "
                f"({window}, GMT+3).\n"
                "Добавьте игру вручную."
            )
            return

        tg_id = query.from_user.id
        added = self.db.add_game(
            tournament_id,
            rating_data.get("name") or offer["name"],
            tg_id,
            offer["place"],
            date_start,
            rating_data.get("difficulty_level"),
        )
        if not added:
            if self.db.get_game(tournament_id):
                self.db.set_announce_offers_status_for_tournament(
                    tournament_id,
                    AnnounceOfferStatus.ADDED,
                )
                await query.edit_message_text("Игра уже добавлена.")
                return
            await query.edit_message_text("Не удалось добавить игру.")
            return

        self.db.set_announce_offers_status_for_tournament(
            tournament_id,
            AnnounceOfferStatus.ADDED,
        )
        when_text = date_start.strftime("%d.%m.%y %H:%M")
        await query.edit_message_text(
            "Игра добавлена.\n"
            f"{rating_data.get('name') or offer['name']}\n"
            f"{offer['place']}\n"
            f"{when_text}"
        )
