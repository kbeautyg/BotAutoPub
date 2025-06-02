from aiogram import Router, types, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove, KeyboardButton, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from datetime import datetime
from zoneinfo import ZoneInfo
from states import CreatePost
from storage import supabase_db
from commands import TEXTS
import re

router = Router()

TOKEN_MAP = {
    "YYYY": "%Y", "YY": "%y",
    "MM": "%m",   "DD": "%d",
    "HH": "%H",   "hh": "%I",
    "mm": "%M",   "SS": "%S",
    "AM": "%p",   "PM": "%p",
    "am": "%p",   "pm": "%p",
}
_rx = re.compile("|".join(sorted(TOKEN_MAP, key=len, reverse=True)))

def format_to_strptime(date_fmt: str, time_fmt: str) -> str:
    return _rx.sub(lambda m: TOKEN_MAP[m.group(0)], f"{date_fmt} {time_fmt}")

def parse_time(user: dict, text: str):
    date_fmt = user.get("date_format", "YYYY-MM-DD")
    time_fmt = user.get("time_format", "HH:mm")
    tz_name = user.get("timezone", "UTC")
    # Adjust format to avoid conflict between month and minute tokens
    if "MM" in time_fmt:
        time_fmt = time_fmt.replace("MM", "mm")
    fmt = format_to_strptime(date_fmt, time_fmt)
    dt = datetime.strptime(text, fmt)
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("UTC")
    local_dt = dt.replace(tzinfo=tz)
    utc_dt = local_dt.astimezone(ZoneInfo("UTC"))
    return utc_dt

def format_example(user: dict):
    date_fmt = user.get("date_format", "YYYY-MM-DD")
    time_fmt = user.get("time_format", "HH:mm")
    # Adjust time format for example formatting
    if "MM" in time_fmt:
        time_fmt = time_fmt.replace("MM", "mm")
    fmt = format_to_strptime(date_fmt, time_fmt)
    now = datetime.now()
    try:
        return now.strftime(fmt)
    except Exception:
        return now.strftime("%Y-%m-%d %H:%M")

router = Router()

@router.message(Command("create"))
async def cmd_create(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user = supabase_db.db.get_user(user_id)
    lang = user.get("language", "ru") if user else "ru"
    # Ensure user and active project
    if not user:
        user = supabase_db.db.ensure_user(user_id, default_lang=lang)
        lang = user.get("language", lang)
    project_id = user.get("current_project") if user else None
    if not project_id or not supabase_db.db.list_channels(project_id=project_id):
        await message.answer(TEXTS[lang]['no_channels'])
        return
    await state.update_data(user_settings=user)
    await state.set_state(CreatePost.text)
    await message.answer(TEXTS[lang]['create_step1'])

@router.message(CreatePost.text, Command("skip"))
async def skip_text(message: Message, state: FSMContext):
    await state.update_data(text="")
    await next_media_step(message, state)

@router.message(CreatePost.text)
async def got_text(message: Message, state: FSMContext):
    await state.update_data(text=message.text or "")
    await next_media_step(message, state)

async def next_media_step(message: Message, state: FSMContext):
    await state.set_state(CreatePost.media)
    data = await state.get_data()
    lang = data.get("user_settings", {}).get("language", "ru")
    # Remove any reply keyboard if present
    await message.answer(TEXTS[lang]['create_step2'], reply_markup=ReplyKeyboardRemove())

@router.message(CreatePost.media, Command("skip"))
async def skip_media(message: Message, state: FSMContext):
    await state.update_data(media_id=None, media_type=None)
    await ask_format(message, state)

@router.message(CreatePost.media, F.photo)
async def got_photo(message: Message, state: FSMContext):
    await state.update_data(media_id=message.photo[-1].file_id, media_type="photo")
    await ask_format(message, state)

@router.message(CreatePost.media, F.video)
async def got_video(message: Message, state: FSMContext):
    await state.update_data(media_id=message.video.file_id, media_type="video")
    await ask_format(message, state)

@router.message(CreatePost.media)
async def wrong_media(message: Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get("user_settings", {}).get("language", "ru")
    # If wrong media type, prompt again
    await message.answer(TEXTS[lang]['create_step2_retry'])

async def ask_format(message: Message, state: FSMContext):
    await state.set_state(CreatePost.format)
    data = await state.get_data()
    lang = data.get("user_settings", {}).get("language", "ru")
    # Offer format choices via reply keyboard
    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Markdown"), KeyboardButton(text="HTML"), KeyboardButton(text="Без форматирования" if lang == "ru" else "None")]], resize_keyboard=True, one_time_keyboard=True)
    await message.answer(TEXTS[lang]['create_step3'], reply_markup=kb)

@router.message(CreatePost.format)
async def got_format(message: Message, state: FSMContext):
    raw = (message.text or "").strip().lower()
    new_fmt = "markdown" if raw.startswith("markdown") else "html" if raw.startswith("html") else "none"
    await state.update_data(format=new_fmt)
    # Remove the format keyboard
    await message.answer("OK", reply_markup=ReplyKeyboardRemove())
    await ask_buttons(message, state)

async def ask_buttons(message: Message, state: FSMContext):
    await state.set_state(CreatePost.buttons)
    data = await state.get_data()
    lang = data.get("user_settings", {}).get("language", "ru")
    await message.answer(TEXTS[lang]['create_step4'])

@router.message(CreatePost.buttons, Command("skip"))
async def skip_buttons(message: Message, state: FSMContext):
    await state.update_data(buttons=[])
    await ask_time(message, state)

@router.message(CreatePost.buttons)
async def got_buttons(message: Message, state: FSMContext):
    text = message.text or ""
    if text.strip().lower() in ("нет", "none"):
        # No buttons
        await state.update_data(buttons=[])
    else:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        buttons = []
        for line in lines:
            parts = line.split("|")
            if len(parts) >= 2:
                btn_text = parts[0].strip()
                btn_url = parts[1].strip()
                if btn_text and btn_url:
                    buttons.append({"text": btn_text, "url": btn_url})
        await state.update_data(buttons=buttons)
    await ask_time(message, state)

async def ask_time(message: Message, state: FSMContext):
    await state.set_state(CreatePost.time)
    data = await state.get_data()
    user = data.get("user_settings", {})
    lang = user.get("language", "ru") if user else "ru"
    example = format_example(user or {})
    fmt = f"{user.get('date_format', 'YYYY-MM-DD')} {user.get('time_format', 'HH:MM')}"
    await message.answer(TEXTS[lang]['create_step5'].format(format=fmt))

@router.message(CreatePost.time)
async def got_time(message: Message, state: FSMContext):
    data = await state.get_data()
    user = data.get("user_settings", {}) or {}
    lang = user.get("language", "ru")
    text = (message.text or "").strip()
    # Check for special 'none' keyword to indicate draft (no time)
    if text.lower() in ("none", "нет"):
        await state.update_data(publish_time=None, draft=True)
        await ask_repeat(message, state)
        return
    try:
        pub_dt = parse_time(user, text)
    except Exception:
        example = format_example(user)
        await message.answer(TEXTS[lang]['create_time_error'].format(example=example))
        return
    now = datetime.now(ZoneInfo("UTC"))
    if pub_dt <= now:
        await message.answer(TEXTS[lang]['time_past_error'])
        return
    await state.update_data(publish_time=pub_dt, draft=False)
    await ask_repeat(message, state)

async def ask_repeat(message: Message, state: FSMContext):
    await state.set_state(CreatePost.repeat)
    data = await state.get_data()
    lang = data.get("user_settings", {}).get("language", "ru")
    await message.answer(TEXTS[lang]['create_step6'])

@router.message(CreatePost.repeat)
async def got_repeat(message: Message, state: FSMContext):
    data = await state.get_data()
    user = data.get("user_settings", {}) or {}
    lang = user.get("language", "ru")
    raw = (message.text or "").strip().lower()
    interval = 0
    if raw in ("0", "/skip", "нет", "none"):
        interval = 0
    else:
        unit = raw[-1] if raw else ""
        try:
            value = int(raw[:-1])
        except:
            value = None
        if not value or unit not in ("d", "h", "m"):
            await message.answer(TEXTS[lang]['create_repeat_error'])
            return
        if unit == "d":
            interval = value * 24 * 3600
        elif unit == "h":
            interval = value * 3600
        elif unit == "m":
            interval = value * 60
    await state.update_data(repeat_interval=interval)
    await ask_channel(message, state)

async def ask_channel(message: Message, state: FSMContext):
    await state.set_state(CreatePost.channel)
    data = await state.get_data()
    user = data.get("user_settings", {}) or {}
    lang = user.get("language", "ru")
    # List channels in current project for selection
    channels = supabase_db.db.list_channels(project_id=user.get("current_project"))
    if not channels:
        await message.answer(TEXTS[lang]['channels_no_channels'])
        return
    lines = [TEXTS[lang]['create_step7']]
    for i, ch in enumerate(channels, start=1):
        name = ch['name'] or str(ch['chat_id'])
        lines.append(f"{i}. {name}")
    await state.update_data(_chan_map=channels)
    await message.answer("\n".join(lines))

@router.message(CreatePost.channel)
async def choose_channel(message: Message, state: FSMContext):
    data = await state.get_data()
    channels = data.get("_chan_map", [])
    raw = (message.text or "").strip()
    chosen = None
    if raw.isdigit():
        idx = int(raw)
        if 1 <= idx <= len(channels):
            chosen = channels[idx - 1]
    else:
        for ch in channels:
            if str(ch["chat_id"]) == raw or (ch["name"] and ("@" + ch["name"]) == raw):
                chosen = ch
                break
    if not chosen:
        lang = data.get("user_settings", {}).get("language", "ru")
        await message.answer(TEXTS[lang]['create_channel_error'])
        return
    await state.update_data(
        channel_chat_id=chosen["chat_id"],
        channel_db_id=chosen["id"],
        channel_name=chosen["name"] or str(chosen["chat_id"])
    )
    await show_preview(message, state)

async def show_preview(message: Message, state: FSMContext):
    data = await state.get_data()
    user = data.get("user_settings", {}) or {}
    lang = user.get("language", "ru")
    text = data.get("text", "")
    media_id = data.get("media_id")
    media_type = data.get("media_type")
    fmt = data.get("format", "none")
    buttons = data.get("buttons", [])
    parse_mode = None
    if fmt == "markdown":
        parse_mode = "Markdown"
    elif fmt == "html":
        parse_mode = "HTML"
    markup = None
    if buttons:
        kb = []
        for btn in buttons:
            if isinstance(btn, dict):
                btn_text = btn.get("text"); btn_url = btn.get("url")
            elif isinstance(btn, (list, tuple)) and len(btn) >= 2:
                btn_text, btn_url = btn[0], btn[1]
            else:
                continue
            if btn_text and btn_url:
                kb.append([InlineKeyboardButton(text=btn_text, url=btn_url)])
        if kb:
            markup = InlineKeyboardMarkup(inline_keyboard=kb)
    # Send a preview of the post content
    try:
        if media_id and media_type == "photo":
            await message.answer_photo(media_id, caption=text or TEXTS[lang]['no_text'], parse_mode=parse_mode, reply_markup=markup)
        elif media_id and media_type == "video":
            await message.answer_video(media_id, caption=text or TEXTS[lang]['no_text'], parse_mode=parse_mode, reply_markup=markup)
        else:
            await message.answer(text or TEXTS[lang]['no_text'], parse_mode=parse_mode, reply_markup=markup)
    except Exception as e:
        await message.answer(f"Предпросмотр недоступен: {e}" if lang == "ru" else f"Preview unavailable: {e}")
    # Build confirmation prompt text
    channel_name = data.get("channel_name")
    publish_time = data.get("publish_time")
    draft = data.get("draft", False)
    repeat_interval = data.get("repeat_interval", 0)
    if draft or publish_time is None:
        prompt = (f"Шаг 8/8: подтвердите сохранение черновика для «{channel_name}». (Не будет опубликован автоматически.)"
                 if lang == "ru" else
                 f"Step 8/8: confirm saving draft for \"{channel_name}\". (It will not be posted automatically.)")
    else:
        pub_dt = publish_time if isinstance(publish_time, datetime) else None
        if pub_dt is None:
            try:
                pub_dt = datetime.fromisoformat(publish_time)
            except Exception:
                pub_dt = datetime.strptime(publish_time, "%Y-%m-%dT%H:%M:%S")
        tz_name = user.get("timezone", "UTC")
        try:
            tz = ZoneInfo(tz_name)
        except Exception:
            tz = ZoneInfo("UTC")
        local_dt = pub_dt.astimezone(tz)
        local_str = local_dt.strftime(format_to_strptime(user.get("date_format", "YYYY-MM-DD"), user.get("time_format", "HH:MM")))
        utc_str = pub_dt.strftime("%Y-%m-%d %H:%M UTC")
        if repeat_interval and repeat_interval > 0:
            # Describe repeat interval in human-readable form
            interval_desc = ""
            if repeat_interval % 86400 == 0:
                days = repeat_interval // 86400
                if days == 1:
                    interval_desc = "каждый день" if lang == "ru" else "daily"
                else:
                    interval_desc = f"каждые {days} дней" if lang == "ru" else f"every {days} days"
            elif repeat_interval % 3600 == 0:
                hours = repeat_interval // 3600
                if hours == 1:
                    interval_desc = "каждый час" if lang == "ru" else "hourly"
                else:
                    interval_desc = f"каждые {hours} часов" if lang == "ru" else f"every {hours} hours"
            else:
                minutes = repeat_interval // 60
                interval_desc = f"каждые {minutes} минут" if lang == "ru" else f"every {minutes} minutes"
            prompt = (f"Шаг 8/8: подтвердите публикацию в «{channel_name}» {local_str} (UTC: {utc_str}).\nБудет повторяться {interval_desc}."
                     if lang == "ru" else
                     f"Step 8/8: confirm posting to \"{channel_name}\" at {local_str} (UTC: {utc_str}).\nIt will repeat {interval_desc}.")
        else:
            prompt = (f"Шаг 8/8: подтвердите публикацию в «{channel_name}» {local_str} (UTC: {utc_str})."
                     if lang == "ru" else
                     f"Step 8/8: confirm posting to \"{channel_name}\" at {local_str} (UTC: {utc_str}).")
    # Send confirm/cancel prompt with inline buttons
    confirm_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=TEXTS[lang]['yes_btn'], callback_data="confirm_create"),
            InlineKeyboardButton(text=TEXTS[lang]['no_btn'], callback_data="cancel_create")
        ]
    ])
    await message.answer(prompt, reply_markup=confirm_kb)
    await state.set_state(CreatePost.confirm)

@router.callback_query(F.data == "confirm_create")
async def on_confirm_create(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    user = data.get("user_settings", {})
    lang = user.get("language", "ru") if user else "ru"
    post_data = {
        "user_id": callback.from_user.id,
        "project_id": user.get("current_project"),
        "channel_id": data["channel_db_id"],
        "chat_id": data["channel_chat_id"],
        "text": data.get("text", ""),
        "media_id": data.get("media_id"),
        "media_type": data.get("media_type"),
        "format": data.get("format", "none"),
        "buttons": data.get("buttons", []),
        "publish_time": None,
        "repeat_interval": data.get("repeat_interval", 0),
        "draft": False,
        "published": False
    }
    if data.get("draft"):
        post_data["draft"] = True
        post_data["publish_time"] = None
    else:
        pub_time = data.get("publish_time")
        if isinstance(pub_time, datetime):
            post_data["publish_time"] = pub_time.strftime("%Y-%m-%dT%H:%M:%SZ")
        else:
            post_data["publish_time"] = pub_time
    supabase_db.db.add_post(post_data)
    # Edit the confirmation prompt message to success
    success_text = TEXTS[lang]['confirm_post_scheduled'] if not data.get("draft") else TEXTS[lang]['confirm_post_draft']
    try:
        await callback.message.edit_text(success_text)
    except:
        await callback.answer(success_text, show_alert=True)
    await state.clear()
    await callback.answer()

@router.callback_query(F.data == "cancel_create")
async def on_cancel_create(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    user = data.get("user_settings", {})
    lang = user.get("language", "ru") if user else "ru"
    # Edit prompt message to cancellation notice
    try:
        await callback.message.edit_text(TEXTS[lang]['confirm_post_cancel'])
    except:
        await callback.answer(TEXTS[lang]['confirm_post_cancel'], show_alert=True)
    await state.clear()
    await callback.answer()
