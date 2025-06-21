from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import Command
import supabase_db
from __init__ import TEXTS
import json
from datetime import datetime
from zoneinfo import ZoneInfo
import html
import re

router = Router()

def format_time_for_user(time_str: str, user: dict) -> str:
    """Форматировать время для отображения пользователю в его часовом поясе"""
    try:
        # Парсим время из ISO формата
        if isinstance(time_str, str):
            if time_str.endswith('Z'):
                time_str = time_str[:-1] + '+00:00'
            utc_time = datetime.fromisoformat(time_str)
        else:
            utc_time = time_str
        
        # Получаем часовой пояс пользователя
        user_tz_name = user.get('timezone', 'UTC')
        try:
            user_tz = ZoneInfo(user_tz_name)
            local_time = utc_time.astimezone(user_tz)
        except:
            local_time = utc_time
            user_tz_name = 'UTC'
        
        # Форматируем согласно настройкам пользователя
        date_format = user.get('date_format', 'YYYY-MM-DD')
        time_format = user.get('time_format', 'HH:MM')
        
        # Конвертируем формат в strftime
        if date_format == 'DD.MM.YYYY':
            date_str = local_time.strftime('%d.%m.%Y')
        elif date_format == 'DD/MM/YYYY':
            date_str = local_time.strftime('%d/%m/%Y')
        elif date_format == 'MM/DD/YYYY':
            date_str = local_time.strftime('%m/%d/%Y')
        else:  # YYYY-MM-DD
            date_str = local_time.strftime('%Y-%m-%d')
        
        if time_format == 'hh:MM AM':
            time_str = local_time.strftime('%I:%M %p')
        else:  # HH:MM
            time_str = local_time.strftime('%H:%M')
        
        return f"{date_str} {time_str} ({user_tz_name})"
    except Exception as e:
        # Fallback на оригинальную строку
        return str(time_str)

def clean_text_for_format(text: str, parse_mode: str) -> str:
    """Очистить и подготовить текст для определенного формата"""
    if not text:
        return text
    
    if parse_mode == "Markdown":
        # Экранируем специальные символы Markdown
        # Сначала убираем HTML-теги если они есть
        text = re.sub(r'<[^>]+>', '', text)
        
        # Экранируем специальные символы Markdown v2
        special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
        for char in special_chars:
            text = text.replace(char, '\\' + char)
        
        return text
    
    elif parse_mode == "HTML":
        # Экранируем HTML символы если нет тегов
        if not re.search(r'<[^>]+>', text):
            text = html.escape(text)
        return text
    
    else:
        # Обычный текст - убираем все теги и специальные символы
        text = re.sub(r'<[^>]+>', '', text)
        return text

def get_post_management_keyboard(post_id: int, is_published: bool = False) -> InlineKeyboardMarkup:
    """Создать клавиатуру управления постом"""
    buttons = []
    
    if not is_published:
        buttons.append([
            InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"post_edit_direct:{post_id}"),
            InlineKeyboardButton(text="🚀 Опубликовать", callback_data=f"post_publish_cmd:{post_id}")
        ])
        buttons.append([
            InlineKeyboardButton(text="📅 Перенести", callback_data=f"post_reschedule_cmd:{post_id}"),
            InlineKeyboardButton(text="🗑 Удалить", callback_data=f"post_delete_cmd:{post_id}")
        ])
    
    buttons.append([
        InlineKeyboardButton(text="📋 Список постов", callback_data="posts_menu"),
        InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

@router.message(Command("view"))
async def cmd_view_post(message: Message):
    """Просмотр поста по ID"""
    user_id = message.from_user.id
    user = supabase_db.db.get_user(user_id)
    lang = user.get("language", "ru") if user else "ru"
    
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📋 Список постов", callback_data="posts_menu")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ])
        await message.answer(
            "❌ **Использование команды**\n\n"
            "`/view <ID поста>`\n\n"
            "Пример: `/view 123`",
            parse_mode="Markdown",
            reply_markup=keyboard
        )
        return
    
    try:
        post_id = int(args[1])
    except ValueError:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📋 Список постов", callback_data="posts_menu")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ])
        await message.answer("❌ ID поста должен быть числом", reply_markup=keyboard)
        return
    
    # Получаем пост
    post = supabase_db.db.get_post(post_id)
    if not post:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📋 Список постов", callback_data="posts_menu")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ])
        await message.answer(f"❌ Пост #{post_id} не найден", reply_markup=keyboard)
        return
    
    # Проверяем доступ через канал
    if not supabase_db.db.is_channel_admin(post.get("channel_id"), user_id):
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📋 Список постов", callback_data="posts_menu")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ])
        await message.answer("❌ У вас нет доступа к этому посту", reply_markup=keyboard)
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
        formatted_time = format_time_for_user(post['publish_time'], user)
        info_text += f"**Статус:** ⏰ Запланирован на {formatted_time}\n"
    
    parse_mode_value = post.get("parse_mode") or post.get("format")
    if parse_mode_value:
        info_text += f"**Формат:** {parse_mode_value}\n"
    
    if post.get("repeat_interval") and post["repeat_interval"] > 0:
        info_text += f"**Повтор:** каждые {format_interval(post['repeat_interval'])}\n"
    
    # Добавляем кнопки управления
    keyboard = get_post_management_keyboard(post_id, post.get("published", False))
    
    await message.answer(info_text, parse_mode="Markdown", reply_markup=keyboard)

async def send_post_preview(message: Message, post: dict, channel: dict = None):
    """Отправить превью поста с правильной обработкой форматирования"""
    text = post.get("text", "")
    media_id = post.get("media_id")
    media_type = post.get("media_type")
    format_type = post.get("parse_mode") or post.get("format")
    buttons = post.get("buttons")
    
    # Определяем parse_mode
    parse_mode = None
    if format_type:
        if format_type.lower() == "markdown":
            parse_mode = "Markdown"
        elif format_type.lower() == "html":
            parse_mode = "HTML"
    
    # Очищаем и подготавливаем текст для формата
    if text and parse_mode:
        try:
            cleaned_text = clean_text_for_format(text, parse_mode)
        except Exception as e:
            print(f"Error cleaning text: {e}")
            cleaned_text = text
            parse_mode = None  # Отключаем форматирование при ошибке
    else:
        cleaned_text = text
    
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
        except Exception as e:
            print(f"Error processing buttons: {e}")
            pass
    
    # Fallback text если основной пустой
    final_text = cleaned_text or "📝 *Пост без текста*"
    fallback_parse_mode = parse_mode or "Markdown"
    
    # Отправка превью
    try:
        if media_id and media_type:
            if media_type.lower() == "photo":
                await message.answer_photo(
                    media_id,
                    caption=final_text,
                    parse_mode=parse_mode,
                    reply_markup=markup
                )
            elif media_type.lower() == "video":
                await message.answer_video(
                    media_id,
                    caption=final_text,
                    parse_mode=parse_mode,
                    reply_markup=markup
                )
            elif media_type.lower() == "animation":
                await message.answer_animation(
                    media_id,
                    caption=final_text,
                    parse_mode=parse_mode,
                    reply_markup=markup
                )
        else:
            await message.answer(
                final_text,
                parse_mode=parse_mode,
                reply_markup=markup
            )
    except Exception as e:
        print(f"First attempt failed: {e}")
        # Второй попытка без форматирования
        try:
            safe_text = re.sub(r'<[^>]+>', '', text) if text else "📝 Пост без текста"
            
            if media_id and media_type:
                if media_type.lower() == "photo":
                    await message.answer_photo(
                        media_id,
                        caption=safe_text,
                        reply_markup=markup
                    )
                elif media_type.lower() == "video":
                    await message.answer_video(
                        media_id,
                        caption=safe_text,
                        reply_markup=markup
                    )
                elif media_type.lower() == "animation":
                    await message.answer_animation(
                        media_id,
                        caption=safe_text,
                        reply_markup=markup
                    )
            else:
                await message.answer(
                    safe_text,
                    reply_markup=markup
                )
        except Exception as e2:
            print(f"Second attempt failed: {e2}")
            # Последняя попытка с минимальным текстом
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📋 Список постов", callback_data="posts_menu")],
                [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
            ])
            
            error_msg = f"⚠️ **Ошибка предпросмотра**\n\nНе удалось показать превью поста из-за ошибки форматирования.\n\n**Формат:** {format_type or 'не задан'}\n**Ошибка:** {str(e)}"
            
            await message.answer(
                error_msg,
                parse_mode="Markdown",
                reply_markup=keyboard
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
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📋 Список постов", callback_data="posts_menu")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ])
        await message.answer(
            "❌ **Использование команды**\n\n"
            "`/publish <ID поста>`\n\n"
            "Пример: `/publish 123`",
            parse_mode="Markdown",
            reply_markup=keyboard
        )
        return
    
    try:
        post_id = int(args[1])
    except ValueError:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📋 Список постов", callback_data="posts_menu")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ])
        await message.answer("❌ ID поста должен быть числом", reply_markup=keyboard)
        return
    
    # Получаем пост
    post = supabase_db.db.get_post(post_id)
    if not post:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📋 Список постов", callback_data="posts_menu")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ])
        await message.answer(f"❌ Пост #{post_id} не найден", reply_markup=keyboard)
        return
    
    # Проверяем доступ через канал
    if not supabase_db.db.is_channel_admin(post.get("channel_id"), user_id):
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📋 Список постов", callback_data="posts_menu")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ])
        await message.answer("❌ У вас нет доступа к этому посту", reply_markup=keyboard)
        return
    
    if post.get("published"):
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👀 Просмотр поста", callback_data=f"post_full_view:{post_id}")],
            [InlineKeyboardButton(text="📋 Список постов", callback_data="posts_menu")]
        ])
        await message.answer("❌ Пост уже опубликован", reply_markup=keyboard)
        return
    
    # Обновляем время публикации на текущее
    now = datetime.now(ZoneInfo("UTC"))
    supabase_db.db.update_post(post_id, {
        "publish_time": now,
        "draft": False
    })
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👀 Просмотр поста", callback_data=f"post_full_view:{post_id}")],
        [InlineKeyboardButton(text="📋 Список постов", callback_data="posts_menu")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
    ])
    
    await message.answer(
        f"🚀 **Пост #{post_id} поставлен в очередь**\n\n"
        f"Пост будет опубликован в ближайшее время.",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

@router.message(Command("reschedule"))
async def cmd_reschedule_post(message: Message):
    """Перенести публикацию поста"""
    user_id = message.from_user.id
    user = supabase_db.db.get_user(user_id)
    lang = user.get("language", "ru") if user else "ru"
    
    parts = message.text.split(maxsplit=3)
    if len(parts) < 4:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📋 Список постов", callback_data="posts_menu")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ])
        await message.answer(
            "❌ **Использование команды**\n\n"
            "`/reschedule <ID> <YYYY-MM-DD> <HH:MM>`\n\n"
            "Пример: `/reschedule 123 2024-12-25 15:30`",
            parse_mode="Markdown",
            reply_markup=keyboard
        )
        return
    
    try:
        post_id = int(parts[1])
        date_str = parts[2]
        time_str = parts[3]
    except (ValueError, IndexError):
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📋 Список постов", callback_data="posts_menu")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ])
        await message.answer("❌ Неверный формат команды", reply_markup=keyboard)
        return
    
    # Получаем пост
    post = supabase_db.db.get_post(post_id)
    if not post:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📋 Список постов", callback_data="posts_menu")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ])
        await message.answer(f"❌ Пост #{post_id} не найден", reply_markup=keyboard)
        return
    
    # Проверяем доступ через канал
    if not supabase_db.db.is_channel_admin(post.get("channel_id"), user_id):
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📋 Список постов", callback_data="posts_menu")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ])
        await message.answer("❌ У вас нет доступа к этому посту", reply_markup=keyboard)
        return
    
    if post.get("published"):
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👀 Просмотр поста", callback_data=f"post_full_view:{post_id}")],
            [InlineKeyboardButton(text="📋 Список постов", callback_data="posts_menu")]
        ])
        await message.answer("❌ Нельзя перенести уже опубликованный пост", reply_markup=keyboard)
        return
    
    # Парсим новое время
    try:
        dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
        tz = ZoneInfo(user.get("timezone", "UTC"))
        local_dt = dt.replace(tzinfo=tz)
        utc_dt = local_dt.astimezone(ZoneInfo("UTC"))
        
        # Проверяем, что время в будущем
        if utc_dt <= datetime.now(ZoneInfo("UTC")):
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="👀 Просмотр поста", callback_data=f"post_full_view:{post_id}")],
                [InlineKeyboardButton(text="📋 Список постов", callback_data="posts_menu")]
            ])
            await message.answer("❌ Время должно быть в будущем", reply_markup=keyboard)
            return
        
        # Обновляем пост
        supabase_db.db.update_post(post_id, {
            "publish_time": utc_dt,
            "draft": False,
            "notified": False
        })
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👀 Просмотр поста", callback_data=f"post_full_view:{post_id}")],
            [InlineKeyboardButton(text="📋 Список постов", callback_data="posts_menu")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ])
        
        await message.answer(
            f"✅ **Пост #{post_id} перенесен**\n\n"
            f"Новое время публикации: {date_str} {time_str} ({user.get('timezone', 'UTC')})",
            parse_mode="Markdown",
            reply_markup=keyboard
        )
        
    except ValueError as e:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📋 Список постов", callback_data="posts_menu")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ])
        await message.answer(
            f"❌ **Ошибка формата времени**\n\n"
            f"Используйте формат: YYYY-MM-DD HH:MM\n"
            f"Ошибка: {str(e)}",
            parse_mode="Markdown",
            reply_markup=keyboard
        )

@router.message(Command("delete"))
async def cmd_delete_post(message: Message):
    """Удалить пост"""
    user_id = message.from_user.id
    user = supabase_db.db.get_user(user_id)
    lang = user.get("language", "ru") if user else "ru"
    
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📋 Список постов", callback_data="posts_menu")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ])
        await message.answer(
            "❌ **Использование команды**\n\n"
            "`/delete <ID поста>`\n\n"
            "Пример: `/delete 123`",
            parse_mode="Markdown",
            reply_markup=keyboard
        )
        return
    
    try:
        post_id = int(args[1])
    except ValueError:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📋 Список постов", callback_data="posts_menu")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ])
        await message.answer("❌ ID поста должен быть числом", reply_markup=keyboard)
        return
    
    # Получаем пост
    post = supabase_db.db.get_post(post_id)
    if not post:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📋 Список постов", callback_data="posts_menu")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ])
        await message.answer(f"❌ Пост #{post_id} не найден", reply_markup=keyboard)
        return
    
    # Проверяем доступ через канал
    if not supabase_db.db.is_channel_admin(post.get("channel_id"), user_id):
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📋 Список постов", callback_data="posts_menu")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ])
        await message.answer("❌ У вас нет доступа к этому посту", reply_markup=keyboard)
        return
    
    # Подтверждение удаления
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"delete_confirm:{post_id}"),
            InlineKeyboardButton(text="❌ Отмена", callback_data=f"post_full_view:{post_id}")
        ]
    ])
    
    await message.answer(
        f"🗑 **Удаление поста #{post_id}**\n\n"
        f"Вы уверены, что хотите удалить этот пост?\n"
        f"Это действие нельзя отменить.",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

# Callback для подтверждения удаления поста
@router.callback_query(F.data.startswith("delete_confirm:"))
async def callback_confirm_delete_post(callback: CallbackQuery):
    """Подтверждение удаления поста через callback"""
    user_id = callback.from_user.id
    post_id = int(callback.data.split(":", 1)[1])
    
    # Проверяем доступ
    post = supabase_db.db.get_post(post_id)
    if not post or not supabase_db.db.is_channel_admin(post.get("channel_id"), user_id):
        await callback.answer("❌ У вас нет доступа к этому посту!")
        return
    
    if supabase_db.db.delete_post(post_id):
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📋 Список постов", callback_data="posts_menu")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ])
        
        await callback.message.edit_text(
            f"✅ **Пост #{post_id} удален**\n\n"
            f"Пост успешно удален из базы данных.",
            parse_mode="Markdown",
            reply_markup=keyboard
        )
    else:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📋 Список постов", callback_data="posts_menu")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ])
        await callback.message.edit_text(
            f"❌ **Ошибка удаления**\n\n"
            f"Не удалось удалить пост",
            parse_mode="Markdown",
            reply_markup=keyboard
        )
    
    await callback.answer()
