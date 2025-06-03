from aiogram import Router, types, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
import supabase_db
from __init__ import TEXTS
import asyncio

router = Router()

# Главное меню управления каналами
def get_channels_main_menu(lang: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Список каналов", callback_data="channels_list")],
        [InlineKeyboardButton(text="➕ Добавить канал", callback_data="channels_add")],
        [InlineKeyboardButton(text="🗑 Удалить канал", callback_data="channels_remove")],
        [InlineKeyboardButton(text="🔄 Проверить права", callback_data="channels_check_admin")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
    ])

@router.message(Command("channels"))
async def cmd_channels(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user = supabase_db.db.ensure_user(user_id)
    lang = user.get("language", "ru") if user else "ru"
    
    # Parse subcommand
    args = message.text.split()[1:] if len(message.text.split()) > 1 else []
    
    if not args:
        # Show main channels menu
        await show_channels_menu(message, user, lang)
    elif args[0] == "add" and len(args) > 1:
        await add_channel_direct(message, user, lang, args[1])
    elif args[0] == "remove" and len(args) > 1:
        await remove_channel_direct(message, user, lang, args[1])
    elif args[0] == "list":
        await list_channels_direct(message, user, lang)
    else:
        await message.answer(TEXTS[lang]['channels_unknown_command'])

async def show_channels_menu(message: Message, user: dict, lang: str):
    """Показать главное меню управления каналами"""
    text = "🔧 **Управление каналами**\n\nВыберите действие:"
    keyboard = get_channels_main_menu(lang)
    await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")

@router.callback_query(F.data == "channels_list")
async def callback_list_channels(callback: CallbackQuery):
    user_id = callback.from_user.id
    user = supabase_db.db.get_user(user_id)
    lang = user.get("language", "ru") if user else "ru"
    
    await list_channels_callback(callback, user, lang)

@router.callback_query(F.data == "channels_add")
async def callback_add_channel(callback: CallbackQuery):
    user_id = callback.from_user.id
    user = supabase_db.db.get_user(user_id)
    lang = user.get("language", "ru") if user else "ru"
    
    text = ("➕ **Добавление канала**\n\n"
            "Отправьте ID канала или @username канала.\n"
            "Например: `-1001234567890` или `@mychannel`\n\n"
            "⚠️ **Важно:** Бот должен быть администратором канала!")
    
    # Кнопка отмены
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="channels_menu")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data == "channels_remove")
async def callback_remove_channel(callback: CallbackQuery):
    user_id = callback.from_user.id
    user = supabase_db.db.get_user(user_id)
    lang = user.get("language", "ru") if user else "ru"
    
    await show_channels_for_removal(callback, user, lang)

@router.callback_query(F.data == "channels_check_admin")
async def callback_check_admin_rights(callback: CallbackQuery):
    user_id = callback.from_user.id
    user = supabase_db.db.get_user(user_id)
    lang = user.get("language", "ru") if user else "ru"
    
    await check_admin_rights_all(callback, user, lang)

@router.callback_query(F.data == "channels_menu")
async def callback_channels_menu(callback: CallbackQuery):
    user_id = callback.from_user.id
    user = supabase_db.db.get_user(user_id)
    lang = user.get("language", "ru") if user else "ru"
    
    text = "🔧 **Управление каналами**\n\nВыберите действие:"
    keyboard = get_channels_main_menu(lang)
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()

async def list_channels_callback(callback: CallbackQuery, user: dict, lang: str):
    """Показать список каналов через callback"""
    project_id = user.get("current_project")
    if not project_id:
        text = "❌ Нет активного проекта. Создайте проект через /project"
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ])
        await callback.message.edit_text(text, reply_markup=keyboard)
        await callback.answer()
        return
    
    channels = supabase_db.db.list_channels(project_id=project_id)
    if not channels:
        text = ("📋 **Список каналов**\n\n"
                "❌ Каналы не найдены.\n"
                "Добавьте канал с помощью кнопки ниже.")
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить канал", callback_data="channels_add")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="channels_menu")]
        ])
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
        await callback.answer()
        return
    
    text = "📋 **Список каналов**\n\n"
    buttons = []
    
    for i, channel in enumerate(channels, 1):
        admin_status = "✅" if channel.get('is_admin_verified') else "❓"
        text += f"{i}. {admin_status} **{channel['name']}**\n"
        text += f"   ID: `{channel['chat_id']}`\n"
        if channel.get('username'):
            text += f"   @{channel['username']}\n"
        text += "\n"
        
        # Кнопка для каждого канала
        buttons.append([InlineKeyboardButton(
            text=f"⚙️ {channel['name'][:20]}...", 
            callback_data=f"channel_manage:{channel['id']}"
        )])
    
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="channels_menu")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()

async def list_channels_direct(message: Message, user: dict, lang: str):
    """Показать список каналов через команду"""
    project_id = user.get("current_project")
    if not project_id:
        await message.answer(TEXTS[lang]['channels_no_channels'])
        return
    
    channels = supabase_db.db.list_channels(project_id=project_id)
    if not channels:
        await message.answer(TEXTS[lang]['channels_no_channels'])
        return
    
    text = TEXTS[lang]['channels_list_title'] + "\n"
    for i, channel in enumerate(channels, 1):
        admin_status = "✅" if channel.get('is_admin_verified') else "❓"
        text += f"{i}. {admin_status} " + TEXTS[lang]['channels_item'].format(
            name=channel['name'], 
            id=channel['chat_id']
        ) + "\n"
    
    await message.answer(text)

async def show_channels_for_removal(callback: CallbackQuery, user: dict, lang: str):
    """Показать каналы для удаления"""
    project_id = user.get("current_project")
    if not project_id:
        text = "❌ Нет активного проекта."
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="channels_menu")]
        ])
        await callback.message.edit_text(text, reply_markup=keyboard)
        await callback.answer()
        return
    
    channels = supabase_db.db.list_channels(project_id=project_id)
    if not channels:
        text = "❌ Нет каналов для удаления."
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="channels_menu")]
        ])
        await callback.message.edit_text(text, reply_markup=keyboard)
        await callback.answer()
        return
    
    text = "🗑 **Удаление канала**\n\nВыберите канал для удаления:"
    buttons = []
    
    for channel in channels:
        buttons.append([InlineKeyboardButton(
            text=f"🗑 {channel['name']}", 
            callback_data=f"remove_channel_confirm:{channel['id']}"
        )])
    
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="channels_menu")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()

async def check_admin_rights_all(callback: CallbackQuery, user: dict, lang: str):
    """Проверить права администратора для всех каналов"""
    project_id = user.get("current_project")
    if not project_id:
        text = "❌ Нет активного проекта."
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="channels_menu")]
        ])
        await callback.message.edit_text(text, reply_markup=keyboard)
        await callback.answer()
        return
    
    channels = supabase_db.db.list_channels(project_id=project_id)
    if not channels:
        text = "❌ Нет каналов для проверки."
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="channels_menu")]
        ])
        await callback.message.edit_text(text, reply_markup=keyboard)
        await callback.answer()
        return
    
    text = "🔄 **Проверка прав администратора...**\n\n"
    await callback.message.edit_text(text, parse_mode="Markdown")
    
    results = []
    for channel in channels:
        try:
            # Проверяем права администратора
            chat_member = await callback.bot.get_chat_member(channel['chat_id'], callback.bot.id)
            is_admin = chat_member.status in ['administrator', 'creator']
            
            # Обновляем статус в базе данных
            supabase_db.db.update_channel_admin_status(channel['id'], is_admin)
            
            status = "✅ Администратор" if is_admin else "❌ Не администратор"
            results.append(f"**{channel['name']}**: {status}")
            
        except Exception as e:
            results.append(f"**{channel['name']}**: ❌ Ошибка проверки")
    
    text = "🔄 **Результаты проверки прав:**\n\n" + "\n".join(results)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="channels_menu")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()

# Фильтр для текстовых сообщений - только если они похожи на ID канала
async def channel_id_filter(message):
    """Фильтр для определения, является ли сообщение ID канала"""
    if not message.text:
        return False
    text = message.text.strip()
    # Проверяем, похоже ли на ID канала или username
    return text.startswith('@') or (text.startswith('-') and text[1:].isdigit())

# Обработка текстовых сообщений для добавления канала (только если они похожи на ID канала)
@router.message(F.text, channel_id_filter)
async def handle_channel_input(message: Message, state: FSMContext):
    """Обработка ввода ID канала"""
    user_id = message.from_user.id
    user = supabase_db.db.get_user(user_id)
    lang = user.get("language", "ru") if user else "ru"
    
    text = message.text.strip()
    await add_channel_direct(message, user, lang, text)

async def add_channel_direct(message: Message, user: dict, lang: str, identifier: str):
    """Добавить канал напрямую"""
    project_id = user.get("current_project")
    if not project_id:
        await message.answer("❌ Нет активного проекта. Создайте проект через /project")
        return
    
    try:
        # Получаем информацию о чате
        if identifier.startswith("@"):
            chat = await message.bot.get_chat(identifier)
        else:
            chat_id = int(identifier)
            chat = await message.bot.get_chat(chat_id)
        
        # Проверяем права пользователя в канале
        try:
            user_member = await message.bot.get_chat_member(chat.id, message.from_user.id)
            user_is_admin = user_member.status in ['administrator', 'creator']
        except:
            user_is_admin = False
        
        if not user_is_admin:
            await message.answer(
                "❌ **Ошибка доступа**\n\n"
                "Вы должны быть администратором канала для его добавления.",
                parse_mode="Markdown"
            )
            return
        
        # Проверяем права бота в канале
        try:
            chat_member = await message.bot.get_chat_member(chat.id, message.bot.id)
            is_admin = chat_member.status in ['administrator', 'creator']
        except:
            is_admin = False
        
        if not is_admin:
            await message.answer(
                "⚠️ **Внимание!** Бот не является администратором этого канала.\n"
                "Добавить канал можно, но публикация постов будет невозможна.\n\n"
                "Сделайте бота администратором канала и повторите проверку.",
                parse_mode="Markdown"
            )
        
        # Добавляем канал в базу данных
        channel = supabase_db.db.add_channel(
            user_id=message.from_user.id,
            chat_id=chat.id,
            name=chat.title or chat.username or str(chat.id),
            project_id=project_id,
            username=chat.username,
            is_admin_verified=is_admin
        )
        
        if channel:
            status_text = "✅ с правами администратора" if is_admin else "❓ без прав администратора"
            await message.answer(
                f"✅ **Канал добавлен** {status_text}\n\n"
                f"**Название:** {channel['name']}\n"
                f"**ID:** `{channel['chat_id']}`",
                parse_mode="Markdown"
            )
        else:
            await message.answer("❌ Ошибка при добавлении канала в базу данных.")
    
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")

async def remove_channel_direct(message: Message, user: dict, lang: str, identifier: str):
    """Удалить канал напрямую"""
    project_id = user.get("current_project")
    if not project_id:
        await message.answer(TEXTS[lang]['channels_not_found'])
        return
    
    # Создаем клавиатуру подтверждения
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да", callback_data=f"remove_channel_direct:{identifier}"),
            InlineKeyboardButton(text="❌ Нет", callback_data="remove_channel_cancel")
        ]
    ])
    
    await message.answer(
        TEXTS[lang]['channels_remove_confirm'].format(name=identifier),
        reply_markup=keyboard
    )

@router.callback_query(F.data.startswith("remove_channel_confirm:"))
async def confirm_remove_channel(callback: CallbackQuery):
    user_id = callback.from_user.id
    user = supabase_db.db.get_user(user_id)
    lang = user.get("language", "ru") if user else "ru"
    project_id = user.get("current_project")
    
    channel_id = callback.data.split(":", 1)[1]
    
    try:
        # Получаем информацию о канале
        channel = supabase_db.db.get_channel(int(channel_id))
        if not channel:
            await callback.message.edit_text("❌ Канал не найден.")
            await callback.answer()
            return
        
        # Удаляем канал
        if supabase_db.db.remove_channel(project_id, channel_id):
            await callback.message.edit_text(
                f"✅ **Канал удален**\n\n"
                f"**{channel['name']}** был удален из проекта.\n"
                f"Все связанные посты также удалены.",
                parse_mode="Markdown"
            )
        else:
            await callback.message.edit_text("❌ Ошибка при удалении канала.")
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка: {str(e)}")
    
    await callback.answer()

@router.callback_query(F.data.startswith("remove_channel_direct:"))
async def confirm_remove_channel_direct(callback: CallbackQuery):
    user_id = callback.from_user.id
    user = supabase_db.db.get_user(user_id)
    lang = user.get("language", "ru") if user else "ru"
    project_id = user.get("current_project")
    
    identifier = callback.data.split(":", 1)[1]
    
    if supabase_db.db.remove_channel(project_id, identifier):
        await callback.message.edit_text(TEXTS[lang]['channels_removed'])
    else:
        await callback.message.edit_text(TEXTS[lang]['channels_not_found'])
    
    await callback.answer()

@router.callback_query(F.data == "remove_channel_cancel")
async def cancel_remove_channel(callback: CallbackQuery):
    user_id = callback.from_user.id
    user = supabase_db.db.get_user(user_id)
    lang = user.get("language", "ru") if user else "ru"
    
    await callback.message.edit_text(TEXTS[lang]['confirm_post_cancel'])
    await callback.answer()

@router.callback_query(F.data.startswith("channel_manage:"))
async def manage_specific_channel(callback: CallbackQuery):
    """Управление конкретным каналом"""
    user_id = callback.from_user.id
    user = supabase_db.db.get_user(user_id)
    lang = user.get("language", "ru") if user else "ru"
    
    channel_id = int(callback.data.split(":", 1)[1])
    channel = supabase_db.db.get_channel(channel_id)
    
    if not channel:
        await callback.message.edit_text("❌ Канал не найден.")
        await callback.answer()
        return
    
    admin_status = "✅ Администратор" if channel.get('is_admin_verified') else "❓ Не проверено"
    
    text = (f"⚙️ **Управление каналом**\n\n"
            f"**Название:** {channel['name']}\n"
            f"**ID:** `{channel['chat_id']}`\n"
            f"**Статус:** {admin_status}\n")
    
    if channel.get('username'):
        text += f"**Username:** @{channel['username']}\n"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Проверить права", callback_data=f"check_admin:{channel_id}")],
        [InlineKeyboardButton(text="📋 Посты канала", callback_data=f"channel_posts:{channel_id}")],
        [InlineKeyboardButton(text="🗑 Удалить канал", callback_data=f"remove_channel_confirm:{channel_id}")],
        [InlineKeyboardButton(text="🔙 К списку каналов", callback_data="channels_list")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data.startswith("check_admin:"))
async def check_single_channel_admin(callback: CallbackQuery):
    """Проверить права администратора для одного канала"""
    channel_id = int(callback.data.split(":", 1)[1])
    channel = supabase_db.db.get_channel(channel_id)
    
    if not channel:
        await callback.message.edit_text("❌ Канал не найден.")
        await callback.answer()
        return
    
    try:
        # Проверяем права администратора
        chat_member = await callback.bot.get_chat_member(channel['chat_id'], callback.bot.id)
        is_admin = chat_member.status in ['administrator', 'creator']
        
        # Обновляем статус в базе данных
        supabase_db.db.update_channel_admin_status(channel_id, is_admin)
        
        status = "✅ Администратор" if is_admin else "❌ Не администратор"
        text = (f"🔄 **Проверка завершена**\n\n"
                f"**Канал:** {channel['name']}\n"
                f"**Статус:** {status}")
        
        if not is_admin:
            text += "\n\n⚠️ Сделайте бота администратором для публикации постов."
        
    except Exception as e:
        text = (f"❌ **Ошибка проверки**\n\n"
                f"**Канал:** {channel['name']}\n"
                f"**Ошибка:** {str(e)}")
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data=f"channel_manage:{channel_id}")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data.startswith("channel_posts:"))
async def show_channel_posts(callback: CallbackQuery):
    """Показать посты конкретного канала"""
    channel_id = int(callback.data.split(":", 1)[1])
    channel = supabase_db.db.get_channel(channel_id)
    
    if not channel:
        await callback.message.edit_text("❌ Канал не найден.")
        await callback.answer()
        return
    
    # Получаем посты канала
    posts = supabase_db.db.list_posts_by_channel(channel_id)
    
    if not posts:
        text = f"📋 **Посты канала {channel['name']}**\n\n❌ Постов не найдено."
    else:
        text = f"📋 **Посты канала {channel['name']}**\n\n"
        for i, post in enumerate(posts[:10], 1):  # Показываем только первые 10
            status = "✅" if post.get('published') else "⏰" if post.get('publish_time') else "📝"
            text += f"{i}. {status} {post.get('text', 'Без текста')[:30]}...\n"
        
        if len(posts) > 10:
            text += f"\n... и еще {len(posts) - 10} постов"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data=f"channel_manage:{channel_id}")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()
