# db.py
import os
from typing import List, Optional, Dict
from uuid import UUID
from datetime import datetime

from supabase import create_client, Client

# ============================
# Инициализация Supabase-клиента
# ============================
SUPABASE_URL: str = os.getenv("SUPABASE_URL")
SUPABASE_KEY: str = os.getenv("SUPABASE_KEY")
if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("SUPABASE_URL и SUPABASE_KEY должны быть заданы в окружении")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


# ----------------------------
# Пользователи (users)
# ----------------------------
def get_user(telegram_id: int) -> Optional[Dict]:
    """
    Возвращает dict-представление пользователя по telegram_id или None, если не найден.
    """
    resp = supabase.table("users").select("*").eq("telegram_id", telegram_id).limit(1).execute()
    data = resp.data
    return data[0] if data else None


def create_user(telegram_id: int, timezone: str = "UTC") -> Dict:
    """
    Создаёт нового пользователя с указанным часовым поясом.
    Возвращает вставленную запись.
    """
    resp = supabase.table("users").insert(
        {"telegram_id": telegram_id, "timezone": timezone}
    ).execute()
    return resp.data[0]


def set_user_timezone(telegram_id: int, timezone: str) -> None:
    """
    Обновляет у пользователя timezone.
    """
    supabase.table("users").update({"timezone": timezone}).eq("telegram_id", telegram_id).execute()


# ----------------------------
# Каналы (channels)
# ----------------------------
def add_channel(user_id: UUID, channel_id: int, title: str) -> Dict:
    """
    Добавляет канал в таблицу channels для данного пользователя.
    Возвращает вставленную запись.
    """
    resp = supabase.table("channels").insert(
        {
            "user_id": str(user_id),
            "channel_id": channel_id,
            "title": title,
            "is_active": True
        }
    ).execute()
    return resp.data[0]


def remove_channel(user_id: UUID, channel_id: int) -> None:
    """
    Помечает канал как is_active = False.
    (Логику удаления из связанных постов оставляем на бизнес‐логику в бот/планировщик.)
    """
    supabase.table("channels").update(
        {"is_active": False}
    ).eq("user_id", str(user_id)).eq("channel_id", channel_id).execute()


def list_channels(user_id: UUID) -> List[Dict]:
    """
    Возвращает список активных каналов (is_active = True) пользователя.
    """
    resp = supabase.table("channels").select("*") \
        .eq("user_id", str(user_id)).eq("is_active", True).execute()
    return resp.data or []


# ----------------------------
# Посты (posts)
# ----------------------------
def create_post_draft(user_id: UUID) -> UUID:
    """
    Создаёт черновик (status='draft') и возвращает сгенерированный UUID.
    """
    resp = supabase.table("posts").insert({
        "user_id": str(user_id),
        "status": "draft",
        "text": None,
        "has_media": False,
        "media_ids": [],
        "buttons": [],
        "type_schedule": None,
        "one_time_ts_utc": None,
        "cron_rule": None,
        "channels": [],
        "delete_rule": None,
        "next_run_at": None,
        "task_id_pub": None,
        "task_id_del": None
    }).execute()
    return UUID(resp.data[0]["id"])


def update_post_text(post_id: UUID, text: str) -> None:
    """
    Обновляет поле text у поста (черновика или запланированного).
    """
    supabase.table("posts").update({"text": text}).eq("id", str(post_id)).execute()


def update_post_media(post_id: UUID, media_list: List[str]) -> None:
    """
    Сохраняет массив media_list (JSONB) и устанавливает has_media = True/False.
    """
    has_media = len(media_list) > 0
    supabase.table("posts").update({
        "media_ids": media_list,
        "has_media": has_media
    }).eq("id", str(post_id)).execute()


def update_post_channels(post_id: UUID, channels: List[int]) -> None:
    """
    Сохраняет JSONB-массив каналов (channel_id).
    """
    supabase.table("posts").update({"channels": channels}).eq("id", str(post_id)).execute()


def update_post_buttons(post_id: UUID, buttons: List[Dict]) -> None:
    """
    Сохраняет JSONB-массив кнопок вида [{"text": "...", "url": "..."}, ...].
    """
    supabase.table("posts").update({"buttons": buttons}).eq("id", str(post_id)).execute()


def set_post_schedule_one_time(post_id: UUID, ts_utc: datetime) -> None:
    """
    Устанавливает расписание одноразовой публикации:
      type_schedule='one_time'
      one_time_ts_utc = ts_utc
      cron_rule = NULL
    """
    supabase.table("posts").update({
        "type_schedule": "one_time",
        "one_time_ts_utc": ts_utc,
        "cron_rule": None
    }).eq("id", str(post_id)).execute()


def set_post_schedule_cron(
    post_id: UUID,
    cron_rule: str
) -> None:
    """
    Сохраняет cron_rule (строка, например "0 15 * * *") и выставляет type_schedule.
    (Даты начала/окончания фактически будут учтены при регистрации CronTrigger в планировщике.)
    """
    supabase.table("posts").update({
        "type_schedule": "cron",
        "cron_rule": cron_rule,
        "one_time_ts_utc": None
    }).eq("id", str(post_id)).execute()


def set_post_delete_rule(post_id: UUID, delete_rule: Dict) -> None:
    """
    Сохраняет JSONB‐объект delete_rule:
      { "type": "never" }
      { "type": "after_N", "value": <seconds> }
      { "type": "at_time", "value": <ISO8601 UTC‐строка> }
    """
    supabase.table("posts").update({"delete_rule": delete_rule}).eq("id", str(post_id)).execute()


def get_scheduled_posts(user_id: UUID) -> List[Dict]:
    """
    Возвращает все посты со статусом 'scheduled' данного пользователя.
    """
    resp = supabase.table("posts").select("*") \
        .eq("user_id", str(user_id)).eq("status", "scheduled").execute()
    return resp.data or []


def cancel_post(post_id: UUID) -> None:
    """
    Помечает пост как 'cancelled'. Задачи из APScheduler нужно снимать отдельно.
    """
    supabase.table("posts").update({"status": "cancelled"}).eq("id", str(post_id)).execute()


def get_post(post_id: UUID) -> Optional[Dict]:
    """
    Возвращает запись поста (словарь) по его UUID, если существует.
    """
    resp = supabase.table("posts").select("*").eq("id", str(post_id)).limit(1).execute()
    data = resp.data
    return data[0] if data else None


def list_draft_posts(user_id: UUID) -> List[Dict]:
    """
    Возвращает все черновики (status='draft') данного пользователя.
    """
    resp = supabase.table("posts").select("*") \
        .eq("user_id", str(user_id)).eq("status", "draft").execute()
    return resp.data or []


def mark_post_sent(post_id: UUID, posted_messages: List[Dict]) -> None:
    """
    После успешной публикации:
    - Помечаем статус 'sent' и next_run_at = NULL (за исключение циклических, там обновляется отдельно).
    - Вставляем в таблицу posted_messages пару (post_id, channel_id, message_id) для каждой отправки.
    """
    # Обновляем статус поста
    supabase.table("posts").update({
        "status": "sent",
        "next_run_at": None
    }).eq("id", str(post_id)).execute()

    # Вставляем записи в posted_messages
    for pm in posted_messages:
        supabase.table("posted_messages").insert({
            "post_id": str(post_id),
            "channel_id": pm["channel_id"],
            "message_id": pm["message_id"]
        }).execute()


def mark_post_cancelled(post_id: UUID) -> None:
    """
    Альтернативная обёртка для cancel_post.
    """
    cancel_post(post_id)


# ----------------------------
# Записи отправленных сообщений (posted_messages)
# ----------------------------
def save_posted_message(post_id: UUID, channel_id: int, message_id: int) -> None:
    """
    Сохраняет одну запись о том, что пост отправлен в канал: (post_id, channel_id, message_id).
    """
    supabase.table("posted_messages").insert({
        "post_id": str(post_id),
        "channel_id": channel_id,
        "message_id": message_id
    }).execute()


def get_posted_messages(post_id: UUID) -> List[Dict]:
    """
    Возвращает все записи из posted_messages для данного post_id.
    """
    resp = supabase.table("posted_messages").select("*").eq("post_id", str(post_id)).execute()
    return resp.data or []


def delete_posted_messages_records(post_id: UUID) -> None:
    """
    Удаляет все записи из posted_messages, связанные с post_id.
    """
    supabase.table("posted_messages").delete().eq("post_id", str(post_id)).execute()
