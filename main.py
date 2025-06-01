import asyncio
import logging
import sys
from os import getenv
from datetime import datetime, timedelta
import pytz
import re

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto, InputMediaVideo, InputMediaDocument

import config
from db_manager import DBManager
from bot_states import CreatePost, ManageChannels, EditPost, DeletePost, ChangeTimezone
import telegram_utils # Import the module
from scheduler import Scheduler

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize Bot and Dispatcher
bot = Bot(token=config.BOT_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()
db_manager = DBManager()
scheduler = Scheduler(bot, db_manager)

# --- Helper Functions ---

async def get_user_db_id(chat_id: int, username: str, first_name: str, last_name: str):
    user = await db_manager.get_user(chat_id)
    if not user:
        user = await db_manager.create_user(chat_id, username, first_name, last_name)
    return user['id'], user['timezone']

async def get_user_timezone(chat_id: int):
    user = await db_manager.get_user(chat_id)
    return pytz.timezone(user['timezone']) if user and user['timezone'] else pytz.utc

def format_post_preview(post_data: dict, channels_data: list, media_count: int, buttons_data: list, schedule_info: str, deletion_info: str):
    text_preview = post_data.get('text', '<i>Без текста</i>')
    channels_preview = ", ".join([c['channels']['channel_name'] for c in channels_data]) if channels_data else "Не выбраны"
    media_preview = f"Медиа: {media_count} файл(ов)" if media_count > 0 else "Без медиа"
    buttons_preview = "\n".join([f"- {btn['button_text']} ({btn['button_url']})" for btn in buttons_data]) if buttons_data else "Без кнопок"

    preview_text = (
        f"<b>Предварительный просмотр поста:</b>\n\n"
        f"<b>Текст:</b>\n{text_preview}\n\n"
        f"<b>{media_preview}</b>\n"
        f"<b>Каналы:</b> {channels_preview}\n"
        f"<b>Кнопки:</b>\n{buttons_preview}\n\n"
        f"<b>Режим отправки:</b> {schedule_info}\n"
        f"<b>Правило удаления:</b> {deletion_info}\n\n"
        f"Подтвердите отправку/сохранение или отмените."
    )
    return preview_text

def get_deletion_info_string(post_data: dict):
    delete_type = post_data.get('delete_after_publish_type')
    if delete_type == 'never':
        return "Не удалять"
    elif delete_type == 'hours':
        return f"Удалить через {post_data.get('delete_after_publish_value')} часов после публикации"
    elif delete_type == 'days':
        return f"Удалить через {post_data.get('delete_after_publish_value')} дней после публикации"
    elif delete_type == 'specific_date':
        # Need to ensure post_data['delete_at'] is a datetime object
        delete_at_utc = post_data['delete_at']
        if isinstance(delete_at_utc, str):
            delete_at_utc = datetime.fromisoformat(delete_at_utc)

        user_tz = pytz.timezone(post_data.get('user_timezone', 'UTC')) # Assuming user_timezone is passed or fetched
        delete_at_local = delete_at_utc.astimezone(user_tz).strftime("%d.%m.%Y %H:%M")
        return f"Удалить в {delete_at_local}"
    return "Не указано"

def get_schedule_info_string(post_data: dict, user_tz: pytz.timezone):
    schedule_type = post_data.get('schedule_type')
    if not schedule_type:
        return "Мгновенно"
    elif schedule_type == 'one_time':
        scheduled_at_utc = post_data['scheduled_at']
        if isinstance(scheduled_at_utc, str):
            scheduled_at_utc = datetime.fromisoformat(scheduled_at_utc)
        scheduled_at_local = scheduled_at_utc.astimezone(user_tz).strftime("%d.%m.%Y %H:%M")
        return f"Разово: {scheduled_at_local}"
    elif schedule_type in ['daily', 'weekly', 'monthly', 'yearly']:
        info = f"Циклически ({schedule_type}): "
        cron_expression = post_data['cron_schedule']
        
        # Parse cron expression (assuming UTC for cron)
        # Example cron: "0 10 * * *" (minute hour day_of_month month day_of_week)
        cron_parts = cron_expression.split(' ')
        minute_utc = int(cron_parts[0])
        hour_utc = int(cron_parts[1])

        # Convert UTC time to user's local time for display
        dummy_date = datetime.now().date() # Any date will do for time conversion
        utc_datetime = pytz.utc.localize(datetime.combine(dummy_date, datetime.min.time().replace(hour=hour_utc, minute=minute_utc)))
        local_datetime = utc_datetime.astimezone(user_tz)
        
        local_time_str = local_datetime.strftime("%H:%M")

        if schedule_type == 'daily':
            info += f"Ежедневно в {local_time_str}"
        elif schedule_type == 'weekly':
            days_of_week_cron = cron_parts[4]
            # APScheduler CronTrigger.from_crontab uses 0=Sun, 6=Sat.
            # We need to map these to Russian days.
            cron_day_to_display_day = {0: 'Вс', 1: 'Пн', 2: 'Вт', 3: 'Ср', 4: 'Чт', 5: 'Пт', 6: 'Сб'}
            
            display_days = []
            for d in days_of_week_cron.split(','):
                try:
                    display_days.append(cron_day_to_display_day[int(d)])
                except ValueError: # If it's not a number, assume it's like MON, TUE
                    # This part might need more robust mapping if APScheduler uses different string formats
                    # For now, we'll just use the raw string if it's not numeric
                    display_days.append(d) 
            days_str = ", ".join(display_days)

            info += f"Еженедельно по {days_str} в {local_time_str}"
        elif schedule_type == 'monthly':
            day_of_month = cron_parts[2]
            info += f"Ежемесячно {day_of_month} числа в {local_time_str}"
        elif schedule_type == 'yearly':
            day_of_month = cron_parts[2]
            month = cron_parts[3]
            month_map = {'1': 'Янв', '2': 'Фев', '3': 'Мар', '4': 'Апр', '5': 'Май', '6': 'Июн', '7': 'Июл', '8': 'Авг', '9': 'Сен', '10': 'Окт', '11': 'Ноя', '12': 'Дек'}
            info += f"Ежегодно {day_of_month} {month_map.get(month, month)} в {local_time_str}"
        
        start_date = post_data.get('start_date')
        end_date = post_data.get('end_date')
        
        # Convert string dates to datetime.date objects if they are strings
        if isinstance(start_date, str):
            start_date = datetime.fromisoformat(start_date).date()
        if isinstance(end_date, str):
            end_date = datetime.fromisoformat(end_date).date()

        if start_date:
            info += f" (Начало: {start_date.strftime('%d.%m.%Y')}"
            if end_date:
                info += f", Конец: {end_date.strftime('%d.%m.%Y')})"
            else:
                info += ", Без конца)"
        return info
    return "Неизвестно"

# --- Handlers ---

@dp.message(CommandStart())
async def command_start_handler(message: Message, state: FSMContext) -> None:
    user_id, _ = await get_user_db_id(message.chat.id, message.from_user.username, message.from_user.first_name, message.from_user.last_name)
    await state.clear()
    await message.answer(
        f"Привет, {message.from_user.full_name}! Я бот для управления постами в Telegram.\n\n"
        f"Вот что я умею:\n"
        f"• <b>создать пост</b> - начать создание нового поста\n"
        f"• <b>просмотр постов</b> - показать запланированные посты\n"
        f"• <b>редактировать пост [ID]</b> - изменить существующий пост\n"
        f"• <b>отменить пост [ID]</b> - удалить запланированный пост\n"
        f"• <b>добавить канал</b> - добавить канал для публикации\n"
        f"• <b>удалить канал</b> - удалить канал из списка\n"
        f"• <b>просмотр каналов</b> - показать список ваших каналов\n"
        f"• <b>сменить часовой пояс</b> - установить ваш часовой пояс\n\n"
        f"В любой момент вы можете ввести 'отмена' или 'назад' для отмены текущего действия."
    )

@dp.message(F.text.lower() == "отмена")
@dp.message(F.text.lower() == "назад")
async def cancel_handler(message: Message, state: FSMContext) -> None:
    current_state = await state.get_state()
    if current_state is None:
        await message.answer("Нет активных действий для отмены.")
        return

    # Implement specific "назад" logic if needed for multi-step states
    # For now, "отмена" and "назад" both clear the state
    await state.clear()
    await message.answer("Действие отменено. Вы вернулись в главное меню.")

# --- Create Post ---

@dp.message(F.text.lower() == "создать пост")
async def create_post_start(message: Message, state: FSMContext):
    user_db_id, _ = await get_user_db_id(message.chat.id, message.from_user.username, message.from_user.first_name, message.from_user.last_name)
    
    new_post = await db_manager.create_post(user_db_id)
    await state.update_data(post_id=new_post['id'], user_db_id=user_db_id)
    await state.set_state(CreatePost.waiting_for_text)
    await message.answer("Отправьте текст для поста (можно использовать Markdown/HTML). Если текст не нужен, отправьте '–'.")

@dp.message(CreatePost.waiting_for_text)
async def process_post_text(message: Message, state: FSMContext):
    post_text = message.text
    if post_text == '–':
        post_text = None
    
    data = await state.get_data()
    post_id = data['post_id']
    await db_manager.update_post(post_id, {'text': post_text})
    
    await state.set_state(CreatePost.waiting_for_media)
    await message.answer("Теперь отправьте медиа (фото, видео, документ). Можно отправить несколько файлов. Когда закончите, напишите 'готово' или 'пропустить', если медиа не нужны.")

@dp.message(CreatePost.waiting_for_media, F.text.lower() == "готово")
@dp.message(CreatePost.waiting_for_media, F.text.lower() == "пропустить")
async def process_media_done(message: Message, state: FSMContext):
    data = await state.get_data()
    post_id = data['post_id']
    
    # Check if any media was actually uploaded
    media_files = await db_manager.get_post_media(post_id)
    if not media_files and message.text.lower() == "готово":
        await message.answer("Вы не прикрепили ни одного медиафайла. Если медиа не нужны, напишите 'пропустить'.")
        return

    user_channels = await db_manager.get_user_channels(data['user_db_id'])
    if not user_channels:
        await message.answer("У вас пока нет добавленных каналов. Пожалуйста, сначала добавьте канал с помощью команды 'добавить канал'. Отменяю создание поста.")
        await db_manager.delete_post_full(post_id)
        await state.clear()
        return

    channels_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=ch['channel_name'], callback_data=f"select_channel_{ch['id']}")] for ch in user_channels
    ] + [[InlineKeyboardButton(text="Завершить выбор каналов", callback_data="done_channels")]])
    
    await state.set_state(CreatePost.waiting_for_channels)
    await message.answer("Выберите один или несколько каналов для публикации:", reply_markup=channels_keyboard)

@dp.message(CreatePost.waiting_for_media, F.media_group_id)
async def handle_media_group(message: Message, state: FSMContext):
    # Aiogram handles media groups by sending each message separately.
    # We need to store them and process when 'готово' is sent.
    # For simplicity, we'll process each media message as it comes.
    # A more robust solution would collect all media from a group before processing.
    await process_media_file(message, state)

@dp.message(CreatePost.waiting_for_media, F.photo | F.video | F.document)
async def process_media_file(message: Message, state: FSMContext):
    if not telegram_utils.validate_media_file(message): # Use telegram_utils
        await message.answer(f"Файл слишком большой (макс. {config.MAX_MEDIA_SIZE_MB} МБ) или неподдерживаемый формат. Пожалуйста, отправьте другой файл.")
        return

    file_id, media_type = telegram_utils.get_media_file_id_and_type(message) # Use telegram_utils
    if not file_id:
        await message.answer("Не удалось определить тип медиафайла. Пожалуйста, попробуйте еще раз.")
        return

    data = await state.get_data()
    post_id = data['post_id']
    await db_manager.add_post_media(post_id, file_id, media_type)
    await message.answer("Медиафайл добавлен. Отправьте еще или напишите 'готово' / 'пропустить'.")

@dp.callback_query(CreatePost.waiting_for_channels, F.data.startswith("select_channel_"))
async def select_channel_callback(callback: CallbackQuery, state: FSMContext):
    channel_db_id = callback.data.split("_")[2]
    data = await state.get_data()
    selected_channels = data.get('selected_channels', [])

    if channel_db_id not in selected_channels:
        selected_channels.append(channel_db_id)
        await state.update_data(selected_channels=selected_channels)
        channel_info = await db_manager.get_channel_by_id(channel_db_id)
        await callback.answer(f"Канал '{channel_info['channel_name']}' выбран.")
    else:
        selected_channels.remove(channel_db_id)
        await state.update_data(selected_channels=selected_channels)
        channel_info = await db_manager.get_channel_by_id(channel_db_id)
        await callback.answer(f"Канал '{channel_info['channel_name']}' отменен.")
    
    # Update keyboard to reflect selection
    user_channels = await db_manager.get_user_channels(data['user_db_id'])
    updated_keyboard = []
    for ch in user_channels:
        text = f"✅ {ch['channel_name']}" if ch['id'] in selected_channels else ch['channel_name']
        updated_keyboard.append([InlineKeyboardButton(text=text, callback_data=f"select_channel_{ch['id']}")])
    updated_keyboard.append([InlineKeyboardButton(text="Завершить выбор каналов", callback_data="done_channels")])
    
    await callback.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(inline_keyboard=updated_keyboard))

@dp.callback_query(CreatePost.waiting_for_channels, F.data == "done_channels")
async def done_channels_callback(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected_channels = data.get('selected_channels', [])
    
    if not selected_channels:
        await callback.answer("Пожалуйста, выберите хотя бы один канал.", show_alert=True)
        return

    post_id = data['post_id']
    # Clear previous channels for this post if any (e.g., during edit)
    await db_manager.delete_post_channels(post_id)
    for channel_db_id in selected_channels:
        await db_manager.add_post_channel(post_id, channel_db_id)
    
    await state.set_state(CreatePost.waiting_for_buttons)
    await callback.message.edit_text("Каналы выбраны. Теперь отправьте кнопки для поста в формате: 'Текст кнопки | Ссылка'. Каждая кнопка на новой строке. Если кнопки не нужны, отправьте '–'.")
    await callback.answer()

@dp.message(CreatePost.waiting_for_buttons)
async def process_post_buttons(message: Message, state: FSMContext):
    buttons_text = message.text
    data = await state.get_data()
    post_id = data['post_id']
    
    await db_manager.delete_post_buttons(post_id) # Clear previous buttons

    if buttons_text != '–':
        button_lines = buttons_text.split('\n')
        for i, line in enumerate(button_lines):
            parts = line.split('|', 1)
            if len(parts) == 2:
                button_text = parts[0].strip()
                button_url = parts[1].strip()
                if button_text and button_url:
                    await db_manager.add_post_button(post_id, button_text, button_url, i)
                else:
                    await message.answer(f"Ошибка в формате кнопки '{line}'. Пропускаю. Используйте 'Текст | Ссылка'.")
            else:
                await message.answer(f"Ошибка в формате кнопки '{line}'. Пропускаю. Используйте 'Текст | Ссылка'.")
    
    await state.set_state(CreatePost.waiting_for_send_mode)
    send_mode_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Мгновенно", callback_data="send_instant")],
        [InlineKeyboardButton(text="Отложить разово", callback_data="send_one_time")],
        [InlineKeyboardButton(text="Запланировать циклически", callback_data="send_cyclic")]
    ])
    await message.answer("Выберите режим отправки поста:", reply_markup=send_mode_keyboard)

@dp.callback_query(CreatePost.waiting_for_send_mode, F.data == "send_instant")
async def set_send_instant(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    post_id = data['post_id']
    await db_manager.update_post(post_id, {'schedule_type': None, 'scheduled_at': None, 'cron_schedule': None, 'start_date': None, 'end_date': None})
    await state.set_state(CreatePost.waiting_for_deletion_rule)
    await callback.message.edit_text("Пост будет отправлен мгновенно. Теперь выберите правило удаления:")
    await send_deletion_rule_keyboard(callback.message)
    await callback.answer()

@dp.callback_query(CreatePost.waiting_for_send_mode, F.data == "send_one_time")
async def set_send_one_time(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    post_id = data['post_id']
    await db_manager.update_post(post_id, {'schedule_type': 'one_time'})
    await state.set_state(CreatePost.waiting_for_one_time_schedule)
    await callback.message.edit_text("Отправьте дату и время публикации в формате 'ДД.ММ.ГГГГ ЧЧ:ММ' (например, 31.12.2025 14:30).")
    await callback.answer()

@dp.message(CreatePost.waiting_for_one_time_schedule)
async def process_one_time_schedule(message: Message, state: FSMContext):
    try:
        user_tz = await get_user_timezone(message.chat.id)
        local_dt_str = message.text
        local_dt = datetime.strptime(local_dt_str, "%d.%m.%Y %H:%M")
        localized_dt = user_tz.localize(local_dt)
        utc_dt = localized_dt.astimezone(pytz.utc)

        if utc_dt <= datetime.now(pytz.utc):
            await message.answer("Время должно быть в будущем. Пожалуйста, введите корректную дату и время.")
            return

        data = await state.get_data()
        post_id = data['post_id']
        await db_manager.update_post(post_id, {'scheduled_at': utc_dt})
        
        await state.set_state(CreatePost.waiting_for_deletion_rule)
        await message.answer("Время публикации установлено. Теперь выберите правило удаления:")
        await send_deletion_rule_keyboard(message)

    except ValueError:
        await message.answer("Неверный формат даты/времени. Пожалуйста, используйте 'ДД.ММ.ГГГГ ЧЧ:ММ'.")

@dp.callback_query(CreatePost.waiting_for_send_mode, F.data == "send_cyclic")
async def set_send_cyclic(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    post_id = data['post_id']
    await db_manager.update_post(post_id, {'schedule_type': 'cyclic'})
    await state.set_state(CreatePost.waiting_for_cyclic_schedule_type)
    cyclic_type_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Ежедневно", callback_data="cyclic_daily")],
        [InlineKeyboardButton(text="Еженедельно", callback_data="cyclic_weekly")],
        [InlineKeyboardButton(text="Ежемесячно", callback_data="cyclic_monthly")],
        [InlineKeyboardButton(text="Ежегодно", callback_data="cyclic_yearly")]
    ])
    await callback.message.edit_text("Выберите тип циклического расписания:", reply_markup=cyclic_type_keyboard)
    await callback.answer()

@dp.callback_query(CreatePost.waiting_for_cyclic_schedule_type, F.data.startswith("cyclic_"))
async def process_cyclic_schedule_type(callback: CallbackQuery, state: FSMContext):
    schedule_type = callback.data.split("_")[1]
    data = await state.get_data()
    post_id = data['post_id']
    await db_manager.update_post(post_id, {'schedule_type': schedule_type})
    await state.update_data(cyclic_schedule_type=schedule_type)
    await state.set_state(CreatePost.waiting_for_cyclic_schedule_details)

    prompt = ""
    if schedule_type == 'daily':
        prompt = "Отправьте время публикации в формате 'ЧЧ:ММ' (например, 14:30)."
    elif schedule_type == 'weekly':
        prompt = "Отправьте дни недели (Пн, Вт, Ср...) и время в формате 'Пн,Ср,Пт 10:00'."
    elif schedule_type == 'monthly':
        prompt = "Отправьте число месяца и время в формате '15 10:00' (15-го числа в 10:00)."
    elif schedule_type == 'yearly':
        prompt = "Отправьте день и месяц, а также время в формате '15.03 10:00' (15 марта в 10:00)."
    
    await callback.message.edit_text(prompt)
    await callback.answer()

@dp.message(CreatePost.waiting_for_cyclic_schedule_details)
async def process_cyclic_schedule_details(message: Message, state: FSMContext):
    data = await state.get_data()
    schedule_type = data['cyclic_schedule_type']
    user_tz = await get_user_timezone(message.chat.id)
    cron_expression = None
    local_time = None # Initialize local_time

    try:
        if schedule_type == 'daily':
            time_str = message.text
            local_time = datetime.strptime(time_str, "%H:%M").time()
            cron_expression = f"{local_time.minute} {local_time.hour} * * *"
        elif schedule_type == 'weekly':
            parts = message.text.split(' ')
            days_str = parts[0].lower()
            time_str = parts[1]
            
            days_map = {'пн': 'MON', 'вт': 'TUE', 'ср': 'WED', 'чт': 'THU', 'пт': 'FRI', 'сб': 'SAT', 'вс': 'SUN'}
            selected_days = []
            for day_abbr in days_str.split(','):
                if day_abbr in days_map:
                    selected_days.append(days_map[day_abbr])
                else:
                    raise ValueError("Неверное сокращение дня недели.")
            
            local_time = datetime.strptime(time_str, "%H:%M").time()
            cron_expression = f"{local_time.minute} {local_time.hour} * * {','.join(selected_days)}"
        elif schedule_type == 'monthly':
            parts = message.text.split(' ')
            day_of_month = int(parts[0])
            time_str = parts[1]
            if not (1 <= day_of_month <= 31):
                raise ValueError("Неверное число месяца.")
            local_time = datetime.strptime(time_str, "%H:%M").time()
            cron_expression = f"{local_time.minute} {local_time.hour} {day_of_month} * *"
        elif schedule_type == 'yearly':
            parts = message.text.split(' ')
            date_str = parts[0]
            time_str = parts[1]
            day, month = map(int, date_str.split('.'))
            if not (1 <= day <= 31 and 1 <= month <= 12):
                raise ValueError("Неверный день или месяц.")
            local_time = datetime.strptime(time_str, "%H:%M").time()
            cron_expression = f"{local_time.minute} {local_time.hour} {day} {month} *"
        
        # Convert local time to UTC for cron expression
        # Example: User says 10:00 in +3 TZ. UTC is 7:00. Cron should be "0 7 * * *"
        dummy_date = datetime.now().date() # Any date will do for time conversion
        local_datetime = user_tz.localize(datetime.combine(dummy_date, local_time))
        utc_datetime = local_datetime.astimezone(pytz.utc)
        
        # Reconstruct cron with UTC hour/minute
        cron_parts = cron_expression.split(' ')
        cron_parts[0] = str(utc_datetime.minute)
        cron_parts[1] = str(utc_datetime.hour)
        cron_expression_utc = " ".join(cron_parts)

        post_id = data['post_id']
        await db_manager.update_post(post_id, {'cron_schedule': cron_expression_utc})
        
        await state.set_state(CreatePost.waiting_for_cyclic_schedule_dates)
        await message.answer("Расписание установлено. Теперь отправьте дату начала (ДД.ММ.ГГГГ) или 'сейчас'. Опционально, через пробел, дату окончания (ДД.ММ.ГГГГ) или 'без конца'.\nПример: '01.01.2024 31.12.2024' или 'сейчас без конца'.")

    except ValueError as e:
        await message.answer(f"Неверный формат или значение: {e}. Пожалуйста, попробуйте еще раз.")
    except IndexError:
        await message.answer("Неверный формат. Пожалуйста, убедитесь, что вы указали все необходимые части.")

@dp.message(CreatePost.waiting_for_cyclic_schedule_dates)
async def process_cyclic_schedule_dates(message: Message, state: FSMContext):
    parts = message.text.lower().split(' ')
    start_date = None
    end_date = None

    try:
        if parts[0] == 'сейчас':
            start_date = datetime.now().date()
        else:
            start_date = datetime.strptime(parts[0], "%d.%m.%Y").date()
        
        if len(parts) > 1:
            if parts[1] != 'без конца':
                end_date = datetime.strptime(parts[1], "%d.%m.%Y").date()
        
        if start_date and end_date and start_date > end_date:
            await message.answer("Дата начала не может быть позже даты окончания. Пожалуйста, введите корректные даты.")
            return

        data = await state.get_data()
        post_id = data['post_id']
        await db_manager.update_post(post_id, {'start_date': start_date, 'end_date': end_date})
        
        await state.set_state(CreatePost.waiting_for_deletion_rule)
        await message.answer("Даты расписания установлены. Теперь выберите правило удаления:")
        await send_deletion_rule_keyboard(message)

    except ValueError:
        await message.answer("Неверный формат даты. Пожалуйста, используйте 'ДД.ММ.ГГГГ'.")

async def send_deletion_rule_keyboard(message: Message):
    deletion_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Не удалять", callback_data="delete_never")],
        [InlineKeyboardButton(text="Удалить через N часов", callback_data="delete_hours")],
        [InlineKeyboardButton(text="Удалить через N дней", callback_data="delete_days")],
        [InlineKeyboardButton(text="Удалить в конкретную дату и время", callback_data="delete_specific_date")]
    ])
    await message.answer("Выберите правило удаления поста после публикации:", reply_markup=deletion_keyboard)

@dp.callback_query(CreatePost.waiting_for_deletion_rule, F.data.startswith("delete_"))
async def process_deletion_rule_type(callback: CallbackQuery, state: FSMContext):
    delete_type = callback.data.split("_")[1]
    data = await state.get_data()
    post_id = data['post_id']

    if delete_type == 'never':
        await db_manager.update_post(post_id, {'delete_after_publish_type': 'never', 'delete_after_publish_value': None, 'delete_at': None})
        await state.set_state(CreatePost.waiting_for_confirmation)
        await send_post_preview(callback.message, state)
    elif delete_type in ['hours', 'days']:
        await state.update_data(delete_type=delete_type)
        await state.set_state(CreatePost.waiting_for_deletion_value)
        unit = "часов" if delete_type == 'hours' else "дней"
        await callback.message.edit_text(f"Через сколько {unit} после публикации удалить пост? Отправьте число.")
    elif delete_type == 'specific_date':
        await state.update_data(delete_type=delete_type)
        await state.set_state(CreatePost.waiting_for_deletion_specific_date)
        await callback.message.edit_text("Отправьте дату и время удаления в формате 'ДД.ММ.ГГГГ ЧЧ:ММ'.")
    
    await callback.answer()

@dp.message(CreatePost.waiting_for_deletion_value)
async def process_deletion_value(message: Message, state: FSMContext):
    try:
        value = int(message.text)
        if value <= 0:
            raise ValueError
        
        data = await state.get_data()
        post_id = data['post_id']
        delete_type = data['delete_type']
        
        await db_manager.update_post(post_id, {
            'delete_after_publish_type': delete_type,
            'delete_after_publish_value': value,
            'delete_at': None
        })
        
        await state.set_state(CreatePost.waiting_for_confirmation)
        await send_post_preview(message, state)

    except ValueError:
        await message.answer("Неверное число. Пожалуйста, отправьте положительное целое число.")

@dp.message(CreatePost.waiting_for_deletion_specific_date)
async def process_deletion_specific_date(message: Message, state: FSMContext):
    try:
        user_tz = await get_user_timezone(message.chat.id)
        local_dt_str = message.text
        local_dt = datetime.strptime(local_dt_str, "%d.%m.%Y %H:%M")
        localized_dt = user_tz.localize(local_dt)
        utc_dt = localized_dt.astimezone(pytz.utc)

        if utc_dt <= datetime.now(pytz.utc):
            await message.answer("Время удаления должно быть в будущем. Пожалуйста, введите корректную дату и время.")
            return

        data = await state.get_data()
        post_id = data['post_id']
        await db_manager.update_post(post_id, {
            'delete_after_publish_type': 'specific_date',
            'delete_after_publish_value': None,
            'delete_at': utc_dt
        })
        
        await state.set_state(CreatePost.waiting_for_confirmation)
        await send_post_preview(message, state)

    except ValueError:
        await message.answer("Неверный формат даты/времени. Пожалуйста, используйте 'ДД.ММ.ГГГГ ЧЧ:ММ'.")

async def send_post_preview(message: Message, state: FSMContext):
    data = await state.get_data()
    post_id = data['post_id']
    user_db_id = data['user_db_id']
    
    post_data = await db_manager.get_post(post_id)
    media_files = await db_manager.get_post_media(post_id)
    buttons_data = await db_manager.get_post_buttons(post_id)
    channels_data = await db_manager.get_post_channels(post_id)
    user_tz = await get_user_timezone(message.chat.id)

    # Add user_timezone to post_data for formatting deletion info
    post_data['user_timezone'] = user_tz.tzname(datetime.now())

    schedule_info = get_schedule_info_string(post_data, user_tz)
    deletion_info = get_deletion_info_string(post_data)

    preview_text = format_post_preview(post_data, channels_data, len(media_files), buttons_data, schedule_info, deletion_info)
    
    confirmation_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Подтвердить и отправить/сохранить", callback_data="confirm_post")],
        [InlineKeyboardButton(text="Отмена", callback_data="cancel_post")]
    ])

    # Send actual media for preview
    if media_files:
        # Separate documents from photos/videos for media group
        doc_media = [m for m in media_files if m['media_type'] == 'document']
        other_media = [m for m in media_files if m['media_type'] != 'document']

        # Send documents first, one by one
        for i, media in enumerate(doc_media):
            caption = post_data['text'] if i == 0 and not other_media else None
            await message.answer_document(document=media['telegram_file_id'], caption=caption, reply_markup=telegram_utils.create_inline_buttons(buttons_data) if buttons_data and i == 0 and not other_media else None)
        
        # Send photo/video media group
        if other_media:
            media_group = []
            for i, media in enumerate(other_media):
                caption = post_data['text'] if i == 0 and not doc_media else None # Only first item of this group gets caption
                if media['media_type'] == 'photo':
                    media_group.append(InputMediaPhoto(media=media['telegram_file_id'], caption=caption))
                elif media['media_type'] == 'video':
                    media_group.append(InputMediaVideo(media=media['telegram_file_id'], caption=caption))
            
            if media_group:
                try:
                    await message.answer_media_group(media=media_group)
                except TelegramBadRequest as e:
                    logger.error(f"Failed to send media group for preview: {e}")
                    await message.answer("Не удалось отобразить медиа для предпросмотра. Возможно, проблема с файлами.")
    
    # Send text and buttons separately if no media was sent at all
    if not media_files:
        await message.answer(post_data['text'] if post_data['text'] else "<i>Без текста</i>", reply_markup=telegram_utils.create_inline_buttons(buttons_data) if buttons_data else None)
    
    await message.answer(preview_text, reply_markup=confirmation_keyboard)

@dp.callback_query(CreatePost.waiting_for_confirmation, F.data == "confirm_post")
async def confirm_post(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    post_id = data['post_id']
    post_data = await db_manager.get_post(post_id)

    if post_data['schedule_type'] is None: # Instant send
        media_files = await db_manager.get_post_media(post_id)
        buttons_data = await db_manager.get_post_buttons(post_id)
        channels_data = await db_manager.get_post_channels(post_id)
        
        for pc_data in channels_data:
            channel_info = pc_data['channels']
            if channel_info:
                try:
                    sent_message = await telegram_utils.send_post_to_channel( # Use telegram_utils
                        bot,
                        channel_info['telegram_channel_id'],
                        post_data['text'],
                        media_files,
                        buttons_data
                    )
                    
                    if post_data['delete_after_publish_type'] != 'never':
                        delete_time = None
                        if post_data['delete_after_publish_type'] == 'hours':
                            delete_time = datetime.now(pytz.utc) + timedelta(hours=post_data['delete_after_publish_value'])
                        elif post_data['delete_after_publish_type'] == 'days':
                            delete_time = datetime.now(pytz.utc) + timedelta(days=post_data['delete_after_publish_value'])
                        elif post_data['delete_after_publish_type'] == 'specific_date':
                            delete_time = post_data['delete_at']
                        
                        if delete_time and sent_message: # Only schedule if message was sent
                            # This is a simplification. In a real system, you'd store sent_message_id in post_channels table.
                            scheduler.add_one_time_job(
                                job_func=scheduler._delete_post_job,
                                run_date=delete_time,
                                args=[post_id, [{'channel_id': channel_info['id'], 'message_id': sent_message.message_id}]],
                                job_id=f"delete_post_{post_id}_{delete_time.timestamp()}"
                            )
                            logger.info(f"Deletion job for instant post {post_id} scheduled for {delete_time}.")

                except Exception as e:
                    logger.error(f"Failed to send instant post {post_id} to channel {channel_info['channel_name']}: {e}")
        
        await db_manager.update_post(post_id, {'status': 'sent'})
        await callback.message.edit_text("Пост успешно отправлен!")

    else: # Scheduled post
        await db_manager.update_post(post_id, {'status': 'scheduled'})
        
        job_id = f"send_post_{post_id}"
        if post_data['schedule_type'] == 'one_time':
            scheduler.add_one_time_job(scheduler._send_post_job, post_data['scheduled_at'], args=[post_id], job_id=job_id)
        else: # Cyclic
            # Need to pass start_date and end_date to scheduler.add_recurring_job
            start_date = post_data.get('start_date')
            end_date = post_data.get('end_date')
            scheduler.add_recurring_job(scheduler._send_post_job, post_data['cron_schedule'], args=[post_id], job_id=job_id, start_date=start_date, end_date=end_date)
        
        await callback.message.edit_text("Пост успешно запланирован!")
    
    await state.clear()
    await callback.answer()

@dp.callback_query(CreatePost.waiting_for_confirmation, F.data == "cancel_post")
async def cancel_post_creation(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    post_id = data['post_id']
    await db_manager.delete_post_full(post_id)
    await state.clear()
    await callback.message.edit_text("Создание поста отменено.")
    await callback.answer()

# --- Manage Channels ---

@dp.message(F.text.lower() == "добавить канал")
async def add_channel_start(message: Message, state: FSMContext):
    await state.set_state(ManageChannels.waiting_for_channel_to_add)
    await message.answer("Отправьте имя пользователя канала (например, @mychannel) или его ID.")

@dp.message(ManageChannels.waiting_for_channel_to_add)
async def process_channel_to_add(message: Message, state: FSMContext):
    channel_identifier = message.text.strip()
    if channel_identifier.startswith('@'):
        channel_identifier = channel_identifier
    else:
        try:
            channel_identifier = int(channel_identifier) # Try to convert to int if it's an ID
        except ValueError:
            await message.answer("Неверный формат. Пожалуйста, используйте @username или числовой ID канала.")
            return

    channel_info = await telegram_utils.get_channel_info(bot, channel_identifier) # Use telegram_utils
    if not channel_info:
        await message.answer("Канал не найден или я не могу получить информацию о нем. Убедитесь, что бот добавлен в канал и имеет права администратора.")
        await state.clear()
        return

    channel_id, channel_name = channel_info
    
    # Check bot's admin rights
    if not await telegram_utils.check_bot_admin_in_channel(bot, channel_id): # Use telegram_utils
        await message.answer(f"Бот не является администратором в канале '{channel_name}'. Пожалуйста, дайте боту права администратора, чтобы он мог публиковать посты.")
        await state.clear()
        return

    # Check user's admin rights
    if not await telegram_utils.check_user_admin_in_channel(bot, channel_id, message.from_user.id): # Use telegram_utils
        await message.answer(f"Вы не являетесь администратором в канале '{channel_name}'. Вы должны быть администратором, чтобы добавлять этот канал.")
        await state.clear()
        return
    
    user_db_id, _ = await get_user_db_id(message.chat.id, message.from_user.username, message.from_user.first_name, message.from_user.last_name)
    try:
        await db_manager.add_channel(user_db_id, channel_id, channel_name)
        await message.answer(f"Канал '{channel_name}' успешно добавлен!")
    except Exception as e:
        logger.error(f"Error adding channel to DB: {e}")
        await message.answer("Произошла ошибка при добавлении канала. Возможно, он уже добавлен.")
    
    await state.clear()

@dp.message(F.text.lower() == "удалить канал")
async def delete_channel_start(message: Message, state: FSMContext):
    user_db_id, _ = await get_user_db_id(message.chat.id, message.from_user.username, message.from_user.first_name, message.from_user.last_name)
    user_channels = await db_manager.get_user_channels(user_db_id)

    if not user_channels:
        await message.answer("У вас нет добавленных каналов.")
        await state.clear()
        return

    channels_text = "Выберите канал для удаления (отправьте его номер):\n"
    for i, ch in enumerate(user_channels):
        channels_text += f"{i+1}. {ch['channel_name']} (ID: {ch['telegram_channel_id']})\n"
    
    await state.update_data(user_channels_map={str(i+1): ch['id'] for i, ch in enumerate(user_channels)})
    await state.set_state(ManageChannels.waiting_for_channel_to_delete)
    await message.answer(channels_text)

@dp.message(ManageChannels.waiting_for_channel_to_delete)
async def process_channel_to_delete(message: Message, state: FSMContext):
    data = await state.get_data()
    user_channels_map = data.get('user_channels_map')
    
    if message.text not in user_channels_map:
        await message.answer("Неверный номер канала. Пожалуйста, выберите номер из списка.")
        return

    channel_db_id_to_delete = user_channels_map[message.text]
    channel_info = await db_manager.get_channel_by_id(channel_db_id_to_delete)
    
    user_db_id, _ = await get_user_db_id(message.chat.id, message.from_user.username, message.from_user.first_name, message.from_user.last_name)
    await db_manager.deactivate_channel(user_db_id, channel_db_id_to_delete) # Pass channel_db_id, not telegram_channel_id
    await message.answer(f"Канал '{channel_info['channel_name']}' успешно удален из вашего списка.")

    # Check and update related scheduled posts
    posts_affected = await db_manager.get_posts_by_channel_id(channel_db_id_to_delete)
    for post_id in posts_affected:
        await db_manager.remove_channel_from_post(post_id, channel_db_id_to_delete)
        remaining_channels_count = await db_manager.get_post_channel_count(post_id)
        if remaining_channels_count == 0:
            post_data = await db_manager.get_post(post_id)
            if post_data and post_data['status'] == 'scheduled':
                # Cancel the post if it has no channels left
                scheduler.remove_job(f"send_post_{post_id}")
                await db_manager.update_post(post_id, {'status': 'cancelled'})
                await message.answer(f"Запланированный пост ID: {post_id} был отменен, так как все его каналы были удалены.")
    
    await state.clear()

@dp.message(F.text.lower() == "просмотр каналов")
async def view_channels(message: Message, state: FSMContext):
    user_db_id, _ = await get_user_db_id(message.chat.id, message.from_user.username, message.from_user.first_name, message.from_user.last_name)
    user_channels = await db_manager.get_user_channels(user_db_id)

    if not user_channels:
        await message.answer("У вас пока нет добавленных каналов. Используйте 'добавить канал', чтобы добавить первый.")
        return

    channels_text = "Ваши активные каналы:\n"
    for ch in user_channels:
        channels_text += f"- {ch['channel_name']} (ID: {ch['telegram_channel_id']})\n"
    
    await message.answer(channels_text)

# --- View and Edit Scheduled Posts ---

@dp.message(F.text.lower() == "просмотр постов")
async def view_scheduled_posts(message: Message, state: FSMContext):
    user_db_id, user_tz_str = await get_user_db_id(message.chat.id, message.from_user.username, message.from_user.first_name, message.from_user.last_name)
    user_tz = pytz.timezone(user_tz_str)
    
    posts = await db_manager.get_scheduled_posts(user_db_id)

    if not posts:
        await message.answer("У вас нет запланированных постов.")
        return

    response_text = "Ваши запланированные посты:\n\n"
    for post in posts:
        post_id = post['id']
        text_snippet = (post['text'][:50] + "...") if post['text'] and len(post['text']) > 50 else (post['text'] if post['text'] else "<i>Без текста</i>")
        
        channels_names = ", ".join([pc['channels']['channel_name'] for pc in post['post_channels'] if pc['channels']]) if post['post_channels'] else "Не выбраны"
        
        # Pass user_timezone to get_deletion_info_string
        post['user_timezone'] = user_tz_str
        schedule_info = get_schedule_info_string(post, user_tz)
        deletion_info = get_deletion_info_string(post)

        response_text += (
            f"<b>ID поста:</b> <code>{post_id}</code>\n"
            f"<b>Текст:</b> {text_snippet}\n"
            f"<b>Каналы:</b> {channels_names}\n"
            f"<b>Расписание:</b> {schedule_info}\n"
            f"<b>Удаление:</b> {deletion_info}\n\n"
        )
    
    response_text += "Чтобы изменить пост, используйте команду 'редактировать пост [ID]'.\n"
    response_text += "Чтобы отменить пост, используйте команду 'отменить пост [ID]'."
    
    await message.answer(response_text)

@dp.message(Command("редактировать_пост"))
async def edit_post_start(message: Message, state: FSMContext):
    parts = message.text.split(' ')
    if len(parts) < 2:
        await message.answer("Пожалуйста, укажите ID поста. Пример: 'редактировать пост 123e4567-e89b-12d3-a456-426614174000'")
        return
    
    post_id = parts[1]
    post = await db_manager.get_post(post_id)
    user_db_id, _ = await get_user_db_id(message.chat.id, message.from_user.username, message.from_user.first_name, message.from_user.last_name)

    if not post or post['user_id'] != user_db_id:
        await message.answer("Пост с таким ID не найден или вы не являетесь его владельцем.")
        return
    
    await state.update_data(post_id=post_id, user_db_id=user_db_id)
    await state.set_state(EditPost.waiting_for_edit_choice)
    
    edit_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Изменить текст", callback_data="edit_text")],
        [InlineKeyboardButton(text="Изменить медиа", callback_data="edit_media")],
        [InlineKeyboardButton(text="Изменить кнопки", callback_data="edit_buttons")],
        [InlineKeyboardButton(text="Изменить каналы", callback_data="edit_channels")],
        [InlineKeyboardButton(text="Изменить расписание", callback_data="edit_schedule")],
        [InlineKeyboardButton(text="Изменить правило удаления", callback_data="edit_deletion")],
        [InlineKeyboardButton(text="Завершить редактирование", callback_data="edit_done")]
    ])
    await message.answer("Что вы хотите изменить в посте?", reply_markup=edit_keyboard)

@dp.callback_query(EditPost.waiting_for_edit_choice, F.data.startswith("edit_"))
async def process_edit_choice(callback: CallbackQuery, state: FSMContext):
    choice = callback.data.split("_")[1]
    data = await state.get_data()
    post_id = data['post_id']
    
    if choice == 'text':
        await state.set_state(EditPost.editing_text)
        await callback.message.edit_text("Отправьте новый текст для поста (или '–' если без текста).")
    elif choice == 'media':
        await db_manager.delete_post_media(post_id) # Clear existing media
        await state.set_state(EditPost.editing_media)
        await callback.message.edit_text("Отправьте новые медиа (фото, видео, документ). Когда закончите, напишите 'готово' или 'пропустить'.")
    elif choice == 'buttons':
        await db_manager.delete_post_buttons(post_id) # Clear existing buttons
        await state.set_state(EditPost.editing_buttons)
        await callback.message.edit_text("Отправьте новые кнопки в формате 'Текст | Ссылка'. Каждая кнопка на новой строке. Если кнопки не нужны, отправьте '–'.")
    elif choice == 'channels':
        user_channels = await db_manager.get_user_channels(data['user_db_id'])
        if not user_channels:
            await callback.message.edit_text("У вас нет добавленных каналов. Пожалуйста, сначала добавьте канал с помощью команды 'добавить канал'.")
            await state.set_state(EditPost.waiting_for_edit_choice) # Stay in edit mode
            return
        
        channels_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=ch['channel_name'], callback_data=f"select_channel_{ch['id']}")] for ch in user_channels
        ] + [[InlineKeyboardButton(text="Завершить выбор каналов", callback_data="done_channels_edit")]])
        
        await state.set_state(EditPost.editing_channels)
        await callback.message.edit_text("Выберите один или несколько каналов для публикации:", reply_markup=channels_keyboard)
    elif choice == 'schedule':
        await state.set_state(EditPost.editing_schedule_mode)
        send_mode_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Мгновенно", callback_data="send_instant_edit")],
            [InlineKeyboardButton(text="Отложить разово", callback_data="send_one_time_edit")],
            [InlineKeyboardButton(text="Запланировать циклически", callback_data="send_cyclic_edit")]
        ])
        await callback.message.edit_text("Выберите новый режим отправки поста:", reply_markup=send_mode_keyboard)
    elif choice == 'deletion':
        await state.set_state(EditPost.editing_deletion_rule)
        await callback.message.edit_text("Выберите новое правило удаления:")
        await send_deletion_rule_keyboard(callback.message)
    elif choice == 'done':
        # When editing is done, re-schedule the post if it was scheduled
        post_data = await db_manager.get_post(post_id)
        if post_data['status'] == 'scheduled':
            # Remove old job
            scheduler.remove_job(f"send_post_{post_id}")
            # Add new job
            job_id = f"send_post_{post_id}"
            if post_data['schedule_type'] == 'one_time':
                scheduler.add_one_time_job(scheduler._send_post_job, post_data['scheduled_at'], args=[post_id], job_id=job_id)
            else: # Cyclic
                start_date = post_data.get('start_date')
                end_date = post_data.get('end_date')
                scheduler.add_recurring_job(scheduler._send_post_job, post_data['cron_schedule'], args=[post_id], job_id=job_id, start_date=start_date, end_date=end_date)
            await callback.message.edit_text("Редактирование завершено. Пост обновлен и перепланирован.")
        else:
            await callback.message.edit_text("Редактирование завершено.")
        await state.clear()
        await callback.answer()
        return
    
    await callback.answer()

# Handlers for editing specific fields (reusing logic from CreatePost where possible)
@dp.message(EditPost.editing_text)
async def edit_post_text(message: Message, state: FSMContext):
    post_text = message.text
    if post_text == '–':
        post_text = None
    data = await state.get_data()
    post_id = data['post_id']
    await db_manager.update_post(post_id, {'text': post_text})
    await message.answer("Текст обновлен.")
    # Use callback.message if available, otherwise message
    target_message = message if message.text else callback.message # This is a hack, better to pass message object
    await edit_post_start(target_message, state) # Go back to edit menu

@dp.message(EditPost.editing_media, F.text.lower() == "готово")
@dp.message(EditPost.editing_media, F.text.lower() == "пропустить")
async def edit_media_done(message: Message, state: FSMContext):
    data = await state.get_data()
    post_id = data['post_id']
    media_files = await db_manager.get_post_media(post_id)
    if not media_files and message.text.lower() == "готово":
        await message.answer("Вы не прикрепили ни одного медиафайла. Если медиа не нужны, напишите 'пропустить'.")
        return
    await message.answer("Медиа обновлены.")
    target_message = message if message.text else callback.message # This is a hack, better to pass message object
    await edit_post_start(target_message, state)

@dp.message(EditPost.editing_media, F.photo | F.video | F.document)
async def edit_media_file(message: Message, state: FSMContext):
    await process_media_file(message, state) # Reuse logic
    await message.answer("Медиафайл добавлен. Отправьте еще или напишите 'готово' / 'пропустить'.")

@dp.message(EditPost.editing_buttons)
async def edit_post_buttons(message: Message, state: FSMContext):
    buttons_text = message.text
    data = await state.get_data()
    post_id = data['post_id']
    
    await db_manager.delete_post_buttons(post_id) # Clear previous buttons

    if buttons_text != '–':
        button_lines = buttons_text.split('\n')
        for i, line in enumerate(button_lines):
            parts = line.split('|', 1)
            if len(parts) == 2:
                button_text = parts[0].strip()
                button_url = parts[1].strip()
                if button_text and button_url:
                    await db_manager.add_post_button(post_id, button_text, button_url, i)
                else:
                    await message.answer(f"Ошибка в формате кнопки '{line}'. Пропускаю. Используйте 'Текст | Ссылка'.")
            else:
                await message.answer(f"Ошибка в формате кнопки '{line}'. Пропускаю. Используйте 'Текст | Ссылка'.")
    
    await message.answer("Кнопки обновлены.")
    target_message = message if message.text else callback.message # This is a hack, better to pass message object
    await edit_post_start(target_message, state)

@dp.callback_query(EditPost.editing_channels, F.data.startswith("select_channel_"))
async def edit_select_channel_callback(callback: CallbackQuery, state: FSMContext):
    await select_channel_callback(callback, state) # Reuse logic

@dp.callback_query(EditPost.editing_channels, F.data == "done_channels_edit")
async def edit_done_channels_callback(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected_channels = data.get('selected_channels', [])
    
    if not selected_channels:
        await callback.answer("Пожалуйста, выберите хотя бы один канал.", show_alert=True)
        return

    post_id = data['post_id']
    # Clear previous channels for this post
    await db_manager.delete_post_channels(post_id)
    for channel_db_id in selected_channels:
        await db_manager.add_post_channel(post_id, channel_db_id)
    
    await callback.message.edit_text("Каналы обновлены.")
    await edit_post_start(callback.message, state) # Go back to edit menu
    await callback.answer()

# Schedule editing
@dp.callback_query(EditPost.editing_schedule_mode, F.data == "send_instant_edit")
async def edit_set_send_instant(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    post_id = data['post_id']
    await db_manager.update_post(post_id, {'schedule_type': None, 'scheduled_at': None, 'cron_schedule': None, 'start_date': None, 'end_date': None})
    await callback.message.edit_text("Режим отправки изменен на мгновенный.")
    await edit_post_start(callback.message, state)
    await callback.answer()

@dp.callback_query(EditPost.editing_schedule_mode, F.data == "send_one_time_edit")
async def edit_set_send_one_time(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    post_id = data['post_id']
    await db_manager.update_post(post_id, {'schedule_type': 'one_time'})
    await state.set_state(EditPost.editing_one_time_schedule)
    await callback.message.edit_text("Отправьте новую дату и время публикации в формате 'ДД.ММ.ГГГГ ЧЧ:ММ'.")
    await callback.answer()

@dp.message(EditPost.editing_one_time_schedule)
async def edit_process_one_time_schedule(message: Message, state: FSMContext):
    try:
        user_tz = await get_user_timezone(message.chat.id)
        local_dt_str = message.text
        local_dt = datetime.strptime(local_dt_str, "%d.%m.%Y %H:%M")
        localized_dt = user_tz.localize(local_dt)
        utc_dt = localized_dt.astimezone(pytz.utc)

        if utc_dt <= datetime.now(pytz.utc):
            await message.answer("Время должно быть в будущем. Пожалуйста, введите корректную дату и время.")
            return

        data = await state.get_data()
        post_id = data['post_id']
        await db_manager.update_post(post_id, {'scheduled_at': utc_dt})
        
        await message.answer("Время публикации обновлено.")
        target_message = message if message.text else callback.message # This is a hack, better to pass message object
        await edit_post_start(target_message, state)

    except ValueError:
        await message.answer("Неверный формат даты/времени. Пожалуйста, используйте 'ДД.ММ.ГГГГ ЧЧ:ММ'.")

@dp.callback_query(EditPost.editing_schedule_mode, F.data == "send_cyclic_edit")
async def edit_set_send_cyclic(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    post_id = data['post_id']
    await db_manager.update_post(post_id, {'schedule_type': 'cyclic'})
    await state.set_state(EditPost.editing_cyclic_schedule_type)
    cyclic_type_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Ежедневно", callback_data="cyclic_daily_edit")],
        [InlineKeyboardButton(text="Еженедельно", callback_data="cyclic_weekly_edit")],
        [InlineKeyboardButton(text="Ежемесячно", callback_data="cyclic_monthly_edit")],
        [InlineKeyboardButton(text="Ежегодно", callback_data="cyclic_yearly_edit")]
    ])
    await callback.message.edit_text("Выберите новый тип циклического расписания:", reply_markup=cyclic_type_keyboard)
    await callback.answer()

@dp.callback_query(EditPost.editing_cyclic_schedule_type, F.data.startswith("cyclic_"))
async def edit_process_cyclic_schedule_type(callback: CallbackQuery, state: FSMContext):
    schedule_type = callback.data.replace("cyclic_", "").replace("_edit", "") # Remove '_edit' suffix
    data = await state.get_data()
    post_id = data['post_id']
    await db_manager.update_post(post_id, {'schedule_type': schedule_type})
    await state.update_data(cyclic_schedule_type=schedule_type)
    await state.set_state(EditPost.editing_cyclic_schedule_details)

    prompt = ""
    if schedule_type == 'daily':
        prompt = "Отправьте время публикации в формате 'ЧЧ:ММ' (например, 14:30)."
    elif schedule_type == 'weekly':
        prompt = "Отправьте дни недели (Пн, Вт, Ср...) и время в формате 'Пн,Ср,Пт 10:00'."
    elif schedule_type == 'monthly':
        prompt = "Отправьте число месяца и время в формате '15 10:00' (15-го числа в 10:00)."
    elif schedule_type == 'yearly':
        prompt = "Отправьте день и месяц, а также время в формате '15.03 10:00' (15 марта в 10:00)."
    
    await callback.message.edit_text(prompt)
    await callback.answer()

@dp.message(EditPost.editing_cyclic_schedule_details)
async def edit_process_cyclic_schedule_details(message: Message, state: FSMContext):
    data = await state.get_data()
    schedule_type = data['cyclic_schedule_type']
    user_tz = await get_user_timezone(message.chat.id)
    cron_expression = None
    local_time = None # Initialize local_time

    try:
        if schedule_type == 'daily':
            time_str = message.text
            local_time = datetime.strptime(time_str, "%H:%M").time()
            cron_expression = f"{local_time.minute} {local_time.hour} * * *"
        elif schedule_type == 'weekly':
            parts = message.text.split(' ')
            days_str = parts[0].lower()
            time_str = parts[1]
            
            days_map = {'пн': 'MON', 'вт': 'TUE', 'ср': 'WED', 'чт': 'THU', 'пт': 'FRI', 'сб': 'SAT', 'вс': 'SUN'}
            selected_days = []
            for day_abbr in days_str.split(','):
                if day_abbr in days_map:
                    selected_days.append(days_map[day_abbr])
                else:
                    raise ValueError("Неверное сокращение дня недели.")
            
            local_time = datetime.strptime(time_str, "%H:%M").time()
            cron_expression = f"{local_time.minute} {local_time.hour} * * {','.join(selected_days)}"
        elif schedule_type == 'monthly':
            parts = message.text.split(' ')
            day_of_month = int(parts[0])
            time_str = parts[1]
            if not (1 <= day_of_month <= 31):
                raise ValueError("Неверное число месяца.")
            local_time = datetime.strptime(time_str, "%H:%M").time()
            cron_expression = f"{local_time.minute} {local_time.hour} {day_of_month} * *"
        elif schedule_type == 'yearly':
            parts = message.text.split(' ')
            date_str = parts[0]
            time_str = parts[1]
            day, month = map(int, date_str.split('.'))
            if not (1 <= day <= 31 and 1 <= month <= 12):
                raise ValueError("Неверный день или месяц.")
            local_time = datetime.strptime(time_str, "%H:%M").time()
            cron_expression = f"{local_time.minute} {local_time.hour} {day} {month} *"
        
        dummy_date = datetime.now().date()
        local_datetime = user_tz.localize(datetime.combine(dummy_date, local_time))
        utc_datetime = local_datetime.astimezone(pytz.utc)
        
        cron_parts = cron_expression.split(' ')
        cron_parts[0] = str(utc_datetime.minute)
        cron_parts[1] = str(utc_datetime.hour)
        cron_expression_utc = " ".join(cron_parts)

        post_id = data['post_id']
        await db_manager.update_post(post_id, {'cron_schedule': cron_expression_utc})
        
        await state.set_state(EditPost.editing_cyclic_schedule_dates)
        await message.answer("Расписание установлено. Теперь отправьте дату начала (ДД.ММ.ГГГГ) или 'сейчас'. Опционально, через пробел, дату окончания (ДД.ММ.ГГГГ) или 'без конца'.\nПример: '01.01.2024 31.12.2024' или 'сейчас без конца'.")

    except ValueError as e:
        await message.answer(f"Неверный формат или значение: {e}. Пожалуйста, попробуйте еще раз.")
    except IndexError:
        await message.answer("Неверный формат. Пожалуйста, убедитесь, что вы указали все необходимые части.")

@dp.message(EditPost.editing_cyclic_schedule_dates)
async def edit_process_cyclic_schedule_dates(message: Message, state: FSMContext):
    parts = message.text.lower().split(' ')
    start_date = None
    end_date = None

    try:
        if parts[0] == 'сейчас':
            start_date = datetime.now().date()
        else:
            start_date = datetime.strptime(parts[0], "%d.%m.%Y").date()
        
        if len(parts) > 1:
            if parts[1] != 'без конца':
                end_date = datetime.strptime(parts[1], "%d.%m.%Y").date()
        
        if start_date and end_date and start_date > end_date:
            await message.answer("Дата начала не может быть позже даты окончания. Пожалуйста, введите корректные даты.")
            return

        data = await state.get_data()
        post_id = data['post_id']
        await db_manager.update_post(post_id, {'start_date': start_date, 'end_date': end_date})
        
        await message.answer("Даты расписания обновлены.")
        target_message = message if message.text else callback.message # This is a hack, better to pass message object
        await edit_post_start(target_message, state)

    except ValueError:
        await message.answer("Неверный формат даты. Пожалуйста, используйте 'ДД.ММ.ГГГГ'.")

# Deletion rule editing
@dp.callback_query(EditPost.editing_deletion_rule, F.data.startswith("delete_"))
async def edit_process_deletion_rule_type(callback: CallbackQuery, state: FSMContext):
    delete_type = callback.data.split("_")[1]
    data = await state.get_data()
    post_id = data['post_id']

    if delete_type == 'never':
        await db_manager.update_post(post_id, {'delete_after_publish_type': 'never', 'delete_after_publish_value': None, 'delete_at': None})
        await callback.message.edit_text("Правило удаления обновлено.")
        await edit_post_start(callback.message, state)
    elif delete_type in ['hours', 'days']:
        await state.update_data(delete_type=delete_type)
        await state.set_state(EditPost.editing_deletion_value)
        unit = "часов" if delete_type == 'hours' else "дней"
        await callback.message.edit_text(f"Через сколько {unit} после публикации удалить пост? Отправьте число.")
    elif delete_type == 'specific_date':
        await state.update_data(delete_type=delete_type)
        await state.set_state(EditPost.editing_deletion_specific_date)
        await callback.message.edit_text("Отправьте дату и время удаления в формате 'ДД.ММ.ГГГГ ЧЧ:ММ'.")
    
    await callback.answer()

@dp.message(EditPost.editing_deletion_value)
async def edit_process_deletion_value(message: Message, state: FSMContext):
    try:
        value = int(message.text)
        if value <= 0:
            raise ValueError
        
        data = await state.get_data()
        post_id = data['post_id']
        delete_type = data['delete_type']
        
        await db_manager.update_post(post_id, {
            'delete_after_publish_type': delete_type,
            'delete_after_publish_value': value,
            'delete_at': None
        })
        
        await message.answer("Правило удаления обновлено.")
        target_message = message if message.text else callback.message # This is a hack, better to pass message object
        await edit_post_start(target_message, state)

    except ValueError:
        await message.answer("Неверное число. Пожалуйста, отправьте положительное целое число.")

@dp.message(EditPost.editing_deletion_specific_date)
async def edit_process_deletion_specific_date(message: Message, state: FSMContext):
    try:
        user_tz = await get_user_timezone(message.chat.id)
        local_dt_str = message.text
        local_dt = datetime.strptime(local_dt_str, "%d.%m.%Y %H:%M")
        localized_dt = user_tz.localize(local_dt)
        utc_dt = localized_dt.astimezone(pytz.utc)

        if utc_dt <= datetime.now(pytz.utc):
            await message.answer("Время удаления должно быть в будущем. Пожалуйста, введите корректную дату и время.")
            return

        data = await state.get_data()
        post_id = data['post_id']
        await db_manager.update_post(post_id, {
            'delete_after_publish_type': 'specific_date',
            'delete_after_publish_value': None,
            'delete_at': utc_dt
        })
        
        await message.answer("Правило удаления обновлено.")
        target_message = message if message.text else callback.message # This is a hack, better to pass message object
        await edit_post_start(target_message, state)

    except ValueError:
        await message.answer("Неверный формат даты/времени. Пожалуйста, используйте 'ДД.ММ.ГГГГ ЧЧ:ММ'.")

# --- Delete Post ---

@dp.message(Command("отменить_пост"))
async def delete_post_command(message: Message, state: FSMContext):
    parts = message.text.split(' ')
    if len(parts) < 2:
        await message.answer("Пожалуйста, укажите ID поста. Пример: 'отменить пост 123e4567-e89b-12d3-a456-426614174000'")
        return
    
    post_id = parts[1]
    post = await db_manager.get_post(post_id)
    user_db_id, _ = await get_user_db_id(message.chat.id, message.from_user.username, message.from_user.first_name, message.from_user.last_name)

    if not post or post['user_id'] != user_db_id:
        await message.answer("Пост с таким ID не найден или вы не являетесь его владельцем.")
        return
    
    # Remove from scheduler
    scheduler.remove_job(f"send_post_{post_id}")
    # Remove from DB
    await db_manager.delete_post_full(post_id)
    
    await message.answer(f"Пост ID: {post_id} успешно отменен и удален.")
    await state.clear()

# --- Change Timezone ---

@dp.message(F.text.lower() == "сменить часовой пояс")
async def change_timezone_start(message: Message, state: FSMContext):
    await state.set_state(ChangeTimezone.waiting_for_timezone)
    await message.answer("Отправьте ваш часовой пояс в формате IANA (например, 'Europe/Moscow' или 'America/New_York').")

@dp.message(ChangeTimezone.waiting_for_timezone)
async def process_timezone(message: Message, state: FSMContext):
    timezone_str = message.text.strip()
    try:
        pytz.timezone(timezone_str) # Validate timezone string
        user_db_id, _ = await get_user_db_id(message.chat.id, message.from_user.username, message.from_user.first_name, message.from_user.last_name)
        await db_manager.update_user_timezone(user_db_id, timezone_str) # Use user_db_id
        await message.answer(f"Ваш часовой пояс установлен на '{timezone_str}'.")
        await state.clear()
    except pytz.exceptions.UnknownTimeZoneError:
        await message.answer("Неверный формат часового пояса. Пожалуйста, используйте формат IANA (например, 'Europe/Moscow').")

# --- Main ---

async def main() -> None:
    # Load existing scheduled tasks into APScheduler on startup
    await scheduler.load_existing_tasks()
    
    # Start polling
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.info("Starting bot...")
    asyncio.run(main())