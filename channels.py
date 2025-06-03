from aiogram import Router, types, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramAPIError  # Импортируем специфичные ошибки API
import supabase_db
from __init__ import TEXTS # Убедитесь, что TEXTS корректно импортируется и содержит нужные ключи
import asyncio
import logging # Лучше использовать logging вместо print для продакшена

# Настройка логирования (опционально, но рекомендуется)
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')


router = Router()

# -------------------------------------------------------------
# Помощники для меню
# -------------------------------------------------------------

def get_channels_main_menu(lang: str):
    # Убедимся, что TEXTS содержит эти ключи или используем значения по умолчанию
    texts_menu = TEXTS.get(lang, {}).get('channels_menu_buttons', {
        'add': "➕ Добавить",
        'remove': "🗑 Удалить",
        'list': "📋 Список",
        'main_menu': "🏠 Главное меню"
    })
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=texts_menu['add'], callback_data="channels_add")],
        [InlineKeyboardButton(text=texts_menu['remove'], callback_data="channels_remove")],
        [InlineKeyboardButton(text=texts_menu['list'], callback_data="channels_list")],
        [InlineKeyboardButton(text=texts_menu['main_menu'], callback_data="main_menu")],
    ])


def get_back_menu(lang: str = "ru"): # Добавим lang для консистентности
    text_back = TEXTS.get(lang, {}).get('general_buttons', {}).get('back', "🔙 Назад")
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=text_back, callback_data="channels_menu")]
    ])


# -------------------------------------------------------------
# Основная команда /channels
# -------------------------------------------------------------

@router.message(Command("channels"))
async def cmd_channels(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user_data = supabase_db.db.ensure_user(user_id) # Переименовал user в user_data для ясности
    lang = user_data.get("language", "ru") if user_data else "ru"

    args = message.text.split()[1:] if len(message.text.split()) > 1 else []

    if not args:
        await show_channels_menu(message, user_data, lang)
        return

    sub_command = args[0].lower()
    if sub_command == "add" and len(args) > 1:
        await add_channel_direct(message, user_data, lang, args[1])
    elif sub_command == "remove" and len(args) > 1:
        await remove_channel_direct(message, user_data, lang, args[1])
    elif sub_command == "list":
        await list_channels_direct(message, user_data, lang)
    else:
        await message.answer(TEXTS.get(lang, {}).get('channels_unknown_command', "Неизвестная подкоманда для /channels"))


async def show_channels_menu(message: Message, user_data: dict, lang: str):
    """Показать главное меню управления каналами"""
    text = TEXTS.get(lang, {}).get('channels_manage_title', "🔧 **Управление каналами**\n\nВыберите действие:")
    keyboard = get_channels_main_menu(lang)
    # Используем message.reply если это ответ на сообщение, или message.answer если новое
    # Для команды обычно message.answer
    await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")


# -------------------------------------------------------------
# Добавление канала напрямую (без FSM) - УЛУЧШЕННАЯ ВЕРСИЯ
# -------------------------------------------------------------

async def add_channel_direct(message: Message, user_data: dict, lang: str, identifier: str):
    """Добавить канал напрямую"""
    project_id = user_data.get("current_project")
    if not project_id:
        await message.answer(TEXTS.get(lang, {}).get('project_not_active', "❌ Нет активного проекта. Создайте проект через /project"))
        return

    chat_info = None
    try:
        logger.info(f"Attempting to get chat info for identifier: {identifier}")
        if identifier.startswith("@"):
            chat_info = await message.bot.get_chat(identifier)
        else:
            try:
                chat_id_int = int(identifier)
                chat_info = await message.bot.get_chat(chat_id_int)
            except ValueError:
                await message.answer(TEXTS.get(lang, {}).get('channels_invalid_id_format', "❌ Неверный формат ID канала. ID должен быть числом."))
                return
        
        logger.info(f"Fetched chat: ID={chat_info.id}, Title='{chat_info.title}', Type={chat_info.type}, Username=@{chat_info.username}")

    except TelegramAPIError as e:
        logger.warning(f"TelegramAPIError getting chat '{identifier}': {e.description}")
        if "chat not found" in e.description.lower():
            await message.answer(
                TEXTS.get(lang, {}).get('channels_not_found_detailed', 
                f"❌ Канал с ID/username '{identifier}' не найден. Убедитесь, что ID/username указан верно и, если канал приватный, бот добавлен в него.")
            )
        elif "bot was blocked by the user" in e.description.lower() and chat_info and chat_info.type == "private": # Если это ЛС с ботом
             pass # Это нормально, если пользователь заблокировал бота, но мы можем пытаться добавить "канал" (ЛС)
        else:
            await message.answer(TEXTS.get(lang, {}).get('channels_get_info_error', "❌ Ошибка при получении информации о канале:") + f" {e.description}")
        return
    except Exception as e:
        logger.error(f"Unexpected error fetching chat '{identifier}': {e}", exc_info=True)
        await message.answer(TEXTS.get(lang, {}).get('channels_get_info_unexpected_error', "❌ Непредвиденная ошибка при получении информации о канале."))
        return

    if not chat_info:
        # Эта проверка на случай, если предыдущие return не сработали по какой-то причине
        await message.answer(TEXTS.get(lang, {}).get('channels_get_info_failed', "❌ Не удалось получить информацию о канале."))
        return

    # Проверяем права пользователя в канале
    user_is_admin_in_channel = False
    try:
        # Бот должен быть в чате, чтобы проверить права другого пользователя, если это не супергруппа/канал где бот админ.
        # Для публичных каналов это может работать и без участия бота в канале.
        user_member = await message.bot.get_chat_member(chat_info.id, message.from_user.id)
        logger.info(f"User {message.from_user.id} status in chat {chat_info.id} ('{chat_info.title}'): {user_member.status}")
        if user_member.status in ['administrator', 'creator']:
            user_is_admin_in_channel = True
    except TelegramAPIError as e:
        logger.warning(f"TelegramAPIError checking user ({message.from_user.id}) admin status in chat {chat_info.id} ('{chat_info.title}'): {e.description}")
        # Если бот не участник, он может не смочь проверить права пользователя.
        # Сообщение об этом будет выведено ниже, если user_is_admin_in_channel останется False.
        # Типичные ошибки: "user not found" (если юзер не в чате, или бот не в чате и не видит юзера),
        # "bot is not a member of the channel/supergroup"
        pass # user_is_admin_in_channel останется False
    except Exception as e:
        logger.error(f"Exception checking user admin status for user {message.from_user.id} in chat {chat_info.id}: {e}", exc_info=True)
        pass # user_is_admin_in_channel останется False

    if not user_is_admin_in_channel:
        # Формируем сообщение с названием канала
        channel_name_for_msg = f"'{chat_info.title}' (@{chat_info.username})" if chat_info.username else f"'{chat_info.title}'"
        error_text_key = 'channels_user_not_admin'
        default_error_text = (
            f"❌ **Ошибка доступа**\n\n"
            f"Вы должны быть администратором в канале {channel_name_for_msg} для его добавления, "
            "либо не удалось подтвердить ваши права администратора.\n\n"
            "Убедитесь, что:\n"
            "1. Вы указали правильный ID или @username канала.\n"
            "2. Вы действительно являетесь администратором (или создателем) в этом канале.\n"
            "3. Бот добавлен в этот канал как участник (это необходимо для проверки ваших прав)."
        )
        await message.answer(TEXTS.get(lang, {}).get(error_text_key, default_error_text), parse_mode="Markdown")
        return

    # Проверяем права бота в канале
    bot_is_verified_admin_in_channel = False
    bot_can_post = False # Для более точной проверки
    bot_admin_check_details = ""
    try:
        bot_member_in_chat = await message.bot.get_chat_member(chat_info.id, message.bot.id)
        logger.info(f"Bot {message.bot.id} status in chat {chat_info.id} ('{chat_info.title}'): {bot_member_in_chat.status}")
        if bot_member_in_chat.status in ['administrator', 'creator']:
            bot_is_verified_admin_in_channel = True
            # Дополнительно проверим право на постинг, если это администратор
            if hasattr(bot_member_in_chat, 'can_post_messages') and bot_member_in_chat.can_post_messages:
                bot_can_post = True
            elif bot_member_in_chat.status == 'creator': # Создатель всегда может постить
                 bot_can_post = True
            
            if not bot_can_post and bot_is_verified_admin_in_channel:
                 bot_admin_check_details = TEXTS.get(lang,{}).get('channels_bot_admin_no_post', "Бот является администратором, но не имеет права публиковать сообщения.")
            elif bot_can_post:
                 bot_admin_check_details = TEXTS.get(lang,{}).get('channels_bot_admin_with_post', "Бот является администратором с правом публикации.")

        else: # Бот не админ, но может быть участником
            bot_admin_check_details = TEXTS.get(lang,{}).get('channels_bot_not_admin', "Бот является участником канала, но не администратором.")
            
    except TelegramAPIError as e:
        logger.warning(f"TelegramAPIError checking bot ({message.bot.id}) admin status in chat {chat_info.id} ('{chat_info.title}'): {e.description}")
        if "user not found" in e.description.lower() or "bot is not a member" in e.description.lower():
            bot_admin_check_details = TEXTS.get(lang,{}).get('channels_bot_not_member', "Бот не является участником этого канала.")
        else:
            bot_admin_check_details = TEXTS.get(lang,{}).get('channels_bot_check_tg_error', "Ошибка Telegram при проверке прав бота:") + f" {e.description}."
    except Exception as e:
        logger.error(f"Exception checking bot admin status for bot {message.bot.id} in chat {chat_info.id}: {e}", exc_info=True)
        bot_admin_check_details = TEXTS.get(lang,{}).get('channels_bot_check_unknown_error', "Неизвестная ошибка при проверке прав бота.")

    # Сообщение о статусе бота, если он не полностью готов к работе
    if not bot_is_verified_admin_in_channel or (bot_is_verified_admin_in_channel and not bot_can_post) :
        warning_text_key = 'channels_bot_warning_publish'
        default_warning_text = (
            f"⚠️ **Внимание!** {bot_admin_check_details}\n"
            "Добавить канал можно, но автоматическая публикация постов (если она требуется) может быть невозможна.\n\n"
            "Если нужна автоматическая публикация, убедитесь, что бот является администратором канала с правом 'Публикация сообщений'."
        )
        await message.answer(TEXTS.get(lang, {}).get(warning_text_key, default_warning_text), parse_mode="Markdown")

    # Добавляем канал в базу данных
    try:
        # Убедимся, что chat_info.username существует, иначе передаем None или пустую строку
        username_to_db = chat_info.username if hasattr(chat_info, 'username') else None
        
        channel_data = supabase_db.db.add_channel(
            user_id=message.from_user.id,
            chat_id=chat_info.id,
            name=chat_info.title or username_to_db or str(chat_info.id), # Название канала
            project_id=project_id,
            username=username_to_db,
            is_admin_verified=bot_is_verified_admin_in_channel and bot_can_post # Сохраняем, может ли бот постить
        )

        if channel_data:
            status_text = ""
            if bot_is_verified_admin_in_channel and bot_can_post:
                status_text = TEXTS.get(lang,{}).get('channels_add_status_bot_admin_can_post', "✅ (бот - админ с правом постинга)")
            elif bot_is_verified_admin_in_channel:
                status_text = TEXTS.get(lang,{}).get('channels_add_status_bot_admin_no_post', "⚠️ (бот - админ, но нет права постить)")
            else:
                status_text = TEXTS.get(lang,{}).get('channels_add_status_bot_not_admin', "❓ (бот не админ или нет прав)")

            channel_name_for_msg = f"'{channel_data['name']}'"
            success_text_key = 'channels_added_success'
            default_success_text = (
                f"✅ **Канал {channel_name_for_msg} добавлен** {status_text}\n\n"
                f"**ID:** `{channel_data['chat_id']}`"
            )
            await message.answer(TEXTS.get(lang, {}).get(success_text_key, default_success_text), parse_mode="Markdown")
        else:
            # Проверим, может канал уже существует?
            # Это зависит от реализации supabase_db.db.add_channel (возвращает ли он None при дубликате или ошибку)
            # Предположим, что add_channel может вернуть None/False, если канал уже есть и не был обновлен
            existing_channel = supabase_db.db.get_channel_by_chat_id_and_project(chat_info.id, project_id) # Нужна такая функция
            if existing_channel:
                 await message.answer(TEXTS.get(lang, {}).get('channels_already_exists', f"ℹ️ Канал '{chat_info.title}' уже был ранее добавлен в этот проект."))
            else:
                 await message.answer(TEXTS.get(lang, {}).get('channels_add_db_error', "❌ Ошибка при добавлении канала в базу данных. Попробуйте позже."))

    except Exception as e:
        logger.error(f"Database error adding channel {chat_info.id} ('{chat_info.title}'): {e}", exc_info=True)
        await message.answer(TEXTS.get(lang, {}).get('channels_add_db_exception', "❌ Критическая ошибка при сохранении канала в базу данных."))


# -------------------------------------------------------------
# Удаление канала напрямую
# -------------------------------------------------------------

async def remove_channel_direct(message: Message, user_data: dict, lang: str, identifier: str):
    project_id = user_data.get("current_project")
    if not project_id: # Хотя для удаления канала проект не так важен, как user_id и channel_id
        # но если логика такая, что каналы привязаны к проектам юзера, то ок
        await message.answer(TEXTS.get(lang, {}).get('project_not_active', "❌ Нет активного проекта. Создайте проект через /project"))
        return

    # Создаем клавиатуру подтверждения
    confirm_text = TEXTS.get(lang,{}).get('general_buttons',{}).get('yes', "✅ Да")
    cancel_text = TEXTS.get(lang,{}).get('general_buttons',{}).get('no', "❌ Нет")
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=confirm_text, callback_data=f"confirm_remove_channel_direct:{identifier}"), # Изменил колбек для ясности
            InlineKeyboardButton(text=cancel_text, callback_data="cancel_remove_channel")
        ]
    ])
    question_text = TEXTS.get(lang, {}).get('channels_remove_confirm', "Вы уверены, что хотите удалить канал {}?").format(f"'{identifier}'")
    await message.answer(question_text, reply_markup=keyboard)


@router.callback_query(F.data.startswith("confirm_remove_channel_direct:"))
async def confirm_remove_channel_cb(callback: CallbackQuery): # Переименовал для ясности
    identifier = callback.data.split(":", 1)[1]
    user_id = callback.from_user.id
    # Нужен lang для ответа
    user_data = supabase_db.db.ensure_user(user_id)
    lang = user_data.get("language", "ru") if user_data else "ru"

    # Для удаления канала может потребоваться project_id, если он часть ключа в БД
    # Либо удаляем по user_id и chat_id/username
    # Предположим, remove_channel ожидает user_id и identifier (chat_id или username)
    result = supabase_db.db.remove_channel(user_id, identifier) # Убедитесь, что эта функция правильно работает с identifier
    
    if result:
        await callback.message.edit_text(TEXTS.get(lang, {}).get('channels_removed_success', "🗑 Канал удалён."))
    else:
        await callback.message.edit_text(TEXTS.get(lang, {}).get('channels_remove_not_found_or_error', "❌ Канал не найден или ошибка при удалении."))
    await callback.answer()


@router.callback_query(F.data == "cancel_remove_channel") # Переименовал для ясности
async def cancel_remove_channel_cb(callback: CallbackQuery):
    user_data = supabase_db.db.ensure_user(callback.from_user.id)
    lang = user_data.get("language", "ru") if user_data else "ru"
    await callback.message.edit_text(TEXTS.get(lang, {}).get('channels_remove_cancelled', "❌ Удаление отменено."))
    await callback.answer()


# -------------------------------------------------------------
# Вывод списка каналов
# -------------------------------------------------------------

async def list_channels_direct(message_or_callback_message: Message, user_data: dict, lang: str):
    # Эта функция может вызываться из Message handler или CallbackQuery handler
    # message_or_callback_message может быть message или callback.message
    user_id = user_data["id"] # Предполагая, что ensure_user возвращает dict с 'id'
    channels = supabase_db.db.list_channels(user_id) # Предполагая, что list_channels ожидает user_id

    if not channels:
        await message_or_callback_message.answer(TEXTS.get(lang, {}).get('channels_list_empty', "У вас ещё нет добавленных каналов."))
        return

    text_lines = [TEXTS.get(lang, {}).get('channels_list_title', "📋 **Ваши каналы:**") + "\n"]
    for ch in channels:
        admin_marker = "✅" if ch.get("is_admin_verified") else "❓" # is_admin_verified относится к боту
        channel_name = ch.get('name', 'Unknown Channel')
        chat_id_val = ch.get('chat_id', 'N/A')
        text_lines.append(f"{admin_marker} {channel_name} — `{chat_id_val}`")

    final_text = "\n".join(text_lines)
    
    # Если это callback.message, то лучше использовать edit_text, если текст небольшой и не меняет суть сообщения
    # Но для списка часто лучше ответить новым сообщением или отредактировать, если предыдущее было приглашением к списку.
    # В данном случае cb_channels_list вызывает list_channels_direct с callback.message.
    # Исходное сообщение было "🔧 Управление каналами...", так что edit_text подойдет.
    if isinstance(message_or_callback_message, types.Message) and message_or_callback_message.from_user.id == message_or_callback_message.chat.id :
        # Если это сообщение от пользователя (не callback) или callback, но изначальное сообщение уже не актуально
        try: # если это callback.message
            await message_or_callback_message.edit_text(final_text, parse_mode="Markdown", reply_markup=get_back_menu(lang))
        except TelegramAPIError: # если это message, или edit_text невозможен
             await message_or_callback_message.answer(final_text, parse_mode="Markdown", reply_markup=get_back_menu(lang))
    else: # Для команды /channels list
         await message_or_callback_message.answer(final_text, parse_mode="Markdown")


# -------------------------------------------------------------
# Коллбеки меню
# -------------------------------------------------------------

@router.callback_query(F.data == "channels_menu")
async def cb_channels_menu(callback: CallbackQuery, state: FSMContext): # Добавил state для единообразия, хотя он тут не используется
    await state.clear() # На всякий случай, если были активные состояния
    user_data = supabase_db.db.ensure_user(callback.from_user.id)
    lang = user_data.get("language", "ru") if user_data else "ru"
    keyboard = get_channels_main_menu(lang)
    text = TEXTS.get(lang, {}).get('channels_manage_title', "🔧 **Управление каналами**\n\nВыберите действие:")
    try:
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    except TelegramAPIError as e:
        logger.warning(f"Error editing message in cb_channels_menu: {e.description}. Sending new one.")
        await callback.message.answer(text, reply_markup=keyboard, parse_mode="Markdown") # Если не удалось отредактировать
    await callback.answer()


@router.callback_query(F.data == "channels_add")
async def cb_channels_add(callback: CallbackQuery, state: FSMContext):
    user_data = supabase_db.db.ensure_user(callback.from_user.id)
    lang = user_data.get("language", "ru") if user_data else "ru"
    prompt_text = TEXTS.get(lang, {}).get('channels_add_prompt_id', "Введите ID или @username канала:")
    try:
        await callback.message.edit_text(prompt_text, reply_markup=get_back_menu(lang))
    except TelegramAPIError as e:
        logger.warning(f"Error editing message in cb_channels_add: {e.description}. Sending new one.")
        await callback.message.answer(prompt_text, reply_markup=get_back_menu(lang))
    await state.set_state("channels_add_waiting_id")
    await callback.answer()


@router.message(F.state == "channels_add_waiting_id") # Обновленный синтаксис для FSMContext.filter_state
async def channels_add_receive_id(message: Message, state: FSMContext):
    identifier = message.text.strip()
    user_data = supabase_db.db.ensure_user(message.from_user.id)
    lang = user_data.get("language", "ru") if user_data else "ru"
    
    # После добавления или ошибки, хорошо бы вернуть пользователя в меню каналов или главное меню
    await add_channel_direct(message, user_data, lang, identifier)
    await state.clear()
    # Опционально: показать меню каналов снова
    # await show_channels_menu(message, user_data, lang)


@router.callback_query(F.data == "channels_remove")
async def cb_channels_remove(callback: CallbackQuery, state: FSMContext):
    user_data = supabase_db.db.ensure_user(callback.from_user.id)
    lang = user_data.get("language", "ru") if user_data else "ru"
    prompt_text = TEXTS.get(lang, {}).get('channels_remove_prompt_id', "Введите ID или @username канала для удаления:")
    try:
        await callback.message.edit_text(prompt_text, reply_markup=get_back_menu(lang))
    except TelegramAPIError as e:
        logger.warning(f"Error editing message in cb_channels_remove: {e.description}. Sending new one.")
        await callback.message.answer(prompt_text, reply_markup=get_back_menu(lang))
    await state.set_state("channels_remove_waiting_id")
    await callback.answer()


@router.message(F.state == "channels_remove_waiting_id") # Обновленный синтаксис
async def channels_remove_receive_id(message: Message, state: FSMContext):
    identifier = message.text.strip()
    user_data = supabase_db.db.ensure_user(message.from_user.id)
    lang = user_data.get("language", "ru") if user_data else "ru"
    
    await remove_channel_direct(message, user_data, lang, identifier) # remove_channel_direct покажет свою клавиатуру подтверждения
    await state.clear()
    # Опционально: показать меню каналов снова
    # await show_channels_menu(message, user_data, lang)


@router.callback_query(F.data == "channels_list")
async def cb_channels_list(callback: CallbackQuery, state: FSMContext): # Добавил state
    await state.clear() # На всякий случай
    user_data = supabase_db.db.ensure_user(callback.from_user.id)
    lang = user_data.get("language", "ru") if user_data else "ru"
    await list_channels_direct(callback.message, user_data, lang) # callback.message для редактирования
    await callback.answer()

# Не забудьте зарегистрировать роутер в основном файле бота:
# dp.include_router(your_channels_router_filename.router)

# Также, убедитесь, что ваша TEXTS структура корректна. Пример:
# TEXTS = {
#     "ru": {
#         "channels_menu_buttons": {
#             "add": "➕ Добавить", ...
#         },
#         "general_buttons": {
#             "back": "🔙 Назад", ...
#         },
#         "channels_manage_title": "🔧 **Управление каналами**\n\nВыберите действие:",
#         # ... и так далее для всех используемых ключей
#     },
#     "en": { ... }
# }
