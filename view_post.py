from aiogram import Router
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
import supabase_db
from __init__ import TEXTS
import json

router = Router()

@router.message(Command("view"))
async def cmd_view_post(message: Message):
    """Просмотр поста по ID"""
    user_id = message.from_user.id
    user = supabase_db.db.get_user(user_id)
    lang = user.get("language", "ru") if user else "ru"
    
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer(
            "❌ **Использование команды**\n\n"
            "`/view <ID поста>`\n\n"
            "Пример: `/view 123`",
            parse_mode="Markdown"
        )
        return
    
    try:
        post_id = int(args[1])
    except ValueError:
        await message.answer("❌ ID поста должен быть числом")
        return
    
    # Получаем пост
    post = supabase_db.db.get_post(post_id)
    if not post:
        await message.answer(f"❌ Пост #{post_id} не найден")
        return
    
    # Проверяем доступ
    if not supabase_db.db.is_user_in_project(user_id, post.get("project_id", -1)):
        await message.answer("❌ У вас нет доступа к этому посту")
        return
    
    # Получаем информацию о канале
    channel = supabase_db.db.get_channel(post.get("channel_id"))
    
    # Отправляем превью поста
    await send_post_preview(message, post, channel)
    
    # Отправляем информацию о посте
    info_text = f"📋 **Информация о посте #{post_id}**\n\n"
    
    if channel:
        info_text += f"**Канал:** {channel['name']}\n"
    
    if post.get("published"):
        info_text += "**Статус:** ✅ Опубликован\n"
    elif post.get("draft"):
        info_text += "**Статус:** 📝 Черновик\n"
    elif post.get("publish_time"):
        info_text += f"**Статус:** ⏰ Запланирован на {post['publish_time']}\n"
    
    if post.get("format"):
        info_text += f"**Формат:** {post['format']}\n"
    
    if post.get("repeat_interval") and post["repeat_interval"] > 0:
        info_text += f"**Повтор:** каждые {format_interval(post['repeat_interval'])}\n"
    
    info_text += f"\n**Команды:**\n"
    
    if not post.get("published"):
        info_text += f"• `/edit {post_id}` - редактировать\n"
        info_text += f"• `/publish {post_id}` - опубликовать сейчас\n"
        info_text += f"• `/reschedule {post_id} YYYY-MM-DD HH:MM` - перенести\n"
        info_text += f"• `/delete {post_id}` - удалить\n"
    
    info_text += f"• `/list` - список всех постов"
    
    await message.answer(info_text, parse_mode="Markdown")

async def send_post_preview(message: Message, post: dict, channel: dict = None):
    """Отправить превью поста"""
    text = post.get("text", "")
    media_id = post.get("media_id")
    media_type = post.get("media_type")
    format_type = post.get("format")
    buttons = post.get("buttons")
    
    # Определяем parse_mode
    parse_mode = None
    if format_type:
        if format_type.lower() == "markdown":
            parse_mode = "Markdown"
        elif format_type.lower() == "html":
            parse_mode = "HTML"
    
    # Подготовка кнопок
    markup = None
    if buttons:
        try:
            if isinstance(buttons, str):
                buttons_list = json.loads(buttons)
            else:
                buttons_list = buttons
            
            if buttons_list:
                kb = []
                for btn in buttons_list:
                    if isinstance(btn, dict) and btn.get("text") and btn.get("url"):
                        kb.append([InlineKeyboardButton(text=btn["text"], url=btn["url"])])
                if kb:
                    markup = InlineKeyboardMarkup(inline_keyboard=kb)
        except:
            pass
    
    # Отправка превью
    try:
        if media_id and media_type:
            if media_type.lower() == "photo":
                await message.answer_photo(
                    media_id,
                    caption=text or "📝 *Пост без текста*",
                    parse_mode=parse_mode or "Markdown",
                    reply_markup=markup
                )
            elif media_type.lower() == "video":
                await message.answer_video(
                    media_id,
                    caption=text or "📝 *Пост без текста*",
                    parse_mode=parse_mode or "Markdown",
                    reply_markup=markup
                )
            elif media_type.lower() == "animation":
                await message.answer_animation(
                    media_id,
                    caption=text or "📝 *Пост без текста*",
                    parse_mode=parse_mode or "Markdown",
                    reply_markup=markup
                )
        else:
            await message.answer(
                text or "📝 *Пост без текста*",
                parse_mode=parse_mode or "Markdown",
                reply_markup=markup
            )
    except Exception as e:
        await message.answer(
            f"⚠️ **Ошибка предпросмотра**\n\n"
            f"Не удалось показать превью: {str(e)}\n\n"
            f"Проверьте форматирование текста.",
            parse_mode="Markdown"
        )

def format_interval(seconds: int) -> str:
    """Форматировать интервал в человекочитаемый вид"""
    if seconds % 86400 == 0:
        days = seconds // 86400
        return f"{days} дн." if days != 1 else "день"
    elif seconds % 3600 == 0:
        hours = seconds // 3600
        return f"{hours} ч." if hours != 1 else "час"
    else:
        minutes = seconds // 60
        return f"{minutes} мин." if minutes != 1 else "минуту"

@router.message(Command("publish"))
async def cmd_publish_now(message: Message):
    """Опубликовать пост немедленно"""
    user_id = message.from_user.id
    user = supabase_db.db.get_user(user_id)
    lang = user.get("language", "ru") if user else "ru"
    
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer(
            "❌ **Использование команды**\n\n"
            "`/publish <ID поста>`\n\n"
            "Пример: `/publish 123`",
            parse_mode="Markdown"
        )
        return
    
    try:
        post_id = int(args[1])
    except ValueError:
        await message.answer("❌ ID поста должен быть числом")
        return
    
    # Получаем пост
    post = supabase_db.db.get_post(post_id)
    if not post:
        await message.answer(f"❌ Пост #{post_id} не найден")
        return
    
    # Проверяем доступ
    if not supabase_db.db.is_user_in_project(user_id, post.get("project_id", -1)):
        await message.answer("❌ У вас нет доступа к этому посту")
        return
    
    if post.get("published"):
        await message.answer("❌ Пост уже опубликован")
        return
    
    # Обновляем время публикации на текущее
    from datetime import datetime
    from zoneinfo import ZoneInfo
    
    now = datetime.now(ZoneInfo("UTC"))
    supabase_db.db.update_post(post_id, {
        "publish_time": now,
        "draft": False
    })
    
    await message.answer(
        f"🚀 **Пост #{post_id} поставлен в очередь**\n\n"
        f"Пост будет опубликован в ближайшее время.",
        parse_mode="Markdown"
    )

@router.message(Command("reschedule"))
async def cmd_reschedule_post(message: Message):
    """Перенести публикацию поста"""
    user_id = message.from_user.id
    user = supabase_db.db.get_user(user_id)
    lang = user.get("language", "ru") if user else "ru"
    
    parts = message.text.split(maxsplit=3)
    if len(parts) < 4:
        await message.answer(
            "❌ **Использование команды**\n\n"
            "`/reschedule <ID> <YYYY-MM-DD> <HH:MM>`\n\n"
            "Пример: `/reschedule 123 2024-12-25 15:30`",
            parse_mode="Markdown"
        )
        return
    
    try:
        post_id = int(parts[1])
        date_str = parts[2]
        time_str = parts[3]
    except (ValueError, IndexError):
        await message.answer("❌ Неверный формат команды")
        return
    
    # Получаем пост
    post = supabase_db.db.get_post(post_id)
    if not post:
        await message.answer(f"❌ Пост #{post_id} не найден")
        return
    
    # Проверяем доступ
    if not supabase_db.db.is_user_in_project(user_id, post.get("project_id", -1)):
        await message.answer("❌ У вас нет доступа к этому посту")
        return
    
    if post.get("published"):
        await message.answer("❌ Нельзя перенести уже опубликованный пост")
        return
    
    # Парсим новое время
    from datetime import datetime
    from zoneinfo import ZoneInfo
    
    try:
        dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
        tz = ZoneInfo(user.get("timezone", "UTC"))
        local_dt = dt.replace(tzinfo=tz)
        utc_dt = local_dt.astimezone(ZoneInfo("UTC"))
        
        # Проверяем, что время в будущем
        if utc_dt <= datetime.now(ZoneInfo("UTC")):
            await message.answer("❌ Время должно быть в будущем")
            return
        
        # Обновляем пост
        supabase_db.db.update_post(post_id, {
            "publish_time": utc_dt,
            "draft": False,
            "notified": False
        })
        
        await message.answer(
            f"✅ **Пост #{post_id} перенесен**\n\n"
            f"Новое время публикации: {date_str} {time_str} ({user.get('timezone', 'UTC')})",
            parse_mode="Markdown"
        )
        
    except ValueError as e:
        await message.answer(
            f"❌ **Ошибка формата времени**\n\n"
            f"Используйте формат: YYYY-MM-DD HH:MM\n"
            f"Ошибка: {str(e)}",
            parse_mode="Markdown"
        )
