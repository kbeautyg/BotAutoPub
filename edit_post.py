import json
import re
from aiogram import Router, types, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove, KeyboardButton, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from datetime import datetime
from zoneinfo import ZoneInfo
from states import EditPost
from storage import supabase_db
from commands import TEXTS

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
    # Adjust time format for correct parsing
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
    if "MM" in time_fmt:
        time_fmt = time_fmt.replace("MM", "mm")
    fmt = format_to_strptime(date_fmt, time_fmt)
    now = datetime.now()
    try:
        return now.strftime(fmt)
    except Exception:
        return now.strftime("%Y-%m-%d %H:%M")

@router.message(Command("edit"))
async def cmd_edit(message: Message, state: FSMContext):
    user_id = message.from_user.id
    args = message.text.split(maxsplit=1)
    lang = "ru"
    user = supabase_db.db.get_user(user_id)
    if user:
        lang = user.get("language", "ru")
    if len(args) < 2:
        await message.answer(TEXTS[lang]['edit_usage'])
        return
    try:
        post_id = int(args[1])
    except:
        await message.answer(TEXTS[lang]['edit_invalid_id'])
        return
    post = supabase_db.db.get_post(post_id)
    # Permission check: user must be member of the project containing this post
    if not post or not supabase_db.db.is_user_in_project(user_id, post.get("project_id", -1)):
        await message.answer(TEXTS[lang]['edit_post_not_found'])
        return
    if post.get("published"):
        await message.answer(TEXTS[lang]['edit_post_published'])
        return
    # Initialize FSM for editing
    await state.update_data(orig_post=post, user_settings=(user or supabase_db.db.ensure_user(user_id, default_lang=lang)))
    await state.set_state(EditPost.text)
    current_text = post.get("text") or ""
    await message.answer(TEXTS[lang]['edit_begin'].format(id=post_id, text=current_text))

@router.message(EditPost.text, Command("skip"))
async def skip_edit_text(message: Message, state: FSMContext):
    await state.update_data(new_text=None)
    await ask_edit_media(message, state)

@router.message(EditPost.text)
async def edit_step_text(message: Message, state: FSMContext):
    await state.update_data(new_text=message.text or "")
    await ask_edit_media(message, state)

async def ask_edit_media(message: Message, state: FSMContext):
    await state.set_state(EditPost.media)
    data = await state.get_data()
    orig_post = data.get("orig_post", {})
    lang = data.get("user_settings", {}).get("language", "ru")
    if orig_post.get("media_id"):
        info = TEXTS[lang]['media_photo'] if orig_post.get("media_type") == "photo" else TEXTS[lang]['media_video'] if orig_post.get("media_type") == "video" else TEXTS[lang]['media_media']
        await message.answer(TEXTS[lang]['edit_current_media'].format(info=info))
    else:
        await message.answer(TEXTS[lang]['edit_no_media'])

@router.message(EditPost.media, Command("skip"))
async def skip_edit_media(message: Message, state: FSMContext):
    await state.update_data(new_media_id=None, new_media_type=None)
    await ask_edit_format(message, state)

@router.message(EditPost.media, F.photo)
async def edit_step_media_photo(message: Message, state: FSMContext):
    await state.update_data(new_media_id=message.photo[-1].file_id, new_media_type="photo")
    await ask_edit_format(message, state)

@router.message(EditPost.media, F.video)
async def edit_step_media_video(message: Message, state: FSMContext):
    await state.update_data(new_media_id=message.video.file_id, new_media_type="video")
    await ask_edit_format(message, state)

@router.message(EditPost.media)
async def edit_step_media_invalid(message: Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get("user_settings", {}).get("language", "ru")
    # Prompt again if invalid media type
    if data.get("orig_post", {}).get("media_id"):
        info = TEXTS[lang]['media_media']
        await message.answer(TEXTS[lang]['edit_current_media'].format(info=info))
    else:
        await message.answer(TEXTS[lang]['edit_no_media'])

async def ask_edit_format(message: Message, state: FSMContext):
    await state.set_state(EditPost.format)
    data = await state.get_data()
    orig_post = data.get("orig_post", {})
    lang = data.get("user_settings", {}).get("language", "ru")
    current_format = orig_post.get("format") or "none"
    # Show current format and prompt for new
    await message.answer(TEXTS[lang]['edit_current_format'].format(format=current_format))

@router.message(EditPost.format)
async def edit_step_format(message: Message, state: FSMContext):
    raw = (message.text or "").strip().lower()
    new_fmt = None
    if raw:
        if raw.startswith("markdown"):
            new_fmt = "markdown"
        elif raw.startswith("html") or raw.startswith("htm"):
            new_fmt = "html"
        elif raw in ("none", "без", "без форматирования"):
            new_fmt = "none"
    if new_fmt is None:
        data = await state.get_data()
        lang = data.get("user_settings", {}).get("language", "ru")
        # If format not recognized, keep current
        new_fmt = (data.get("orig_post", {}).get("format") or "none")
    await state.update_data(new_format=new_fmt)
    await ask_edit_buttons(message, state)

async def ask_edit_buttons(message: Message, state: FSMContext):
    await state.set_state(EditPost.buttons)
    data = await state.get_data()
    orig_post = data.get("orig_post", {})
    lang = data.get("user_settings", {}).get("language", "ru")
    if orig_post.get("buttons"):
        # Present current buttons list
        btns = orig_post.get("buttons")
        if isinstance(btns, str):
            try:
                btns = json.loads(btns)
            except:
                btns = []
        if not isinstance(btns, list):
            btns = []
        if btns:
            buttons_list = "\n".join([f"- {b['text']} | {b['url']}" if isinstance(b, dict) else f"- {b}" for b in btns])
        else:
            buttons_list = "-"
        await message.answer(TEXTS[lang]['edit_current_buttons'].format(buttons_list=buttons_list))
    else:
        await message.answer(TEXTS[lang]['edit_no_buttons'])

@router.message(EditPost.buttons)
async def edit_step_buttons(message: Message, state: FSMContext):
    text = message.text or ""
    if text.strip().lower() in ("нет", "none"):
        await state.update_data(new_buttons=[])
    else:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        new_buttons = []
        for line in lines:
            parts = line.split("|")
            if len(parts) >= 2:
                btn_text = parts[0].strip()
                btn_url = parts[1].strip()
                if btn_text and btn_url:
                    new_buttons.append({"text": btn_text, "url": btn_url})
        await state.update_data(new_buttons=new_buttons)
    await ask_edit_time(message, state)

async def ask_edit_time(message: Message, state: FSMContext):
    await state.set_state(EditPost.time)
    data = await state.get_data()
    orig_post = data.get("orig_post", {})
    user = data.get("user_settings", {}) or {}
    lang = user.get("language", "ru")
    if orig_post.get("publish_time"):
        # Show current scheduled time
        orig_time = orig_post.get("publish_time")
        try:
            pub_dt = datetime.fromisoformat(orig_time) if isinstance(orig_time, str) else orig_time
        except:
            pub_dt = datetime.strptime(orig_time, "%Y-%m-%dT%H:%M:%S")
            pub_dt = pub_dt.replace(tzinfo=ZoneInfo("UTC"))
        tz_name = user.get("timezone", "UTC")
        try:
            tz = ZoneInfo(tz_name)
        except:
            tz = ZoneInfo("UTC")
        local_dt = pub_dt.astimezone(tz)
        fmt = format_to_strptime(user.get("date_format", "YYYY-MM-DD"), user.get("time_format", "HH:mm"))
        current_time_str = local_dt.strftime(fmt)
        await message.answer(TEXTS[lang]['edit_current_time'].format(time=current_time_str, format=f"{user.get('date_format', 'YYYY-MM-DD')} {user.get('time_format', 'HH:MM')}"))
    else:
        await message.answer(TEXTS[lang]['edit_current_time'].format(time="(черновик)" if lang == "ru" else "(draft)", format=f"{user.get('date_format', 'YYYY-MM-DD')} {user.get('time_format', 'HH:MM')}"))

@router.message(EditPost.time)
async def edit_step_time(message: Message, state: FSMContext):
    data = await state.get_data()
    user = data.get("user_settings", {}) or {}
    lang = user.get("language", "ru")
    text = (message.text or "").strip()
    if text.lower() in ("none", "нет"):
        await state.update_data(new_publish_time=None)
        # Mark as draft if unscheduled
        await state.update_data(new_publish_time=None)
    else:
        try:
            new_time = parse_time(user, text)
        except:
            example = format_example(user)
            await message.answer(TEXTS[lang]['edit_time_error'].format(format=f"{user.get('date_format', 'YYYY-MM-DD')} {user.get('time_format', 'HH:MM')}"))
            return
        now = datetime.now(ZoneInfo("UTC"))
        if new_time <= now:
            await message.answer(TEXTS[lang]['time_past_error'])
            return
        await state.update_data(new_publish_time=new_time)
    await ask_edit_repeat(message, state)

async def ask_edit_repeat(message: Message, state: FSMContext):
    await state.set_state(EditPost.repeat)
    data = await state.get_data()
    orig_post = data.get("orig_post", {})
    user = data.get("user_settings", {}) or {}
    lang = user.get("language", "ru")
    current_repeat = orig_post.get("repeat_interval") or 0
    current_repeat_str = "0"
    # Determine human-friendly representation for current repeat interval
    if current_repeat % 86400 == 0 and current_repeat > 0:
        days = current_repeat // 86400
        current_repeat_str = f"{days}d"
    elif current_repeat % 3600 == 0 and current_repeat > 0:
        hours = current_repeat // 3600
        current_repeat_str = f"{hours}h"
    elif current_repeat % 60 == 0 and current_repeat > 0:
        minutes = current_repeat // 60
        current_repeat_str = f"{minutes}m"
    await message.answer(TEXTS[lang]['edit_current_repeat'].format(repeat=current_repeat_str))

@router.message(EditPost.repeat)
async def edit_step_repeat(message: Message, state: FSMContext):
    data = await state.get_data()
    user = data.get("user_settings", {}) or {}
    lang = user.get("language", "ru")
    raw = (message.text or "").strip().lower()
    new_interval = None
    if raw in ("0", "none", "нет", "/skip"):
        new_interval = 0
    else:
        unit = raw[-1] if raw else ""
        try:
            value = int(raw[:-1])
        except:
            value = None
        if not value or unit not in ("d", "h", "m"):
            await message.answer(TEXTS[lang]['edit_repeat_error'])
            return
        if unit == "d":
            new_interval = value * 86400
        elif unit == "h":
            new_interval = value * 3600
        elif unit == "m":
            new_interval = value * 60
    if new_interval is None:
        new_interval = 0
    await state.update_data(new_repeat_interval=new_interval)
    # Now ask to choose channel (if want to change) or skip
    await ask_edit_channel(message, state)

async def ask_edit_channel(message: Message, state: FSMContext):
    await state.set_state(EditPost.channel)
    data = await state.get_data()
    orig_post = data.get("orig_post", {})
    lang = data.get("user_settings", {}).get("language", "ru")
    # List channels available in current project
    channels = supabase_db.db.list_channels(project_id=data.get("user_settings", {}).get("current_project"))
    if not channels:
        await message.answer(TEXTS[lang]['channels_no_channels'])
        return
    # Determine current channel name for reference
    current_channel_name = "(unknown)"
    chan_id = orig_post.get("channel_id"); chat_id = orig_post.get("chat_id")
    for ch in channels:
        if chan_id and ch.get("id") == chan_id:
            current_channel_name = ch.get("name") or str(ch.get("chat_id"))
            break
        if chat_id and ch.get("chat_id") == chat_id:
            current_channel_name = ch.get("name") or str(ch.get("chat_id"))
            break
    # Prompt channel selection
    if lang == "ru":
        lines = [f"Текущий канал: {current_channel_name}", "Выберите новый канал или отправьте /skip, чтобы оставить текущий:"]
    else:
        lines = [f"Current channel: {current_channel_name}", "Choose a new channel or send /skip to keep the current one:"]
    for i, ch in enumerate(channels, start=1):
        name = ch.get("name") or str(ch.get("chat_id"))
        lines.append(f"{i}. {name}")
    await state.update_data(_chan_map=channels)
    await message.answer("\n".join(lines))

@router.message(EditPost.channel, Command("skip"))
async def skip_edit_channel(message: Message, state: FSMContext):
    data = await state.get_data()
    orig_post = data.get("orig_post", {})
    # Keep current channel as is
    new_channel_id = orig_post.get("channel_id")
    new_chat_id = orig_post.get("chat_id")
    new_channel_name = None
    channels = supabase_db.db.list_channels(project_id=data.get("user_settings", {}).get("current_project"))
    for ch in channels:
        if ch.get("id") == new_channel_id or ch.get("chat_id") == new_chat_id:
            new_channel_name = ch.get("name") or str(ch.get("chat_id"))
            break
    await state.update_data(new_channel_db_id=new_channel_id, new_channel_chat_id=new_chat_id, new_channel_name=new_channel_name)
    await show_edit_preview(message, state)

@router.message(EditPost.channel)
async def choose_edit_channel(message: Message, state: FSMContext):
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
        await message.answer(TEXTS[lang]['edit_channel_error'] if 'edit_channel_error' in TEXTS[lang] else TEXTS[lang]['edit_post_not_found'])
        return
    await state.update_data(new_channel_db_id=chosen.get("id"), new_channel_chat_id=chosen.get("chat_id"), new_channel_name=chosen.get("name") or str(chosen.get("chat_id")))
    await show_edit_preview(message, state)

async def show_edit_preview(message: Message, state: FSMContext):
    data = await state.get_data()
    orig_post = data.get("orig_post", {})
    user = data.get("user_settings", {}) or {}
    lang = user.get("language", "ru")
    text = data.get("new_text", orig_post.get("text", "")) or ""
    media_id = data.get("new_media_id", orig_post.get("media_id"))
    media_type = data.get("new_media_type", orig_post.get("media_type"))
    fmt = data.get("new_format", orig_post.get("format") or "none")
    buttons = data.get("new_buttons", orig_post.get("buttons") or [])
    # Prepare markup for preview buttons
    btn_list = []
    if isinstance(buttons, str):
        try:
            btn_list = json.loads(buttons) if buttons else []
        except Exception:
            btn_list = []
    elif isinstance(buttons, list):
        btn_list = buttons
    markup = None
    if btn_list:
        kb = []
        for btn in btn_list:
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
    parse_mode = None
    if fmt and fmt.lower() == "markdown":
        parse_mode = "Markdown"
    elif fmt and fmt.lower() == "html":
        parse_mode = "HTML"
    try:
        if media_id and media_type:
            if media_type.lower() == "photo":
                await message.answer_photo(media_id, caption=text or TEXTS[lang]['no_text'], parse_mode=parse_mode, reply_markup=markup)
            elif media_type.lower() == "video":
                await message.answer_video(media_id, caption=text or TEXTS[lang]['no_text'], parse_mode=parse_mode, reply_markup=markup)
            else:
                await message.answer(text or TEXTS[lang]['no_text'], parse_mode=parse_mode, reply_markup=markup)
        else:
            await message.answer(text or TEXTS[lang]['no_text'], parse_mode=parse_mode, reply_markup=markup)
    except Exception as e:
        await message.answer(f"Предпросмотр сообщения недоступен: {e}" if lang == "ru" else f"Preview unavailable: {e}")
    # Prompt for confirming changes via buttons
    confirm_text = ( "Подтвердите изменение поста через кнопки ниже." if lang == "ru" else "Please confirm or cancel the changes using the buttons below." )
    confirm_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=TEXTS[lang]['yes_btn'], callback_data="confirm_edit"),
            InlineKeyboardButton(text=TEXTS[lang]['no_btn'], callback_data="cancel_edit")
        ]
    ])
    await message.answer(confirm_text, reply_markup=confirm_kb)
    await state.set_state(EditPost.confirm)

@router.callback_query(F.data == "confirm_edit")
async def on_confirm_edit(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    orig_post = data.get("orig_post", {})
    post_id = orig_post.get("id")
    # Double-check if post got published during editing
    latest = supabase_db.db.get_post(post_id)
    user = data.get("user_settings", {})
    lang = user.get("language", "ru") if user else "ru"
    if not latest or latest.get("published"):
        await callback.message.edit_text(TEXTS[lang]['edit_post_published'])
        await state.clear()
        await callback.answer()
        return
    updates = {}
    if "new_text" in data:
        updates["text"] = data["new_text"]
    if "new_media_id" in data:
        updates["media_id"] = data["new_media_id"]
        updates["media_type"] = data.get("new_media_type")
    if "new_format" in data:
        updates["format"] = data["new_format"]
    if "new_buttons" in data:
        updates["buttons"] = data["new_buttons"]
    if "new_publish_time" in data:
        pub_time = data["new_publish_time"]
        if isinstance(pub_time, datetime):
            updates["publish_time"] = pub_time.strftime("%Y-%m-%dT%H:%M:%SZ")
        else:
            updates["publish_time"] = pub_time
        if pub_time is None:
            updates["draft"] = True
            updates["published"] = False
            updates["repeat_interval"] = 0
        else:
            updates["draft"] = False
    if "new_repeat_interval" in data:
        updates["repeat_interval"] = data["new_repeat_interval"]
    if "new_channel_db_id" in data:
        updates["channel_id"] = data["new_channel_db_id"]
        updates["chat_id"] = data.get("new_channel_chat_id")
        # If channel changed, also update project_id to new channel's project (should be same project normally)
        # We assume project remains same in current design.
    supabase_db.db.update_post(post_id, updates)
    await callback.message.edit_text(TEXTS[lang]['confirm_changes_saved'].format(id=post_id))
    await state.clear()
    await callback.answer()

@router.callback_query(F.data == "cancel_edit")
async def on_cancel_edit(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    user = data.get("user_settings", {})
    lang = user.get("language", "ru") if user else "ru"
    await callback.message.edit_text(TEXTS[lang]['edit_cancelled'])
    await state.clear()
    await callback.answer()
