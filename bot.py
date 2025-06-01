# bot.py

import os
import logging
import re
from uuid import UUID
from datetime import datetime

from aiogram import Bot, Dispatcher, types
from aiogram.types import ParseMode
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.utils.exceptions import TelegramAPIError

from db import (
    get_user,
    create_user,
    add_channel,
    remove_channel,
    list_channels,
    create_post_draft,
    update_post_text,
    update_post_media,
    update_post_channels,
    update_post_buttons,
    set_post_schedule_one_time,
    set_post_schedule_cron,
    set_post_delete_rule,
    get_scheduled_posts,
    get_post,
    cancel_post,
    mark_post_cancelled,
)
from utils import (
    is_valid_timezone,
    parse_datetime_local,
    to_utc,
    validate_media,
    check_admin_rights,
    save_file_locally,
    upload_media_for_post,
    is_future_datetime,
)
from scheduler import (
    schedule_one_time,
    schedule_cron,
    schedule_delete,
    remove_job,
)

# ============================
# Настройка логирования
# ============================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================
# Инициализация бота и диспетчера
# ============================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN не задан в окружении")

bot = Bot(token=TELEGRAM_BOT_TOKEN, parse_mode=ParseMode.HTML)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)


# ----------------------------
# FSM: состояния
# ----------------------------
class AddChannel(StatesGroup):
    WaitingForChannel = State()


class RemoveChannel(StatesGroup):
    WaitingForChannel = State()


class CreatePost(StatesGroup):
    WaitingForText = State()
    WaitingForMedia = State()
    WaitingForChannels = State()
    WaitingForButtonsQuery = State()
    WaitingForButtons = State()
    WaitingForScheduleType = State()
    WaitingForOneTime = State()
    WaitingForCronType = State()
    WaitingForCronParams = State()
    WaitingForStartDate = State()
    WaitingForEndDate = State()
    WaitingForDeleteRule = State()
    Confirmation = State()


class EditPost(StatesGroup):
    WaitingForEditChoice = State()
    WaitingForNewValue = State()


# ----------------------------
# Утилита: получить или создать пользователя
# ----------------------------
def ensure_user(telegram_id: int):
    user = get_user(telegram_id)
    if not user:
        user = create_user(telegram_id)
    return user


# ----------------------------
# /start
# ----------------------------
@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    ensure_user(message.from_user.id)
    await message.reply(
        "Привет! Я бот для управления постами.\n\n"
        "Доступные команды:\n"
        "/add_channel - добавить канал\n"
        "/remove_channel - удалить канал\n"
        "/list_channels - список каналов\n"
        "/set_timezone <TZ> - установить часовой пояс (например, Europe/Moscow)\n"
        "/create_post - создать новый пост\n"
        "/list_posts - список запланированных постов\n"
        "/cancel_post <ID> - отменить пост\n"
        "/edit_post <ID> - редактировать пост\n"
        "/help - помощь"
    )


# ----------------------------
# /help
# ----------------------------
@dp.message_handler(commands=['help'])
async def cmd_help(message: types.Message):
    await message.reply(
        "Используй команды:\n"
        "/add_channel - добавить канал\n"
        "/remove_channel - удалить канал\n"
        "/list_channels - список каналов\n"
        "/set_timezone <TZ> - установить часовой пояс (например, Europe/Moscow)\n"
        "/create_post - создать новый пост\n"
        "/list_posts - список запланированных постов\n"
        "/cancel_post <ID> - отменить пост\n"
        "/edit_post <ID> - редактировать пост\n"
    )


# ----------------------------
# /add_channel
# ----------------------------
@dp.message_handler(commands=['add_channel'])
async def cmd_add_channel(message: types.Message):
    ensure_user(message.from_user.id)
    await AddChannel.WaitingForChannel.set()
    await message.reply("Введи @username или ID канала (или 'отмена').")


@dp.message_handler(state=AddChannel.WaitingForChannel, content_types=types.ContentTypes.TEXT)
async def process_add_channel(message: types.Message, state: FSMContext):
    text = message.text.strip()
    if text.lower() == 'отмена':
        await state.finish()
        return await message.reply("Добавление канала отменено.")

    channel_identifier = text
    try:
        chat = await bot.get_chat(channel_identifier)
        channel_id = chat.id
        title = chat.title or chat.username or str(chat.id)
    except TelegramAPIError:
        return await message.reply(
            "Не удалось получить информацию о канале. Проверь @username или ID."
        )

    user = get_user(message.from_user.id)
    if not await check_admin_rights(bot, channel_id, message.from_user.id):
        return await message.reply("У тебя или у бота нет прав администратора в этом канале.")

    add_channel(user['id'], channel_id, title)
    await state.finish()
    await message.reply(f"Канал <b>{title}</b> добавлен.")


# ----------------------------
# /remove_channel
# ----------------------------
@dp.message_handler(commands=['remove_channel'])
async def cmd_remove_channel(message: types.Message):
    user = ensure_user(message.from_user.id)
    channels = list_channels(user['id'])
    if not channels:
        return await message.reply("У тебя нет активных каналов. Добавь через /add_channel.")

    text = "Твои каналы:\n"
    for idx, ch in enumerate(channels, start=1):
        text += f"{idx}. {ch.get('title','')} (ID: {ch['channel_id']})\n"
    text += "\nВведи номер или @username/ID для удаления, или 'отмена'."
    await RemoveChannel.WaitingForChannel.set()
    await message.reply(text)


@dp.message_handler(state=RemoveChannel.WaitingForChannel, content_types=types.ContentTypes.TEXT)
async def process_remove_channel(message: types.Message, state: FSMContext):
    text = message.text.strip()
    if text.lower() == 'отмена':
        await state.finish()
        return await message.reply("Удаление канала отменено.")

    user = get_user(message.from_user.id)
    channels = list_channels(user['id'])
    target = None

    if text.isdigit():
        idx = int(text) - 1
        if 0 <= idx < len(channels):
            target = channels[idx]
    else:
        for ch in channels:
            if (str(ch['channel_id']) == text
                    or ch.get('title') == text
                    or (text.startswith('@') and text[1:] == ch.get('title'))):
                target = ch
                break

    if not target:
        return await message.reply("Канал не найден. Попробуй снова или 'отмена'.")

    remove_channel(user['id'], target['channel_id'])
    await state.finish()
    await message.reply(f"Канал <b>{target.get('title')}</b> удалён.")


# ----------------------------
# /list_channels
# ----------------------------
@dp.message_handler(commands=['list_channels'])
async def cmd_list_channels(message: types.Message):
    user = ensure_user(message.from_user.id)
    channels = list_channels(user['id'])
    if not channels:
        return await message.reply("У тебя нет активных каналов. Добавь через /add_channel.")
    text = "<b>Активные каналы:</b>\n"
    for idx, ch in enumerate(channels, start=1):
        text += f"{idx}. {ch.get('title','')} (ID: {ch['channel_id']})\n"
    await message.reply(text)


# ----------------------------
# /set_timezone <TZ>
# ----------------------------
@dp.message_handler(commands=['set_timezone'])
async def cmd_set_timezone(message: types.Message):
    args = message.get_args().strip()
    if not args:
        return await message.reply("Укажи часы̆ пояс. Пример: /set_timezone Europe/Moscow")
    if not is_valid_timezone(args):
        return await message.reply("Неверный часы̆ пояс. Пример: Europe/Moscow")

    user = ensure_user(message.from_user.id)
    from db import set_user_timezone as db_set_tz
    db_set_tz(message.from_user.id, args)
    await message.reply(f"Часы̆ пояс установлен: <b>{args}</b>")


# ----------------------------
# /create_post  (или «создать пост»)
# ----------------------------
@dp.message_handler(
    lambda msg: msg.text
    and (msg.text.lower() == 'создать пост' or msg.text.startswith('/create_post'))
)
async def cmd_create_post(message: types.Message, state: FSMContext):
    user = ensure_user(message.from_user.id)
    post_id = create_post_draft(user['id'])
    await state.update_data(post_id=str(post_id))
    await CreatePost.WaitingForText.set()
    await message.reply("Введи текст поста (Markdown/HTML) или '–' если без текста. 'отмена' — отмена.")


@dp.message_handler(state=CreatePost.WaitingForText, content_types=types.ContentTypes.TEXT)
async def process_post_text(message: types.Message, state: FSMContext):
    data = await state.get_data()
    post_id = data['post_id']
    text = message.text.strip()

    if text.lower() == 'отмена':
        cancel_post(UUID(post_id))
        await state.finish()
        return await message.reply("Создание поста отменено.")

    if text == '–':
        text = ""

    update_post_text(UUID(post_id), text)
    await CreatePost.next()
    await message.reply(
        "Отправь медиа (фото/видео/документы) по одному.\n"
        "'готово' или 'пропустить' — перейти дальше.\n"
        "'отмена' — отмена."
    )


@dp.message_handler(state=CreatePost.WaitingForMedia, content_types=types.ContentTypes.ANY)
async def process_post_media(message: types.Message, state: FSMContext):
    data = await state.get_data()
    post_id = data['post_id']

    # Если текстовая команда (готово/пропустить/отмена)
    if message.text:
        cmd = message.text.strip().lower()
        if cmd == 'отмена':
            cancel_post(UUID(post_id))
            await state.finish()
            return await message.reply("Создание поста отменено.")
        if cmd in {'готово', 'пропустить'}:
            media_list = upload_media_for_post(post_id)
            update_post_media(UUID(post_id), media_list)
            await CreatePost.next()
            return await message.reply(
                "Укажи каналы через запятую (пример: @ch1,@ch2). 'отмена' — отмена."
            )

    # Если медиасообщение
    if validate_media(message):
        local_path = await save_file_locally(message, post_id)
        if local_path:
            return await message.reply("Медиа получено. Можно отправить ещё или 'готово'.")
    else:
        await message.reply(
            "Неподдерживаемый формат или слишком большое (макс 20 МБ). Попробуй ещё или 'пропустить'."
        )


@dp.message_handler(state=CreatePost.WaitingForChannels, content_types=types.ContentTypes.TEXT)
async def process_post_channels(message: types.Message, state: FSMContext):
    data = await state.get_data()
    post_id = data['post_id']
    text = message.text.strip()

    if text.lower() == 'отмена':
        cancel_post(UUID(post_id))
        await state.finish()
        return await message.reply("Создание поста отменено.")

    entries = re.split(r'[\s,]+', text)
    user = get_user(message.from_user.id)
    user_channels = list_channels(user['id'])
    channel_ids = []

    for ent in entries:
        for ch in user_channels:
            if (ent == str(ch['channel_id'])
                    or ent == ch.get('title')
                    or (ent.startswith('@') and ent[1:] == ch.get('title'))):
                channel_ids.append(ch['channel_id'])
                break

    if not channel_ids:
        return await message.reply(
            "Не найден ни один канал из твоего списка. Попробуй снова или 'отмена'."
        )

    update_post_channels(UUID(post_id), channel_ids)
    await CreatePost.next()
    await message.reply("Добавить кнопки? 'да' или 'нет'. 'отмена' — отмена.")


@dp.message_handler(state=CreatePost.WaitingForButtonsQuery, content_types=types.ContentTypes.TEXT)
async def process_buttons_query(message: types.Message, state: FSMContext):
    data = await state.get_data()
    post_id = data['post_id']
    text = message.text.strip().lower()

    if text == 'отмена':
        cancel_post(UUID(post_id))
        await state.finish()
        return await message.reply("Создание поста отменено.")

    if text == 'да':
        await state.update_data(buttons=[])
        await CreatePost.next()
        return await message.reply(
            "Отправь кнопки в формате '<текст> <URL>' по одной. 'готово' — далее."
        )

    if text == 'нет':
        update_post_buttons(UUID(post_id), [])
        await CreatePost.next()
        return await message.reply(
            "Выбери режим отправки:\n1 — мгновенно\n2 — отложить разово\n3 — циклически\n'отмена' — отмена."
        )

    await message.reply("Ответь 'да' или 'нет', или 'отмена'.")


@dp.message_handler(state=CreatePost.WaitingForButtons, content_types=types.ContentTypes.ANY)
async def process_buttons(message: types.Message, state: FSMContext):
    data = await state.get_data()
    post_id = data['post_id']
    buttons = data.get('buttons', [])

    if message.text:
        text = message.text.strip()
        if text.lower() == 'отмена':
            cancel_post(UUID(post_id))
            await state.finish()
            return await message.reply("Создание поста отменено.")

        if text.lower() == 'готово':
            update_post_buttons(UUID(post_id), buttons)
            await CreatePost.next()
            return await message.reply(
                "Выбери режим отправки:\n1 — мгновенно\n2 — отложить разово\n3 — циклически\n'отмена' — отмена."
            )

        # Ожидаем формат "<текст> <URL>"
        parts = text.split(maxsplit=1)
        if len(parts) != 2 or not re.match(r'^https?://', parts[1]):
            return await message.reply("Неправильный формат. '<текст> <URL>' или 'готово'.")

        btn_text, btn_url = parts
        buttons.append({"text": btn_text, "url": btn_url})
        await state.update_data(buttons=buttons)
        return await message.reply(f"Кнопка добавлена: {btn_text} -> {btn_url}. Добавь ещё или 'готово'.")

    return await message.reply("Введи '<текст> <URL>' или 'готово'/'отмена'.")


@dp.message_handler(state=CreatePost.WaitingForScheduleType, content_types=types.ContentTypes.TEXT)
async def process_schedule_type(message: types.Message, state: FSMContext):
    data = await state.get_data()
    post_id = data['post_id']
    text = message.text.strip().lower()

    if text == 'отмена':
        cancel_post(UUID(post_id))
        await state.finish()
        return await message.reply("Создание поста отменено.")

    if text == '1':
        # Мгновенно: собираем превью и сразу публикуем
        post = get_post(UUID(post_id))
        preview = "Превью поста:\n"
        if post.get("text"):
            preview += f"Текст: {post['text']}\n"
        if post.get("media_ids"):
            preview += f"Медиа: {len(post['media_ids'])} файл(ов)\n"
        if post.get("buttons"):
            preview += "Кнопки:\n"
            for b in post["buttons"]:
                preview += f"- {b['text']}: {b['url']}\n"
        preview += "Каналы:\n"
        for cid in post["channels"]:
            preview += f"- ID {cid}\n"
        preview += "\nПодтверждаешь? 'да' или 'нет'."

        await CreatePost.Confirmation.set()
        await state.update_data(schedule_mode='immediate')
        return await message.reply(preview)

    if text == '2':
        # Разово
        await CreatePost.WaitingForOneTime.set()
        return await message.reply(
            "Введи дату и время (ДД.MM.YYYY HH:MM). Например: 05.06.2025 15:30.\n'отмена' — отмена."
        )

    if text == '3':
        # Циклически
        await CreatePost.WaitingForCronType.set()
        return await message.reply(
            "Выбери тип расписания:\n"
            "1 — ежедневно\n"
            "2 — еженедельно\n"
            "3 — ежемесячно\n"
            "4 — ежегодно\n"
            "'отмена' — отмена."
        )

    await message.reply("Введи '1', '2' или '3', или 'отмена'.")


@dp.message_handler(state=CreatePost.WaitingForOneTime, content_types=types.ContentTypes.TEXT)
async def process_one_time(message: types.Message, state: FSMContext):
    data = await state.get_data()
    post_id = data['post_id']
    text = message.text.strip().lower()

    if text == 'отмена':
        cancel_post(UUID(post_id))
        await state.finish()
        return await message.reply("Создание поста отменено.")

    user = get_user(message.from_user.id)
    dt_local = parse_datetime_local(message.text.strip(), user['timezone'])
    if not dt_local or not is_future_datetime(dt_local):
        return await message.reply("Неверный формат или время не в будущем. Попробуй снова.")

    dt_utc = to_utc(dt_local)
    set_post_schedule_one_time(UUID(post_id), dt_utc)

    post = get_post(UUID(post_id))
    preview = "Превью отложенного поста:\n"
    if post.get("text"):
        preview += f"Текст: {post['text']}\n"
    if post.get("media_ids"):
        preview += f"Медиа: {len(post['media_ids'])} файл(ов)\n"
    if post.get("buttons"):
        preview += "Кнопки:\n"
        for b in post["buttons"]:
            preview += f"- {b['text']}: {b['url']}\n"
    preview += "Каналы:\n"
    for cid in post["channels"]:
        preview += f"- ID {cid}\n"
    preview += f"Дата отправки: {dt_local.strftime('%d.%m.%Y %H:%M')} ({user['timezone']})\n"
    preview += "\nПодтверждаешь? 'да' или 'нет'."

    await CreatePost.Confirmation.set()
    await state.update_data(schedule_mode='one_time', run_date=dt_utc.isoformat())
    return await message.reply(preview)


@dp.message_handler(state=CreatePost.WaitingForCronType, content_types=types.ContentTypes.TEXT)
async def process_cron_type(message: types.Message, state: FSMContext):
    data = await state.get_data()
    post_id = data['post_id']
    text = message.text.strip().lower()

    if text == 'отмена':
        cancel_post(UUID(post_id))
        await state.finish()
        return await message.reply("Создание поста отменено.")

    mapping = {'1': 'daily', '2': 'weekly', '3': 'monthly', '4': 'yearly'}
    if text not in mapping:
        return await message.reply("Введи '1', '2', '3' или '4', или 'отмена'.")

    schedule_type = mapping[text]
    await state.update_data(schedule_type=schedule_type)
    await CreatePost.WaitingForCronParams.set()

    if schedule_type == 'daily':
        return await message.reply("Введи время (HH:MM). Например: 15:00. 'отмена' — отмена.")
    if schedule_type == 'weekly':
        return await message.reply("Введи дни недели (Mon,Wed,Fri) и время (HH:MM). Пример: Mon,Wed,Fri 10:00.")
    if schedule_type == 'monthly':
        return await message.reply("Введи число месяца (1-31) и время (HH:MM). Пример: 15 12:00.")
    if schedule_type == 'yearly':
        return await message.reply("Введи DD.MM и время (HH:MM). Пример: 25.12 09:00.")


@dp.message_handler(state=CreatePost.WaitingForCronParams, content_types=types.ContentTypes.TEXT)
async def process_cron_params(message: types.Message, state: FSMContext):
    data = await state.get_data()
    post_id = data['post_id']
    schedule_type = data['schedule_type']
    text = message.text.strip()

    if text.lower() == 'отмена':
        cancel_post(UUID(post_id))
        await state.finish()
        return await message.reply("Создание поста отменено.")

    user = get_user(message.from_user.id)
    try:
        if schedule_type == 'daily':
            time_str = text
            if not re.match(r'^\d{2}:\d{2}$', time_str):
                raise ValueError
            await state.update_data(time_str=time_str)

        elif schedule_type == 'weekly':
            parts = text.split()
            if len(parts) != 2:
                raise ValueError
            days_raw = parts[0].split(',')
            days = [d.strip().lower() for d in days_raw]
            time_str = parts[1]
            if not re.match(r'^\d{2}:\d{2}$', time_str):
                raise ValueError
            await state.update_data(days=days, time_str=time_str)

        elif schedule_type == 'monthly':
            parts = text.split()
            if len(parts) != 2 or not parts[0].isdigit():
                raise ValueError
            day_of_month = int(parts[0])
            time_str = parts[1]
            if not (1 <= day_of_month <= 31 and re.match(r'^\d{2}:\d{2}$', time_str)):
                raise ValueError
            await state.update_data(day_of_month=day_of_month, time_str=time_str)

        elif schedule_type == 'yearly':
            parts = text.split()
            if len(parts) != 2 or not re.match(r'^\d{2}\.\d{2}$', parts[0]):
                raise ValueError
            day, month = map(int, parts[0].split('.'))
            time_str = parts[1]
            if not (1 <= day <= 31 and 1 <= month <= 12 and re.match(r'^\d{2}:\d{2}$', time_str)):
                raise ValueError
            await state.update_data(month_and_day=(month, day), time_str=time_str)

        else:
            raise ValueError
    except ValueError:
        return await message.reply("Неверный формат. Попробуй снова или 'отмена'.")

    await CreatePost.WaitingForStartDate.set()
    await message.reply("Введи дату начала (ДД.MM.YYYY) или 'сейчас'. 'отмена' — отмена.")


@dp.message_handler(state=CreatePost.WaitingForStartDate, content_types=types.ContentTypes.TEXT)
async def process_start_date(message: types.Message, state: FSMContext):
    data = await state.get_data()
    post_id = data['post_id']
    text = message.text.strip()

    if text.lower() == 'отмена':
        cancel_post(UUID(post_id))
        await state.finish()
        return await message.reply("Создание поста отменено.")

    user = get_user(message.from_user.id)
    if text.lower() == 'сейчас':
        start_date = None
    else:
        try:
            dt_local = parse_datetime_local(text + " 00:00", user['timezone'])
            if not dt_local or not is_future_datetime(dt_local):
                raise ValueError
            start_date = dt_local
        except ValueError:
            return await message.reply("Неверный формат или дата в прошлом. Попробуй снова или 'отмена'.")

    await state.update_data(start_date=start_date)
    await CreatePost.WaitingForEndDate.set()
    await message.reply("Введи дату окончания (ДД.MM.YYYY) или 'без конца'. 'отмена' — отмена.")


@dp.message_handler(state=CreatePost.WaitingForEndDate, content_types=types.ContentTypes.TEXT)
async def process_end_date(message: types.Message, state: FSMContext):
    data = await state.get_data()
    post_id = data['post_id']
    schedule_type = data['schedule_type']
    time_str = data.get('time_str')
    days = data.get('days')
    day_of_month = data.get('day_of_month')
    month_and_day = data.get('month_and_day')

    text = message.text.strip()
    if text.lower() == 'отмена':
        cancel_post(UUID(post_id))
        await state.finish()
        return await message.reply("Создание поста отменено.")

    user = get_user(message.from_user.id)
    if text.lower() == 'без конца':
        end_date = None
    else:
        try:
            dt_local = parse_datetime_local(text + " 23:59", user['timezone'])
            if not dt_local or not is_future_datetime(dt_local):
                raise ValueError
            end_date = dt_local
        except ValueError:
            return await message.reply("Неверный формат или дата в прошлом. Попробуй снова или 'отмена'.")

    await state.update_data(end_date=end_date)

    # Сохраняем cron_rule в БД
    # Формируем строку вида "MM HH * * * ..." – но проще хранить в удобном для CronTrigger виде
    # Здесь для наглядности храним JSON‐объект и регистрация задачи происходит при подтверждении

    # Достаем все нужные данные для превью:
    post = get_post(UUID(post_id))
    preview = "Превью циклического поста:\n"
    if post.get("text"):
        preview += f"Текст: {post['text']}\n"
    if post.get("media_ids"):
        preview += f"Медиа: {len(post['media_ids'])} файл(ов)\n"
    if post.get("buttons"):
        preview += "Кнопки:\n"
        for b in post["buttons"]:
            preview += f"- {b['text']}: {b['url']}\n"
    preview += "Каналы:\n"
    for cid in post["channels"]:
        preview += f"- ID {cid}\n"

    if schedule_type == 'daily':
        preview += f"Расписание: ежедневно в {time_str}\n"
    elif schedule_type == 'weekly':
        preview += f"Расписание: по {', '.join(days)} в {time_str}\n"
    elif schedule_type == 'monthly':
        preview += f"Расписание: каждый {day_of_month} числа в {time_str}\n"
    elif schedule_type == 'yearly':
        preview += f"Расписание: {month_and_day[1]}.{month_and_day[0]} в {time_str}\n"

    if data.get('start_date'):
        preview += f"Начало: {data['start_date'].strftime('%d.%m.%Y')}\n"
    else:
        preview += "Начало: сейчас\n"
    if end_date:
        preview += f"Окончание: {end_date.strftime('%d.%m.%Y')}\n"
    else:
        preview += "Окончание: без конца\n"

    preview += "\nПодтверждаешь? 'да' или 'нет'."

    await CreatePost.Confirmation.set()
    await state.update_data(confirm_cron=True)
    await message.reply(preview)


@dp.message_handler(state=CreatePost.WaitingForDeleteRule, content_types=types.ContentTypes.TEXT)
async def process_delete_rule(message: types.Message, state: FSMContext):
    data = await state.get_data()
    post_id = data['post_id']
    text = message.text.strip().lower()

    if text == 'отмена':
        cancel_post(UUID(post_id))
        await state.finish()
        return await message.reply("Создание поста отменено.")

    await state.update_data(delete_query=True)
    await CreatePost.next()
    await message.reply(
        "Правило удаления:\n"
        "1 — не удалять\n"
        "2 — удалить через N часов/дней\n"
        "3 — удалить в дату (ДД.MM.YYYY HH:MM)\n"
        "'отмена' — отмена."
    )


@dp.message_handler(state=CreatePost.Confirmation, content_types=types.ContentTypes.TEXT)
async def process_confirmation(message: types.Message, state: FSMContext):
    data = await state.get_data()
    post_id = data['post_id']
    schedule_mode = data.get('schedule_mode')
    run_date_iso = data.get('run_date')
    confirm_cron = data.get('confirm_cron', False)

    text = message.text.strip().lower()
    if text == 'нет':
        cancel_post(UUID(post_id))
        await state.finish()
        return await message.reply("Создание поста отменено.")

    user = get_user(message.from_user.id)

    # ===== 1) «Мгновенно» =====
    if text == 'да' and schedule_mode == 'immediate':
        job_id = schedule_one_time(post_id, datetime.now(pytz.UTC))
        await state.finish()
        return await message.reply(f"Пост отправлен мгновенно. ID задачи публикации: {job_id}")

    # ===== 2) «Отложить разово» =====
    if text == 'да' and schedule_mode == 'one_time':
        run_date = datetime.fromisoformat(run_date_iso)
        job_id = schedule_one_time(post_id, run_date)
        await state.finish()
        return await message.reply(
            f"Пост запланирован на {run_date.strftime('%d.%m.%Y %H:%M')} UTC.\n"
            f"ID задачи: {job_id}"
        )

    # ===== 3) «Циклически» =====
    if text == 'да' and confirm_cron:
        # Достаём параметры из data
        schedule_type = data['schedule_type']
        time_str = data['time_str']
        days = data.get('days')
        day_of_month = data.get('day_of_month')
        month_and_day = data.get('month_and_day')
        start_date = data.get('start_date')  # локальный datetime или None
        end_date = data.get('end_date')      # локальный datetime или None

        # Сохраняем в БД cron_rule в виде произвольной строки (например, JSON) —
        # для примера сохраним как f"{schedule_type}:{time_str}:{days}:{day_of_month}:{month_and_day}"
        cron_rule = f"{schedule_type}:{time_str}:{days}:{day_of_month}:{month_and_day}"
        set_post_schedule_cron(UUID(post_id), cron_rule)

        # Регистрируем задачу в планировщике
        job_id = schedule_cron(
            post_id,
            schedule_type=schedule_type,
            time_str=time_str,
            days=days,
            day_of_month=day_of_month,
            month_and_day=month_and_day,
            start_date_local=start_date,
            end_date_local=end_date
        )
        await state.finish()
        return await message.reply(f"Циклически: создана задача {job_id}.")

    await message.reply("Ответь 'да' или 'нет'.")


# ----------------------------
# /list_posts
# ----------------------------
@dp.message_handler(commands=['list_posts'])
async def cmd_list_posts(message: types.Message):
    user = ensure_user(message.from_user.id)
    posts = get_scheduled_posts(user['id'])
    if not posts:
        return await message.reply("У тебя нет запланированных постов.")

    text = "<b>Запланированные посты:</b>\n"
    for p in posts:
        pid = p['id']
        snippet = (p['text'][:30] + ("..." if p['text'] and len(p['text']) > 30 else "")) if p['text'] else "без текста"
        channels = ", ".join(str(c) for c in p['channels'] or [])
        schedule_type = p.get('type_schedule')
        if schedule_type == 'one_time':
            ts = p.get('one_time_ts_utc')
            sched = f"одноразово: {ts}"
        else:
            cron = p.get('cron_rule')
            sched = f"cron: {cron}"
        dr = (p.get('delete_rule') or {"type": "never"}).get('type')
        text += (
            f"ID: {pid}\n"
            f"Текст: {snippet}\n"
            f"Каналы: {channels}\n"
            f"Расписание: {sched}\n"
            f"Удаление: {dr}\n\n"
        )

    text += "Чтобы отменить пост: /cancel_post <ID>\nЧтобы редактировать: /edit_post <ID>"
    await message.reply(text)


# ----------------------------
# /cancel_post <ID>
# ----------------------------
@dp.message_handler(commands=['cancel_post'])
async def cmd_cancel_post(message: types.Message):
    args = message.get_args().strip()
    if not args:
        return await message.reply("Укажи ID поста. Пример: /cancel_post <ID>")

    post_id = args
    try:
        p = get_post(UUID(post_id))
    except Exception:
        return await message.reply("Неверный ID поста.")
    if not p or p.get('status') != 'scheduled':
        return await message.reply("Пост не найден или уже не запланирован.")

    remove_job(f"{post_id}_pub")
    remove_job(f"{post_id}_del")
    mark_post_cancelled(UUID(post_id))
    await message.reply(f"Пост {post_id} отменён.")


# ----------------------------
# /edit_post <ID>
# ----------------------------
@dp.message_handler(commands=['edit_post'])
async def cmd_edit_post(message: types.Message, state: FSMContext):
    args = message.get_args().strip()
    if not args:
        return await message.reply("Укажи ID поста. Пример: /edit_post <ID>")

    post_id = args
    try:
        post = get_post(UUID(post_id))
    except Exception:
        return await message.reply("Неверный ID поста.")

    if not post or post.get('status') != 'scheduled':
        return await message.reply("Пост не найден или нельзя редактировать.")

    await state.update_data(edit_post_id=post_id)
    text = "Текущие настройки поста:\n"
    text += f"Текст: {post.get('text') or 'без текста'}\n"
    text += f"Медиа: {len(post.get('media_ids') or [])} файл(ов)\n"
    if post.get('buttons'):
        text += "Кнопки:\n"
        for b in post['buttons']:
            text += f"- {b['text']}: {b['url']}\n"
    text += f"Каналы: {', '.join(str(c) for c in post.get('channels') or [])}\n"
    if post.get('type_schedule') == 'one_time':
        text += f"Расписание: одноразово {post.get('one_time_ts_utc')}\n"
    else:
        text += f"Расписание: cron {post.get('cron_rule')}\n"
    text += f"Удаление: {post.get('delete_rule') or {'type': 'never'}}\n\n"
    text += "Что изменить?\n"
    text += "1 — текст\n2 — медиа\n3 — кнопки\n4 — каналы\n5 — расписание\n6 — правило удаления\n7 — отмена"

    await EditPost.WaitingForEditChoice.set()
    await message.reply(text)


@dp.message_handler(state=EditPost.WaitingForEditChoice, content_types=types.ContentTypes.TEXT)
async def process_edit_choice(message: types.Message, state: FSMContext):
    data = await state.get_data()
    post_id = data['edit_post_id']
    choice = message.text.strip()

    if choice == '7' or choice.lower() == 'отмена':
        await state.finish()
        return await message.reply("Редактирование отменено.")

    # Для краткости — реализовано только изменение текста (выбор 1)
    if choice == '1':
        await state.update_data(edit_field='text')
        await EditPost.WaitingForNewValue.set()
        return await message.reply("Введи новый текст или '–' для удаления текста. 'отмена' — отмена.")

    await message.reply("Пока реализовано изменение только текста (выбери '1') или '7' для отмены.")


@dp.message_handler(state=EditPost.WaitingForNewValue, content_types=types.ContentTypes.TEXT)
async def process_new_value(message: types.Message, state: FSMContext):
    data = await state.get_data()
    post_id = data['edit_post_id']
    field = data.get('edit_field')
    text = message.text.strip()

    if text.lower() == 'отмена':
        await state.finish()
        return await message.reply("Редактирование отменено.")

    if field == 'text':
        new_text = "" if text == '–' else text
        update_post_text(UUID(post_id), new_text)
        await state.finish()
        return await message.reply("Текст поста обновлён.")

    await state.finish()
    return await message.reply("Неизвестное поле.")


# ----------------------------
# Запуск бота
# ----------------------------
if __name__ == '__main__':
    os.makedirs("media", exist_ok=True)
    from aiogram import executor
    executor.start_polling(dp, skip_updates=True)
