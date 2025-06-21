from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import Command
import supabase_db
from datetime import datetime
from zoneinfo import ZoneInfo

router = Router()

def format_time_for_user_simple(time_str: str, user: dict) -> str:
    """Простое форматирование времени для списков"""
    try:
        if isinstance(time_str, str):
            if time_str.endswith('Z'):
                time_str = time_str[:-1] + '+00:00'
            utc_time = datetime.fromisoformat(time_str)
        else:
            utc_time = time_str
        
        user_tz_name = user.get('timezone', 'UTC')
        try:
            user_tz = ZoneInfo(user_tz_name)
            local_time = utc_time.astimezone(user_tz)
        except:
            local_time = utc_time
        
        return local_time.strftime('%m-%d %H:%M')
    except:
        return str(time_str)[:16]

def get_posts_main_menu_keyboard(lang: str = "ru"):
    """Главное меню управления постами"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⏰ Запланированные", callback_data="posts_scheduled"),
            InlineKeyboardButton(text="📝 Черновики", callback_data="posts_drafts")
        ],
        [
            InlineKeyboardButton(text="✅ Опубликованные", callback_data="posts_published"),
            InlineKeyboardButton(text="📋 Все посты", callback_data="posts_all")
        ],
        [
            InlineKeyboardButton(text="📝 Создать пост", callback_data="menu_create_post_direct"),
            InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")
        ]
    ])

def get_post_list_keyboard(posts: list, page: int = 0, posts_per_page: int = 5, list_type: str = "all"):
    """Создать клавиатуру со списком постов с пагинацией"""
    buttons = []
    
    start_idx = page * posts_per_page
    end_idx = min(start_idx + posts_per_page, len(posts))
    
    # Кнопки постов
    for i in range(start_idx, end_idx):
        post = posts[i]
        
        # Определяем статус поста
        if post.get('published'):
            status = "✅"
        elif post.get('draft'):
            status = "📝"
        elif post.get('publish_time'):
            status = "⏰"
        else:
            status = "❓"
        
        # Получаем название канала
        channel_name = "Канал"
        if post.get('channels') and isinstance(post['channels'], dict):
            channel_name = post['channels'].get('name', 'Канал')[:10]
        
        # Краткий текст поста
        post_text = post.get('text', 'Без текста')[:15]
        
        button_text = f"{status} #{post['id']} {channel_name} - {post_text}..."
        buttons.append([InlineKeyboardButton(
            text=button_text, 
            callback_data=f"post_view:{post['id']}"
        )])
    
    # Навигационные кнопки
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(
            text="⬅️ Назад", 
            callback_data=f"posts_page:{list_type}:{page-1}"
        ))
    
    if end_idx < len(posts):
        nav_buttons.append(InlineKeyboardButton(
            text="Вперед ➡️", 
            callback_data=f"posts_page:{list_type}:{page+1}"
        ))
    
    if nav_buttons:
        buttons.append(nav_buttons)
    
    # Кнопки управления страницами
    if len(posts) > posts_per_page:
        total_pages = (len(posts) + posts_per_page - 1) // posts_per_page
        page_info_text = f"📄 {page + 1}/{total_pages}"
        
        page_buttons = []
        if page > 0:
            page_buttons.append(InlineKeyboardButton(text="⏪ Первая", callback_data=f"posts_page:{list_type}:0"))
        if page < total_pages - 1:
            page_buttons.append(InlineKeyboardButton(text="⏩ Последняя", callback_data=f"posts_page:{list_type}:{total_pages-1}"))
        
        if page_buttons:
            buttons.append(page_buttons)
        
        # Добавляем информацию о странице
        buttons.append([InlineKeyboardButton(text=page_info_text, callback_data="page_info")])
    
    # Кнопка возврата
    buttons.append([InlineKeyboardButton(text="🔙 К меню постов", callback_data="posts_menu")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

@router.message(Command("list"))
async def cmd_list_posts(message: Message):
    """Показать список постов"""
    user_id = message.from_user.id
    user = supabase_db.db.get_user(user_id)
    lang = user.get("language", "ru") if user else "ru"
    
    await show_posts_menu(message, user, lang)

async def show_posts_menu(message, user, lang):
    """Показать главное меню постов"""
    user_id = user.get("user_id")
    
    # Получаем статистику
    try:
        all_posts = supabase_db.db.list_posts(user_id=user_id, only_pending=False) or []
        scheduled = [p for p in all_posts if not p.get('published') and not p.get('draft') and p.get('publish_time')]
        drafts = [p for p in all_posts if p.get('draft')]
        published = [p for p in all_posts if p.get('published')]
        
        text = (
            "📋 **Управление постами**\n\n"
            f"📊 **Статистика:**\n"
            f"⏰ Запланированных: {len(scheduled)}\n"
            f"📝 Черновиков: {len(drafts)}\n"
            f"✅ Опубликованных: {len(published)}\n"
            f"📋 Всего: {len(all_posts)}\n\n"
            f"Выберите категорию для просмотра:"
        )
    except Exception as e:
        print(f"Error getting posts stats: {e}")
        text = "📋 **Управление постами**\n\nВыберите категорию для просмотра:"
    
    keyboard = get_posts_main_menu_keyboard(lang)
    
    if hasattr(message, 'edit_text'):
        await message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    else:
        await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")

@router.callback_query(F.data == "posts_menu")
async def callback_posts_menu(callback: CallbackQuery):
    """Callback для главного меню постов"""
    user_id = callback.from_user.id
    user = supabase_db.db.get_user(user_id)
    if not user:
        user = supabase_db.db.ensure_user(user_id)
    lang = user.get("language", "ru") if user else "ru"
    
    await show_posts_menu(callback.message, user, lang)
    await callback.answer()

@router.callback_query(F.data == "posts_scheduled")
async def callback_posts_scheduled(callback: CallbackQuery):
    """Показать запланированные посты с пагинацией"""
    user_id = callback.from_user.id
    user = supabase_db.db.get_user(user_id)
    
    try:
        posts = supabase_db.db.get_scheduled_posts_by_channel(user_id) or []
        
        if not posts:
            text = "⏰ **Запланированные посты**\n\n❌ Нет запланированных постов."
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📝 Создать пост", callback_data="menu_create_post_direct")],
                [InlineKeyboardButton(text="🔙 К меню постов", callback_data="posts_menu")]
            ])
            await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
        else:
            text = f"⏰ **Запланированные посты** ({len(posts)})\n\n"
            keyboard = get_post_list_keyboard(posts, 0, 5, "scheduled")
            
            await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
            
    except Exception as e:
        print(f"Error getting scheduled posts: {e}")
        text = "❌ Ошибка загрузки запланированных постов."
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 К меню постов", callback_data="posts_menu")]
        ])
        await callback.message.edit_text(text, reply_markup=keyboard)
    
    await callback.answer()

@router.callback_query(F.data == "posts_drafts")
async def callback_posts_drafts(callback: CallbackQuery):
    """Показать черновики с пагинацией"""
    user_id = callback.from_user.id
    user = supabase_db.db.get_user(user_id)
    
    try:
        posts = supabase_db.db.get_draft_posts_by_channel(user_id) or []
        
        if not posts:
            text = "📝 **Черновики**\n\n❌ Нет черновиков."
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📝 Создать пост", callback_data="menu_create_post_direct")],
                [InlineKeyboardButton(text="🔙 К меню постов", callback_data="posts_menu")]
            ])
            await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
        else:
            text = f"📝 **Черновики** ({len(posts)})\n\n"
            keyboard = get_post_list_keyboard(posts, 0, 5, "drafts")
            
            await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
            
    except Exception as e:
        print(f"Error getting draft posts: {e}")
        text = "❌ Ошибка загрузки черновиков."
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 К меню постов", callback_data="posts_menu")]
        ])
        await callback.message.edit_text(text, reply_markup=keyboard)
    
    await callback.answer()

@router.callback_query(F.data == "posts_published")
async def callback_posts_published(callback: CallbackQuery):
    """Показать опубликованные посты с пагинацией"""
    user_id = callback.from_user.id
    user = supabase_db.db.get_user(user_id)
    
    try:
        all_posts = supabase_db.db.list_posts(user_id=user_id, only_pending=False) or []
        published_posts = [p for p in all_posts if p.get('published')]
        
        if not published_posts:
            text = "✅ **Опубликованные посты**\n\n❌ Нет опубликованных постов."
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📝 Создать пост", callback_data="menu_create_post_direct")],
                [InlineKeyboardButton(text="🔙 К меню постов", callback_data="posts_menu")]
            ])
            await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
        else:
            text = f"✅ **Опубликованные посты** ({len(published_posts)})\n\n"
            # Сортируем по дате создания (новые сначала)
            published_posts.sort(key=lambda x: x.get('created_at', ''), reverse=True)
            keyboard = get_post_list_keyboard(published_posts, 0, 5, "published")
            
            await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
            
    except Exception as e:
        print(f"Error getting published posts: {e}")
        text = "❌ Ошибка загрузки опубликованных постов."
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 К меню постов", callback_data="posts_menu")]
        ])
        await callback.message.edit_text(text, reply_markup=keyboard)
    
    await callback.answer()

@router.callback_query(F.data == "posts_all")
async def callback_posts_all(callback: CallbackQuery):
    """Показать все посты с пагинацией"""
    user_id = callback.from_user.id
    user = supabase_db.db.get_user(user_id)
    
    try:
        posts = supabase_db.db.list_posts(user_id=user_id, only_pending=False) or []
        
        if not posts:
            text = "📋 **Все посты**\n\n❌ У вас пока нет постов."
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📝 Создать пост", callback_data="menu_create_post_direct")],
                [InlineKeyboardButton(text="🔙 К меню постов", callback_data="posts_menu")]
            ])
            await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
        else:
            # Сортируем посты: сначала запланированные, потом черновики, потом опубликованные
            scheduled = [p for p in posts if not p.get('published') and not p.get('draft') and p.get('publish_time')]
            drafts = [p for p in posts if p.get('draft')]
            published = [p for p in posts if p.get('published')]
            published.sort(key=lambda x: x.get('created_at', ''), reverse=True)
            
            sorted_posts = scheduled + drafts + published
            
            text = f"📋 **Все посты** ({len(posts)})\n\n"
            keyboard = get_post_list_keyboard(sorted_posts, 0, 5, "all")
            
            await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
            
    except Exception as e:
        print(f"Error getting all posts: {e}")
        text = "❌ Ошибка загрузки постов."
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 К меню постов", callback_data="posts_menu")]
        ])
        await callback.message.edit_text(text, reply_markup=keyboard)
    
    await callback.answer()

@router.callback_query(F.data.startswith("posts_page:"))
async def callback_posts_page(callback: CallbackQuery):
    """Обработка пагинации постов"""
    parts = callback.data.split(":")
    list_type = parts[1]
    page = int(parts[2])
    
    user_id = callback.from_user.id
    user = supabase_db.db.get_user(user_id)
    
    try:
        if list_type == "scheduled":
            posts = supabase_db.db.get_scheduled_posts_by_channel(user_id) or []
            title = "⏰ **Запланированные посты**"
        elif list_type == "drafts":
            posts = supabase_db.db.get_draft_posts_by_channel(user_id) or []
            title = "📝 **Черновики**"
        elif list_type == "published":
            all_posts = supabase_db.db.list_posts(user_id=user_id, only_pending=False) or []
            posts = [p for p in all_posts if p.get('published')]
            posts.sort(key=lambda x: x.get('created_at', ''), reverse=True)
            title = "✅ **Опубликованные посты**"
        else:  # all
            posts = supabase_db.db.list_posts(user_id=user_id, only_pending=False) or []
            # Сортируем
            scheduled = [p for p in posts if not p.get('published') and not p.get('draft') and p.get('publish_time')]
            drafts = [p for p in posts if p.get('draft')]
            published = [p for p in posts if p.get('published')]
            published.sort(key=lambda x: x.get('created_at', ''), reverse=True)
            posts = scheduled + drafts + published
            title = "📋 **Все посты**"
        
        text = f"{title} ({len(posts)})\n\n"
        keyboard = get_post_list_keyboard(posts, page, 5, list_type)
        
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
        
    except Exception as e:
        print(f"Error in posts pagination: {e}")
        await callback.answer("❌ Ошибка загрузки страницы")
    
    await callback.answer()

@router.callback_query(F.data == "page_info")
async def callback_page_info(callback: CallbackQuery):
    """Информация о странице (пустой обработчик)"""
    await callback.answer()

@router.callback_query(F.data.startswith("post_view:"))
async def callback_post_view(callback: CallbackQuery):
    """Полный просмотр конкретного поста (ИСПРАВЛЕНО)"""
    post_id = int(callback.data.split(":", 1)[1])
    user_id = callback.from_user.id
    
    # Получаем пост
    post = supabase_db.db.get_post(post_id)
    if not post:
        await callback.answer("❌ Пост не найден!")
        return
    
    # Проверяем доступ через канал
    if not supabase_db.db.is_channel_admin(post.get("channel_id"), user_id):
        await callback.answer("❌ У вас нет доступа к этому посту!")
        return
    
    # Получаем пользователя для форматирования времени
    user = supabase_db.db.get_user(user_id)
    
    # Отправляем полный просмотр поста
    try:
        # Импортируем функции из view_post
        from view_post import send_post_preview_safe, format_time_for_user
        
        # Отправляем превью поста как новое сообщение
        await send_post_preview_safe(callback.message, post)
        
        # Отправляем информацию с кнопками как второе сообщение
        channel = supabase_db.db.get_channel(post['channel_id'])
        channel_name = channel['name'] if channel else 'Неизвестный канал'
        
        info_text = f"👀 **Пост #{post_id}**\n\n"
        info_text += f"📺 **Канал:** {channel_name}\n"
        
        if post.get('published'):
            info_text += "✅ **Статус:** Опубликован\n"
        elif post.get('draft'):
            info_text += "📝 **Статус:** Черновик\n"
        elif post.get('publish_time'):
            if user:
                formatted_time = format_time_for_user(post['publish_time'], user)
                info_text += f"⏰ **Запланировано:** {formatted_time}\n"
            else:
                info_text += f"⏰ **Запланировано:** {post['publish_time']}\n"
        
        # Создаем клавиатуру действий
        buttons = []
        
        if not post.get('published'):
            buttons.append([
                InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"post_edit_direct:{post_id}"),
                InlineKeyboardButton(text="🚀 Опубликовать", callback_data=f"post_publish_cmd:{post_id}")
            ])
            buttons.append([
                InlineKeyboardButton(text="📅 Перенести", callback_data=f"post_reschedule_cmd:{post_id}"),
                InlineKeyboardButton(text="🗑 Удалить", callback_data=f"post_delete_cmd:{post_id}")
            ])
        
        buttons.append([
            InlineKeyboardButton(text="📋 К списку", callback_data="posts_menu"),
            InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")
        ])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        
        # Отправляем как новое сообщение
        await callback.message.answer(info_text, parse_mode="Markdown", reply_markup=keyboard)
        await callback.answer()
        
    except ImportError:
        # Fallback если модуль view_post недоступен
        info_text = f"👀 **Пост #{post_id}**\n\nИспользуйте команду `/view {post_id}` для полного просмотра."
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📋 К списку", callback_data="posts_menu")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ])
        await callback.message.answer(info_text, parse_mode="Markdown", reply_markup=keyboard)
        await callback.answer()
    except Exception as e:
        print(f"Error in post view: {e}")
        await callback.answer("❌ Ошибка просмотра поста")

async def send_post_preview_safe(message: Message, post: dict):
    """Безопасная отправка превью поста"""
    try:
        from view_post import send_post_preview
        await send_post_preview(message, post)
    except Exception as e:
        print(f"Error sending post preview: {e}")
        # Fallback - отправляем основную информацию текстом
        text = f"📝 **Превью поста #{post['id']}**\n\n"
        
        if post.get('text'):
            text += f"**Текст:** {post['text'][:200]}{'...' if len(post['text']) > 200 else ''}\n"
        
        if post.get('media_type'):
            text += f"**Медиа:** {post['media_type']}\n"
        
        if post.get('parse_mode'):
            text += f"**Формат:** {post['parse_mode']}\n"
        
        await message.answer(text, parse_mode="Markdown")
