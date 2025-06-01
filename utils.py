# utils.py

import os
import re
import pytz
from datetime import datetime
from typing import Optional, List, Tuple
from pathlib import Path
import aiofiles

from aiogram import Bot, types
from aiogram.types import ChatMember

# ----------------------------
# Константы
# ----------------------------
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 МБ
ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.mp4', '.gif', '.pdf'}


# ----------------------------
# Проверка валидности таймзоны
# ----------------------------
def is_valid_timezone(tz_str: str) -> bool:
    return tz_str in pytz.all_timezones


# ----------------------------
# Парсинг локальной даты "ДД.ММ.ГГГГ ЧЧ:ММ"
# ----------------------------
def parse_datetime_local(text: str, tz_str: str) -> Optional[datetime]:
    """
    Парсит строку "ДД.MM.YYYY HH:MM" в локальный datetime с tzinfo=tz_str.
    Если формат неверный или tz_str некорректен, возвращает None.
    """
    try:
        dt_naive = datetime.strptime(text, "%d.%m.%Y %H:%M")
    except ValueError:
        return None

    try:
        tz = pytz.timezone(tz_str)
    except pytz.UnknownTimeZoneError:
        return None

    dt_local = tz.localize(dt_naive)
    return dt_local


# ----------------------------
# Конвертация локального datetime → UTC
# ----------------------------
def to_utc(dt_local: datetime) -> datetime:
    """
    Переводит локальный datetime (с tzinfo) в UTC.
    """
    return dt_local.astimezone(pytz.UTC)


# ----------------------------
# Проверка, что локальный datetime уже в будущем
# ----------------------------
def is_future_datetime(dt_local: datetime) -> bool:
    """
    Сравнивает dt_local (с tzinfo) с текущим моментом в той же TZ.
    """
    now_local = datetime.now(pytz.timezone(dt_local.tzinfo.zone))
    return dt_local > now_local


# ----------------------------
# Проверка валидности медиа (photo, video, document)
# ----------------------------
def validate_media(message: types.Message) -> bool:
    """
    Проверяет, что сообщение содержит photo/video/document, 
    размер ≤20 МБ, расширение допустимо.
    """
    # Фото
    if message.photo:
        largest_photo = message.photo[-1]
        return bool(largest_photo.file_size and largest_photo.file_size <= MAX_FILE_SIZE)

    # Видео
    if message.video:
        video = message.video
        if video.file_size and video.file_size <= MAX_FILE_SIZE:
            ext = os.path.splitext(video.file_name or "")[1].lower()
            return (ext in ALLOWED_EXTENSIONS) or (video.file_name is None)
        return False

    # Документы (pdf, gif и т. д.)
    if message.document:
        doc = message.document
        if doc.file_size and doc.file_size <= MAX_FILE_SIZE:
            ext = os.path.splitext(doc.file_name or "")[1].lower()
            return ext in ALLOWED_EXTENSIONS
        return False

    return False  # Если нет подходящего медиа


# ----------------------------
# Асинхронная проверка, что пользователь и бот администраторы в канале
# ----------------------------
async def check_admin_rights(bot: Bot, chat_id: int, user_id: int) -> bool:
    """
    Проверяет через get_chat_member, что пользователь имеет статус administrator или creator,
    и бот тоже – и имеет право post сообщений (can_post_messages) в этом канале.
    """
    try:
        member_user: ChatMember = await bot.get_chat_member(chat_id, user_id)
        member_bot: ChatMember = await bot.get_chat_member(chat_id, (await bot.get_me()).id)

        # Проверяем статус пользователя
        if member_user.status not in {"administrator", "creator"}:
            return False

        # Проверяем статус бота
        if member_bot.status not in {"administrator", "creator"}:
            return False

        # Если есть атрибут can_post_messages у бота, проверяем, что он True
        if hasattr(member_bot, "can_post_messages") and member_bot.can_post_messages is False:
            return False

        return True
    except Exception:
        return False


# ----------------------------
# Локальное хранилище медиа: папка media/<post_id>/
# ----------------------------
def ensure_media_dir(post_id: str) -> Path:
    """
    Создаёт (если нужно) папку media/<post_id>/ и возвращает Path к ней.
    """
    base_dir = Path("media") / post_id
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir


async def save_file_locally(message: types.Message, post_id: str) -> Optional[str]:
    """
    Скачивает файл из Telegram и сохраняет в папку media/<post_id>/. 
    Возвращает путь к сохранённому файлу или None, если не удалось.
    """
    file_id = None
    original_filename = None

    if message.photo:
        file_id = message.photo[-1].file_id
        original_filename = f"{file_id}.jpg"
    elif message.video:
        file_id = message.video.file_id
        original_filename = message.video.file_name or f"{file_id}.mp4"
    elif message.document:
        file_id = message.document.file_id
        original_filename = message.document.file_name
    else:
        return None

    if not file_id or not original_filename:
        return None

    file_obj = await message.bot.get_file(file_id)
    file_path = file_obj.file_path
    file_bytes = await message.bot.download_file(file_path)

    dir_path = ensure_media_dir(post_id)
    save_path = dir_path / original_filename

    async with aiofiles.open(save_path, mode="wb") as f:
        await f.write(file_bytes.read())

    return str(save_path)


def upload_media_for_post(post_id: str) -> List[str]:
    """
    Загружает все файлы из media/<post_id>/ в Supabase Storage (бакет 'media').
    Возвращает список public URL для каждого файла.
    """
    from db import supabase

    dir_path = ensure_media_dir(post_id)
    uploaded_paths: List[str] = []

    for file_path in dir_path.iterdir():
        if file_path.is_file():
            key = f"{post_id}/{file_path.name}"
            with open(file_path, "rb") as file_data:
                supabase.storage.from_("media").upload(key, file_data)
                public_url = supabase.storage.from_("media").get_public_url(key).get("publicURL")
                uploaded_paths.append(public_url)

    return uploaded_paths


# ----------------------------
# Формирование kwargs для CronTrigger
# ----------------------------
def extract_cron_kwargs(
    schedule_type: str,
    time_str: str,
    days: Optional[List[str]] = None,
    day_of_month: Optional[int] = None,
    month_and_day: Optional[Tuple[int, int]] = None
) -> dict:
    """
    Формирует словарь для CronTrigger:
      - daily: time_str = 'HH:MM'
      - weekly: days = ['mon','wed'], time_str='HH:MM'
      - monthly: day_of_month=15, time_str='HH:MM'
      - yearly: month_and_day=(12,25), time_str='HH:MM'
    """
    hh, mm = map(int, time_str.split(":"))
    cron_kwargs = {"hour": hh, "minute": mm}

    if schedule_type == "daily":
        return cron_kwargs

    if schedule_type == "weekly":
        cron_kwargs["day_of_week"] = ",".join(days or [])
        return cron_kwargs

    if schedule_type == "monthly":
        cron_kwargs["day"] = day_of_month
        return cron_kwargs

    if schedule_type == "yearly":
        month, day = month_and_day or (None, None)
        cron_kwargs["month"] = month
        cron_kwargs["day"] = day
        return cron_kwargs

    return cron_kwargs
