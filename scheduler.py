# scheduler.py

import os
import pytz
import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.cron import CronTrigger
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore

from aiogram import Bot
from aiogram.utils.exceptions import TelegramAPIError

from db import (
    get_post,
    mark_post_sent,
    save_posted_message,
    get_posted_messages,
    delete_posted_messages_records,
)
from utils import to_utc, extract_cron_kwargs

# ============================
# Логирование APScheduler
# ============================
logging.basicConfig()
logging.getLogger('apscheduler').setLevel(logging.INFO)

# ============================
# Переменные окружения
# ============================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN не задан в окружении")

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL должен быть задан для SQLAlchemyJobStore")

# ============================
# Инициализация Telegram Bot и Scheduler
# ============================
bot = Bot(token=TELEGRAM_BOT_TOKEN)
jobstores = {
    'default': SQLAlchemyJobStore(url=DATABASE_URL)
}
scheduler = AsyncIOScheduler(jobstores=jobstores, timezone=pytz.UTC)
scheduler.start()


# ----------------------------
# Планирование «одноразовой» публикации
# ----------------------------
def schedule_one_time(post_id: str, run_date_utc: datetime) -> str:
    """
    Планирует одноразовый запуск publish_post(post_id) в UTC‐времени run_date_utc.
    Возвращает job.id.
    """
    trigger = DateTrigger(run_date=run_date_utc, timezone=pytz.UTC)
    job = scheduler.add_job(publish_post, trigger=trigger, args=[post_id], id=f"{post_id}_pub")
    return job.id


# ----------------------------
# Планирование «cron» (циклический) запуск
# ----------------------------
def schedule_cron(
    post_id: str,
    schedule_type: str,
    time_str: str,
    days=None,
    day_of_month=None,
    month_and_day=None,
    start_date_local=None,
    end_date_local=None,
):
    """
    Создаёт CronTrigger для publish_post(post_id) по типу расписания:
      - schedule_type: "daily", "weekly", "monthly", "yearly"
      - time_str: "HH:MM"
      - days: список сокращённых дней ['mon','wed'] (только для weekly)
      - day_of_month: integer (только для monthly)
      - month_and_day: (month:int, day:int) (только для yearly)
      - start_date_local, end_date_local: локальные datetime-с tzinfo пользователя
    Возвращает job.id.
    """
    cron_kwargs = extract_cron_kwargs(schedule_type, time_str, days, day_of_month, month_and_day)

    utc_start = to_utc(start_date_local) if start_date_local else None
    utc_end = to_utc(end_date_local) if end_date_local else None

    trigger = CronTrigger(
        timezone=pytz.UTC,
        **cron_kwargs,
        start_date=utc_start,
        end_date=utc_end
    )
    job = scheduler.add_job(publish_post, trigger=trigger, args=[post_id], id=f"{post_id}_pub")
    return job.id


# ----------------------------
# Планирование «одноразового» удаления
# ----------------------------
def schedule_delete(post_id: str, run_date_utc: datetime) -> str:
    """
    Планирует одноразовый запуск delete_post(post_id) в UTC‐времени run_date_utc.
    Возвращает job.id.
    """
    trigger = DateTrigger(run_date=run_date_utc, timezone=pytz.UTC)
    job = scheduler.add_job(delete_post, trigger=trigger, args=[post_id], id=f"{post_id}_del")
    return job.id


# ----------------------------
# Удаление задачи (по её ID)
# ----------------------------
def remove_job(job_id: str) -> None:
    """
    Удаляет задачу из планировщика, если она там есть.
    """
    try:
        scheduler.remove_job(job_id)
    except Exception:
        pass  # Если задачи нет или уже удалена, просто игнорируем


# ----------------------------
# Функция публикации поста
# ----------------------------
async def publish_post(post_id: str):
    """
    Берёт из БД post_id, извлекает:
      - channels (список chat_id)
      - text
      - media_ids (список URL)
      - buttons (список {"text":..., "url":...})
      - delete_rule
      - type_schedule (строка 'one_time' или 'cron')
    Отправляет в каждый канал (media + text + кнопки).
    Сохраняет в таблицу posted_messages каждую пару (channel_id, message_id).
    Обновляет статус поста в 'sent'. Для циклов – обновляет next_run_at.
    Если delete_rule лежит в БД, проставляет задачу на удаление.
    """
    post = get_post(post_id)
    if not post:
        return  # Пост удалён или не найден

    channels = post.get("channels") or []
    text = post.get("text") or ""
    media_ids = post.get("media_ids") or []
    buttons = post.get("buttons") or []
    delete_rule = post.get("delete_rule") or {"type": "never"}
    schedule_type = post.get("type_schedule")

    posted_messages = []

    # Формируем InlineKeyboard, если есть кнопки
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    keyboard = None
    if buttons:
        keyboard = InlineKeyboardMarkup(row_width=1)
        for btn in buttons:
            keyboard.add(InlineKeyboardButton(text=btn["text"], url=btn["url"]))

    # Отправляем в каждый канал
    for chat_id in channels:
        try:
            if media_ids:
                # Если все медиа – изображения, и их >1, отправляем media_group
                image_exts = {".jpg", ".jpeg", ".png", ".gif"}
                if (len(media_ids) > 1
                        and all(str(url).lower().endswith(tuple(image_exts)) for url in media_ids)):
                    from aiogram.types import InputMediaPhoto
                    media_group = [InputMediaPhoto(media=url) for url in media_ids]
                    # Прикрепляем текст к первому элементу, если он есть
                    if text:
                        media_group[0].caption = text
                        media_group[0].parse_mode = "HTML"
                    sent_msgs = await bot.send_media_group(chat_id=int(chat_id), media=media_group)
                    for msg in sent_msgs:
                        posted_messages.append({
                            "channel_id": int(chat_id),
                            "message_id": msg.message_id
                        })
                    # Если есть кнопки, отправляем отдельно
                    if keyboard:
                        msg_btn = await bot.send_message(chat_id=int(chat_id), text=" ", reply_markup=keyboard)
                        posted_messages.append({
                            "channel_id": int(chat_id),
                            "message_id": msg_btn.message_id
                        })
                else:
                    # Отправляем каждое медиа по отдельности
                    for idx, url in enumerate(media_ids):
                        lower = str(url).lower()
                        if lower.endswith((".jpg", ".jpeg", ".png", ".gif")):
                            if idx == 0 and text:
                                msg = await bot.send_photo(
                                    chat_id=int(chat_id),
                                    photo=url,
                                    caption=text,
                                    parse_mode="HTML",
                                    reply_markup=(keyboard if not media_ids or idx != 0 else None)
                                )
                            else:
                                msg = await bot.send_photo(chat_id=int(chat_id), photo=url)
                            posted_messages.append({
                                "channel_id": int(chat_id),
                                "message_id": msg.message_id
                            })
                        elif lower.endswith(".mp4"):
                            if idx == 0 and text:
                                msg = await bot.send_video(
                                    chat_id=int(chat_id),
                                    video=url,
                                    caption=text,
                                    parse_mode="HTML"
                                )
                            else:
                                msg = await bot.send_video(chat_id=int(chat_id), video=url)
                            posted_messages.append({
                                "channel_id": int(chat_id),
                                "message_id": msg.message_id
                            })
                        elif lower.endswith(".pdf"):
                            if idx == 0 and text:
                                msg = await bot.send_document(
                                    chat_id=int(chat_id),
                                    document=url,
                                    caption=text,
                                    parse_mode="HTML"
                                )
                            else:
                                msg = await bot.send_document(chat_id=int(chat_id), document=url)
                            posted_messages.append({
                                "channel_id": int(chat_id),
                                "message_id": msg.message_id
                            })
                        else:
                            # Попробуем как документ
                            if idx == 0 and text:
                                msg = await bot.send_document(
                                    chat_id=int(chat_id),
                                    document=url,
                                    caption=text,
                                    parse_mode="HTML"
                                )
                            else:
                                msg = await bot.send_document(chat_id=int(chat_id), document=url)
                            posted_messages.append({
                                "channel_id": int(chat_id),
                                "message_id": msg.message_id
                            })
                    # Если не было текста на первом медиа, но текст всё равно есть – отправляем отдельно
                    if not media_ids and text:
                        msg_text = await bot.send_message(
                            chat_id=int(chat_id),
                            text=text,
                            parse_mode="HTML",
                            reply_markup=keyboard
                        )
                        posted_messages.append({
                            "channel_id": int(chat_id),
                            "message_id": msg_text.message_id
                        })
                    elif media_ids and not text:
                        # Если медиа было, но текста нет, а есть кнопки – отправим кнопки отдельно
                        if keyboard:
                            msg_btn = await bot.send_message(chat_id=int(chat_id), text=" ", reply_markup=keyboard)
                            posted_messages.append({
                                "channel_id": int(chat_id),
                                "message_id": msg_btn.message_id
                            })
            else:
                # Без медиа – просто текст + кнопки
                if text:
                    msg_text = await bot.send_message(
                        chat_id=int(chat_id),
                        text=text,
                        parse_mode="HTML",
                        reply_markup=keyboard
                    )
                    posted_messages.append({
                        "channel_id": int(chat_id),
                        "message_id": msg_text.message_id
                    })
        except TelegramAPIError as e:
            logging.error(f"Ошибка при отправке в канал {chat_id}: {e}")

    # Сохраняем все отправленные сообщения в БД и меняем статус поста на 'sent'
    if posted_messages:
        mark_post_sent(post_id, posted_messages)

    # Обрабатываем правило удаления (delete_rule)
    rule_type = delete_rule.get("type", "never")
    if rule_type == "after_N":
        seconds = delete_rule.get("value", 0)
        if seconds > 0:
            # Базовое время – one_time_ts_utc (если было) или now()
            base = post.get("one_time_ts_utc")
            if base:
                try:
                    base_dt = datetime.fromisoformat(base) if isinstance(base, str) else base
                    base_utc = base_dt.astimezone(pytz.UTC)
                except Exception:
                    base_utc = datetime.now(pytz.UTC)
            else:
                base_utc = datetime.now(pytz.UTC)
            run_date = base_utc + timedelta(seconds=seconds)
            schedule_delete(post_id, run_date)

    elif rule_type == "at_time":
        ts = delete_rule.get("value")
        if ts:
            try:
                run_date = datetime.fromisoformat(ts)
                if run_date.tzinfo is None:
                    run_date = pytz.UTC.localize(run_date)
            except Exception:
                run_date = None
            if run_date and run_date > datetime.now(pytz.UTC):
                schedule_delete(post_id, run_date)

    # Если циклический пост (type_schedule != "one_time"), обновляем next_run_at
    if schedule_type != "one_time":
        job = scheduler.get_job(f"{post_id}_pub")
        if job and job.next_run_time:
            from db import supabase
            supabase.table("posts").update({
                "next_run_at": job.next_run_time
            }).eq("id", post_id).execute()


# ----------------------------
# Функция удаления опубликованного поста
# ----------------------------
async def delete_post(post_id: str):
    """
    Удаляет все сообщения, отправленные ранее в каналы (по posted_messages),
    затем удаляет записи posted_messages и помечает одинарный пост как 'deleted'.
    """
    msgs = get_posted_messages(post_id)
    for record in msgs:
        chat_id = record.get("channel_id")
        message_id = record.get("message_id")
        try:
            await bot.delete_message(chat_id=int(chat_id), message_id=int(message_id))
        except TelegramAPIError as e:
            logging.error(f"Не удалось удалить сообщение {message_id} в канале {chat_id}: {e}")

    delete_posted_messages_records(post_id)

    # Если одноразовый – пометим статус 'deleted'
    post = get_post(post_id)
    if post and post.get("type_schedule") == "one_time":
        from db import supabase
        supabase.table("posts").update({"status": "deleted"}).eq("id", post_id).execute()
