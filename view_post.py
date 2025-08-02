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
    """Очистить и подготовить текст для определенного формата с улучшенной обработкой"""
    if not text:
        return text
    
    if parse_mode == "HTML":
        # Заменяем наши теги на HTML
        text = text.replace('[b]', '<b>').replace('[/b]', '</b>')
        text = text.replace('[i]', '<i>').replace('[/i]', '</i>')
        text = text.replace('[u]', '<u>').replace('[/u]', '</u>')
        text = text.replace('[s]', '<s>').replace('[/s]', '</s>')
        text = text.replace('[code]', '<code>').replace('[/code]', '</code>')
        text = text.replace('[pre]', '<pre>').replace('[/pre]', '</pre>')
        
        # Обрабатываем ссылки [url=link]text[/url] -> <a href="link">text</a>
        text = re.sub(r'\[url=([^\]]+)\]([^\[]+)\[/url\]', r'<a href="\1">\2</a>', text)
        
        return text
    
    elif parse_mode == "Markdown":
        # MarkdownV2 требует экранирования этих символов
        special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
        
        # Сначала сохраняем пользовательские теги и ссылки
        placeholders = {}
        placeholder_counter = 0
        
        # Обрабатываем ссылки [url=link]text[/url] заранее
        url_pattern = r'\[url=([^\]]+)\]([^\[]+?)\[/url\]'
        for match in re.finditer(url_pattern, text):
            url, link_text = match.groups()
            placeholder = f'__URLPH_{placeholder_counter}__'
            # Экранируем символы в тексте ссылки для MarkdownV2
            escaped_link_text = escape_markdown_v2_text(link_text)
            placeholders[placeholder] = f'[{escaped_link_text}]({url})'
            text = text.replace(match.group(0), placeholder)
            placeholder_counter += 1

        # Обрабатываем пользовательские теги
        tag_defs = [
            ('[b]', '[/b]', '*', '*'),
            ('[i]', '[/i]', '_', '_'),
            ('[u]', '[/u]', '__', '__'),
            ('[s]', '[/s]', '~', '~'),
            ('[code]', '[/code]', '`', '`'),
            ('[pre]', '[/pre]', '```', '```')
        ]

        for start_tag, end_tag, md_start, md_end in tag_defs:
            pattern = re.escape(start_tag) + r'(.*?)' + re.escape(end_tag)
            def replace_tag(match):
                nonlocal placeholder_counter
                content = match.group(1)
                placeholder = f'__TAGPH_{placeholder_counter}__'
                # Для тегов форматирования не экранируем содержимое
                placeholders[placeholder] = f'{md_start}{content}{md_end}'
                placeholder_counter += 1
                return placeholder
            
            text = re.sub(pattern, replace_tag, text, flags=re.DOTALL)

        # Теперь экранируем специальные символы в основном тексте
        for char in special_chars:
            text = text.replace(char, '\\' + char)

        # Восстанавливаем placeholders
        for placeholder, replacement in placeholders.items():
            text = text.replace(placeholder, replacement)

        return text
    
    else:
        # Обычный текст - убираем все теги и специальные символы
        text = re.sub(r'\[[^\]]*\]', '', text)  # Убираем наши теги
        text = re.sub(r'<[^>]+>', '', text)     # Убираем HTML теги
        return text


def escape_markdown_v2_text(text: str) -> str:
    """Экранирует специальные символы для MarkdownV2 (для использования в тексте ссылок и т.д.)"""
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!', '\\']
    for char in special_chars:
        text = text.replace(char, '\\' + char)
    return text


def escape_markdown_v2_properly(text: str) -> str:
    """Правильное экранирование текста для MarkdownV2 с обработкой пользовательских тегов"""
    if not text:
        return text
    
    # Сначала сохраняем пользовательские теги и ссылки
    placeholders = {}
    placeholder_counter = 0
    
    # Обрабатываем ссылки [url=link]text[/url] заранее
    url_pattern = r'\[url=([^\]]+)\]([^\[]+?)\[/url\]'
    for match in re.finditer(url_pattern, text):
        url, link_text = match.groups()
        placeholder = f'__URLPH_{placeholder_counter}__'
        # Экранируем символы в тексте ссылки для MarkdownV2
        escaped_link_text = escape_markdown_v2_text(link_text)
        placeholders[placeholder] = f'[{escaped_link_text}]({url})'
        text = text.replace(match.group(0), placeholder)
        placeholder_counter += 1

    # Обрабатываем пользовательские теги
    tag_defs = [
        ('[b]', '[/b]', '*', '*'),
        ('[i]', '[/i]', '_', '_'),
        ('[u]', '[/u]', '__', '__'),
        ('[s]', '[/s]', '~', '~'),
        ('[code]', '[/code]', '`', '`'),
        ('[pre]', '[/pre]', '```', '```')
    ]

    for start_tag, end_tag, md_start, md_end in tag_defs:
        pattern = re.escape(start_tag) + r'(.*?)' + re.escape(end_tag)
        def replace_tag(match):
            nonlocal placeholder_counter
            content = match.group(1)
            placeholder = f'__TAGPH_{placeholder_counter}__'
            # Для тегов форматирования не экранируем содержимое
            placeholders[placeholder] = f'{md_start}{content}{md_end}'
            placeholder_counter += 1
            return placeholder
        
        text = re.sub(pattern, replace_tag, text, flags=re.DOTALL)

    # Теперь экранируем специальные символы в основном тексте
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in special_chars:
        text = text.replace(char, '\\' + char)

    # Восстанавливаем placeholders
    for placeholder, replacement in placeholders.items():
        text = text.replace(placeholder, replacement)

    return text


async def send_post_preview(message: Message, post: dict, channel: dict = None):
    """Отправить превью поста с улучшенной обработкой ошибок форматирования"""
    text = post.get("text", "")
    media_id = post.get("media_id")
    media_type = post.get("media_type")
    format_type = post.get("parse_mode") or post.get("format")
    buttons = post.get("buttons")
    
    # Определяем parse_mode
    parse_mode = None
    if format_type:
        if format_type.lower() == "markdown":
            parse_mode = "MarkdownV2"  # Используем MarkdownV2 для лучшей совместимости
        elif format_type.lower() == "html":
            parse_mode = "HTML"
    
    # Очищаем и подготавливаем текст для формата
    cleaned_text = text
    if text and parse_mode:
        try:
            cleaned_text = clean_text_for_format(text, parse_mode.replace("V2", ""))
        except Exception as e:
            print(f"Error cleaning text for format {parse_mode}: {e}")
            # Если ошибка в Markdown, пробуем HTML
            if parse_mode == "MarkdownV2":
                try:
                    cleaned_text = clean_text_for_format(text, "HTML")
                    parse_mode = "HTML"
                except Exception as e2:
                    print(f"Error with HTML fallback: {e2}")
                    cleaned_text = clean_text_for_format(text, None)
                    parse_mode = None
            else:
                cleaned_text = clean_text_for_format(text, None)
                parse_mode = None
    
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
    final_text = cleaned_text or "📝 Пост без текста"
    
    # Отправка превью с множественными попытками
    attempts = [
        (parse_mode, final_text),  # Первая попытка с оригинальным форматом
        ("HTML", clean_text_for_format(text, "HTML") if text else "📝 Пост без текста"),  # HTML fallback
        (None, clean_text_for_format(text, None) if text else "📝 Пост без текста"),  # Без форматирования
        (None, "📝 Пост без текста")  # Минимальный fallback
    ]
    
    last_error = None
    
    for attempt_parse_mode, attempt_text in attempts:
        try:
            if media_id and media_type:
                if media_type.lower() == "photo":
                    await message.answer_photo(
                        media_id,
                        caption=attempt_text,
                        parse_mode=attempt_parse_mode,
                        reply_markup=markup
                    )
                elif media_type.lower() == "video":
                    await message.answer_video(
                        media_id,
                        caption=attempt_text,
                        parse_mode=attempt_parse_mode,
                        reply_markup=markup
                    )
                elif media_type.lower() == "animation":
                    await message.answer_animation(
                        media_id,
                        caption=attempt_text,
                        parse_mode=attempt_parse_mode,
                        reply_markup=markup
                    )
            else:
                await message.answer(
                    attempt_text,
                    parse_mode=attempt_parse_mode,
                    reply_markup=markup
                )
            # Если дошли сюда, значит отправка прошла успешно
            return
            
        except Exception as e:
            last_error = e
            print(f"Attempt with parse_mode={attempt_parse_mode} failed: {e}")
            continue
    
    # Если все попытки провалились, отправляем сообщение об ошибке
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Список постов", callback_data="posts_menu")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
    ])
    
    error_msg = (f"⚠️ **Ошибка предпросмотра**\n\n"
                f"Не удалось показать превью поста.\n\n"
                f"**Исходный формат:** {format_type or 'не задан'}\n"
                f"**Последняя ошибка:** {str(last_error)[:100]}...")
    
    try:
        await message.answer(error_msg, parse_mode="Markdown", reply_markup=keyboard)
    except Exception:
        await message.answer("⚠️ Ошибка предпросмотра поста", reply_markup=keyboard)

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

# Функция для безопасной отправки превью (используется в list_posts)
async def send_post_preview_safe(message: Message, post: dict):
    """Безопасная отправка превью поста (используется из других модулей)"""
    try:
        await send_post_preview(message, post)
    except Exception as e:
        print(f"Error sending post preview: {e}")
        # Fallback - отправляем основную информацию текстом
        text = f"📝 **Превью поста #{post.get('id', '?')}**\n\n"
        
        if post.get('text'):
            # Убираем теги форматирования для превью
            clean_text = clean_text_for_format(post['text'], None)
            text += f"**Текст:** {clean_text[:200]}{'...' if len(clean_text) > 200 else ''}\n"
        
        if post.get('media_type'):
            text += f"**Медиа:** {post['media_type']}\n"
        
        if post.get('parse_mode'):
            text += f"**Формат:** {post['parse_mode']}\n"
        
        await message.answer(text, parse_mode="Markdown")

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
    
    # Обновляем время публикации на текущее - ИСПРАВЛЕНО
    now = datetime.now(ZoneInfo("UTC"))
    supabase_db.db.update_post(post_id, {
        "publish_time": now.isoformat(),  # Конвертируем в строку!
        "draft": False
    })
    
    # Пытаемся получить бот из main.py для немедленной публикации
    try:
        # Импортируем функцию из main.py
        from main import publish_post_immediately
        
        # Пытаемся опубликовать немедленно
        # Получаем бот из глобального контекста
        from main import bot
        published = await publish_post_immediately(bot, post_id)
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👀 Просмотр поста", callback_data=f"post_full_view:{post_id}")],
            [InlineKeyboardButton(text="📋 Список постов", callback_data="posts_menu")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ])
        
        if published:
            await message.answer(
                f"✅ **Пост #{post_id} опубликован!**\n\n"
                f"Пост успешно опубликован в канал.",
                parse_mode="Markdown",
                reply_markup=keyboard
            )
        else:
            await message.answer(
                f"🚀 **Пост #{post_id} поставлен в очередь**\n\n"
                f"Пост будет опубликован в ближайшее время.",
                parse_mode="Markdown",
                reply_markup=keyboard
            )
    except ImportError:
        # Fallback если не удается импортировать функцию
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
        
        # Обновляем пост - ИСПРАВЛЕНО
        supabase_db.db.update_post(post_id, {
            "publish_time": utc_dt.isoformat(),  # Конвертируем в строку!
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
