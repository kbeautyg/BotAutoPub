from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command
from zoneinfo import ZoneInfo
from storage import supabase_db
from commands import TEXTS

router = Router()

@router.message(Command("settings"))
async def cmd_settings(message: Message):
    user_id = message.from_user.id
    args = message.text.split(maxsplit=2)
    lang = "ru"
    user = supabase_db.db.get_user(user_id)
    if user:
        lang = user.get("language", "ru")

    # If just /settings – show current settings
    if len(args) == 1:
        if not user:
            user = supabase_db.db.ensure_user(user_id)
            lang = user.get("language", lang)
        tz = user.get("timezone", "UTC")
        lang_name = TEXTS[lang]['lang_ru'] if user.get("language") == "ru" else TEXTS[lang]['lang_en']
        date_fmt = user.get("date_format", "YYYY-MM-DD")
        time_fmt = user.get("time_format", "HH:MM")
        notify_val = user.get("notify_before", 0)
        notify_str = (str(notify_val) + (" мин." if lang == "ru" else " min")) if notify_val else ("выкл." if lang == "ru" else "off")

        msg = (
            f"Ваши настройки:\n"
            f"Часовой пояс: {tz}\n"
            f"Язык: {lang_name}\n"
            f"Формат даты: {date_fmt}\n"
            f"Формат времени: {time_fmt}\n"
            f"Уведомления: {notify_str}\n\n"
            "Для изменения настроек используйте команды:\n"
            "/settings tz Europe/Moscow — установить часовой пояс\n"
            "/settings lang ru — язык интерфейса (ru, en)\n"
            "/settings datefmt YYYY-MM-DD — формат даты (например: YYYY-MM-DD)\n"
            "/settings timefmt HH:MM — формат времени (например: HH:MM)\n"
            "/settings notify 10 — напоминание за N минут до публикации (0 — выкл.)\n"
        ) if lang == "ru" else (
            f"Your settings:\n"
            f"Timezone: {tz}\n"
            f"Language: {lang_name}\n"
            f"Date format: {date_fmt}\n"
            f"Time format: {time_fmt}\n"
            f"Notifications: {notify_str}\n\n"
            "To change settings, use commands:\n"
            "/settings tz Europe/Moscow — set timezone\n"
            "/settings lang en — interface language (ru, en)\n"
            "/settings datefmt YYYY-MM-DD — date format (e.g., YYYY-MM-DD)\n"
            "/settings timefmt HH:MM — time format (e.g., HH:MM)\n"
            "/settings notify 10 — reminder N minutes before posting (0 to disable)\n"
        )
        await message.answer(msg)
        return

    sub = args[1].lower()
    if sub in ("tz", "timezone", "часовой", "часовой_пояс"):
        if len(args) < 3:
            await message.answer(TEXTS[lang]['settings_timezone_usage'])
            return
        tz_input = args[2]
        try:
            ZoneInfo(tz_input)
        except Exception:
            await message.answer(TEXTS[lang]['settings_invalid_tz'])
            return
        supabase_db.db.update_user(user_id, {"timezone": tz_input})
        await message.answer(TEXTS[lang]['settings_tz_set'].format(tz=tz_input))
    elif sub in ("lang", "language", "язык"):
        if len(args) < 3:
            await message.answer(TEXTS[lang]['settings_language_usage'])
            return
        val = args[2].lower()
        if val in ("ru", "русский", "rus"):
            new_lang = "ru"
        elif val in ("en", "eng", "english", "английский"):
            new_lang = "en"
        else:
            await message.answer(TEXTS[lang]['settings_invalid_lang'])
            return
        supabase_db.db.update_user(user_id, {"language": new_lang})
        lang_name = "Русский" if new_lang == "ru" else "English"
        await message.answer(TEXTS[new_lang]['settings_lang_set'].format(lang_name=lang_name))
    elif sub in ("datefmt", "date_format", "формат_даты"):
        if len(args) < 3:
            await message.answer(TEXTS[lang]['settings_datefmt_usage'])
            return
        fmt = args[2].upper()
        if not ("Y" in fmt and "M" in fmt and "D" in fmt):
            await message.answer(TEXTS[lang]['settings_invalid_datefmt'])
            return
        supabase_db.db.update_user(user_id, {"date_format": fmt})
        await message.answer(TEXTS[lang]['settings_datefmt_set'].format(fmt=fmt))
    elif sub in ("timefmt", "time_format", "формат_времени"):
        if len(args) < 3:
            await message.answer(TEXTS[lang]['settings_timefmt_usage'])
            return
        fmt = args[2]
        if "H" not in fmt.upper() or "M" not in fmt.upper():
            await message.answer(TEXTS[lang]['settings_invalid_timefmt'])
            return
        supabase_db.db.update_user(user_id, {"time_format": fmt})
        await message.answer(TEXTS[lang]['settings_timefmt_set'].format(fmt=fmt))
    elif sub in ("notify", "notifications", "уведомления"):
        if len(args) < 3:
            await message.answer(TEXTS[lang]['settings_notify_usage'])
            return
        val = args[2].lower()
        if val in ("0", "off", "нет", "none"):
            minutes = 0
        else:
            try:
                minutes = int(val)
            except:
                minutes = None
        if minutes is None or minutes < 0:
            await message.answer(TEXTS[lang]['settings_invalid_notify'])
            return
        supabase_db.db.update_user(user_id, {"notify_before": minutes})
        msg = TEXTS[lang]['settings_notify_set'].format(minutes_str=("выключены" if lang == "ru" else "disabled") if minutes == 0 else (str(minutes) + (" мин." if lang == "ru" else " min")))
        await message.answer(msg)
    else:
        await message.answer(TEXTS[lang]['settings_unknown'])
