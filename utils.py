import pytz
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import re
import json
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import logging

logger = logging.getLogger(__name__)

class TimeZoneManager:
    """Менеджер часовых поясов"""
    
    COMMON_TIMEZONES = {
        'UTC': 'UTC',
        'Москва': 'Europe/Moscow',
        'Киев': 'Europe/Kiev',
        'Минск': 'Europe/Minsk',
        'Алматы': 'Asia/Almaty',
        'Ташкент': 'Asia/Tashkent',
        'Баку': 'Asia/Baku',
        'Ереван': 'Asia/Yerevan',
        'Тбилиси': 'Asia/Tbilisi',
        'Нью-Йорк': 'America/New_York',
        'Лос-Анджелес': 'America/Los_Angeles',
        'Лондон': 'Europe/London',
        'Берлин': 'Europe/Berlin',
        'Токио': 'Asia/Tokyo',
        'Пекин': 'Asia/Shanghai'
    }
    
    @classmethod
    def get_timezone_keyboard(cls) -> InlineKeyboardMarkup:
        """Создать клавиатуру с часовыми поясами"""
        keyboard = []
        for name, tz in cls.COMMON_TIMEZONES.items():
            keyboard.append([InlineKeyboardButton(name, callback_data=f"tz_{tz}")])
        
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back_to_settings")])
        return InlineKeyboardMarkup(keyboard)
    
    @classmethod
    def convert_to_user_timezone(cls, utc_time: datetime, user_timezone: str) -> datetime:
        """Конвертировать UTC время в пользовательский часовой пояс"""
        try:
            utc_tz = pytz.UTC
            user_tz = pytz.timezone(user_timezone)
            
            if utc_time.tzinfo is None:
                utc_time = utc_tz.localize(utc_time)
            
            return utc_time.astimezone(user_tz)
        except Exception as e:
            logger.error(f"Ошибка конвертации времени: {e}")
            return utc_time
    
    @classmethod
    def convert_to_utc(cls, local_time: datetime, user_timezone: str) -> datetime:
        """Конвертировать локальное время в UTC"""
        try:
            user_tz = pytz.timezone(user_timezone)
            
            if local_time.tzinfo is None:
                local_time = user_tz.localize(local_time)
            
            return local_time.astimezone(pytz.UTC)
        except Exception as e:
            logger.error(f"Ошибка конвертации в UTC: {e}")
            return local_time

class TextFormatter:
    """Форматирование текста для Telegram"""
    
    @staticmethod
    def escape_html(text: str) -> str:
        """Экранировать HTML символы"""
        if not text:
            return ""
        return (text.replace('&', '&amp;')
                   .replace('<', '&lt;')
                   .replace('>', '&gt;'))
    
    @staticmethod
    def escape_markdown(text: str) -> str:
        """Экранировать Markdown символы"""
        if not text:
            return ""
        chars_to_escape = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
        for char in chars_to_escape:
            text = text.replace(char, f'\\{char}')
        return text
    
    @staticmethod
    def format_post_preview(text: str, media_type: str = None, 
                          buttons: List[List[Dict]] = None, parse_mode: str = 'HTML') -> str:
        """Создать превью поста"""
        preview = "📝 <b>Превью поста:</b>\n\n"
        
        if media_type:
            media_icons = {
                'photo': '🖼️',
                'video': '🎥',
                'document': '📄',
                'audio': '🎵',
                'voice': '🎤',
                'animation': '🎬'
            }
            preview += f"{media_icons.get(media_type, '📎')} <i>Медиа: {media_type}</i>\n\n"
        
        if text:
            preview += f"<b>Текст:</b>\n{text[:500]}{'...' if len(text) > 500 else ''}\n\n"
        
        if buttons:
            preview += "<b>Кнопки:</b>\n"
            for row in buttons:
                row_text = " | ".join([btn.get('text', 'Кнопка') for btn in row])
                preview += f"• {row_text}\n"
            preview += "\n"
        
        preview += f"<b>Форматирование:</b> {parse_mode}"
        
        return preview

class ButtonManager:
    """Менеджер кнопок для постов"""
    
    @staticmethod
    def parse_buttons_text(text: str) -> List[List[Dict]]:
        """Парсинг текста кнопок в формат для Telegram"""
        if not text.strip():
            return []
        
        buttons = []
        lines = text.strip().split('\n')
        
        for line in lines:
            if not line.strip():
                continue
            
            row = []
            # Формат: "Текст кнопки - ссылка" или "Текст кнопки | Текст кнопки 2 - ссылка"
            if '|' in line:
                # Несколько кнопок в ряду
                button_parts = line.split('|')
                for part in button_parts:
                    part = part.strip()
                    if ' - ' in part:
                        text, url = part.split(' - ', 1)
                        row.append({'text': text.strip(), 'url': url.strip()})
                    else:
                        row.append({'text': part, 'url': '#'})
            else:
                # Одна кнопка в ряду
                if ' - ' in line:
                    text, url = line.split(' - ', 1)
                    row.append({'text': text.strip(), 'url': url.strip()})
                else:
                    row.append({'text': line.strip(), 'url': '#'})
            
            if row:
                buttons.append(row)
        
        return buttons
    
    @staticmethod
    def create_inline_keyboard(buttons: List[List[Dict]]) -> Optional[InlineKeyboardMarkup]:
        """Создать InlineKeyboardMarkup из списка кнопок"""
        if not buttons:
            return None
        
        keyboard = []
        for row in buttons:
            keyboard_row = []
            for button in row:
                text = button.get('text', 'Кнопка')
                url = button.get('url', '#')
                
                if url and url != '#':
                    keyboard_row.append(InlineKeyboardButton(text, url=url))
                else:
                    # Если нет URL, создаем callback кнопку
                    keyboard_row.append(InlineKeyboardButton(text, callback_data=f"btn_{text}"))
            
            if keyboard_row:
                keyboard.append(keyboard_row)
        
        return InlineKeyboardMarkup(keyboard) if keyboard else None

class DateTimeParser:
    """Парсер даты и времени"""
    
    @staticmethod
    def parse_datetime_input(text: str, user_timezone: str = 'UTC') -> Optional[datetime]:
        """Парсинг ввода даты и времени"""
        text = text.strip().lower()
        
        try:
            # Попробуем разные форматы
            formats = [
                '%d.%m.%Y %H:%M',
                '%d.%m.%y %H:%M',
                '%d/%m/%Y %H:%M',
                '%d/%m/%y %H:%M',
                '%Y-%m-%d %H:%M',
                '%d.%m %H:%M',
                '%d/%m %H:%M',
                '%H:%M'
            ]
            
            now = datetime.now()
            user_tz = pytz.timezone(user_timezone)
            
            for fmt in formats:
                try:
                    if fmt == '%H:%M':
                        # Только время - используем сегодняшнюю дату
                        parsed_time = datetime.strptime(text, fmt).time()
                        parsed_dt = datetime.combine(now.date(), parsed_time)
                        
                        # Если время уже прошло сегодня, планируем на завтра
                        if parsed_dt <= now:
                            parsed_dt += timedelta(days=1)
                    
                    elif fmt in ['%d.%m %H:%M', '%d/%m %H:%M']:
                        # Дата без года - используем текущий год
                        parsed_dt = datetime.strptime(f"{text} {now.year}", f"{fmt} %Y")
                        
                        # Если дата уже прошла в этом году, используем следующий год
                        if parsed_dt <= now:
                            parsed_dt = parsed_dt.replace(year=now.year + 1)
                    
                    else:
                        parsed_dt = datetime.strptime(text, fmt)
                    
                    # Локализуем время в пользовательском часовом поясе
                    if parsed_dt.tzinfo is None:
                        parsed_dt = user_tz.localize(parsed_dt)
                    
                    # Конвертируем в UTC
                    return parsed_dt.astimezone(pytz.UTC)
                
                except ValueError:
                    continue
            
            # Попробуем относительные форматы
            relative_patterns = {
                r'через (\d+) мин': lambda m: now + timedelta(minutes=int(m.group(1))),
                r'через (\d+) час': lambda m: now + timedelta(hours=int(m.group(1))),
                r'через (\d+) дн': lambda m: now + timedelta(days=int(m.group(1))),
                r'завтра в (\d{1,2}):(\d{2})': lambda m: (now + timedelta(days=1)).replace(
                    hour=int(m.group(1)), minute=int(m.group(2)), second=0, microsecond=0
                ),
                r'сегодня в (\d{1,2}):(\d{2})': lambda m: now.replace(
                    hour=int(m.group(1)), minute=int(m.group(2)), second=0, microsecond=0
                )
            }
            
            for pattern, func in relative_patterns.items():
                match = re.search(pattern, text)
                if match:
                    result_dt = func(match)
                    # Локализуем и конвертируем в UTC
                    if result_dt.tzinfo is None:
                        result_dt = user_tz.localize(result_dt)
                    return result_dt.astimezone(pytz.UTC)
            
        except Exception as e:
            logger.error(f"Ошибка парсинга даты/времени '{text}': {e}")
        
        return None
    
    @staticmethod
    def format_datetime(dt: datetime, user_timezone: str = 'UTC', 
                       include_seconds: bool = False) -> str:
        """Форматирование даты и времени для отображения"""
        try:
            # Конвертируем в пользовательский часовой пояс
            user_dt = TimeZoneManager.convert_to_user_timezone(dt, user_timezone)
            
            fmt = '%d.%m.%Y %H:%M'
            if include_seconds:
                fmt += ':%S'
            
            return user_dt.strftime(fmt)
        except Exception as e:
            logger.error(f"Ошибка форматирования даты: {e}")
            return str(dt)

def create_main_menu_keyboard(is_admin: bool = False) -> InlineKeyboardMarkup:
    """Создать главное меню"""
    keyboard = []
    
    if is_admin:
        keyboard.extend([
            [InlineKeyboardButton("📝 Создать пост", callback_data="create_post")],
            [InlineKeyboardButton("📋 Отложенные посты", callback_data="scheduled_posts")],
            [InlineKeyboardButton("📺 Управление каналами", callback_data="manage_channels")],
            [InlineKeyboardButton("⚙️ Настройки", callback_data="settings")],
            [InlineKeyboardButton("📊 Статистика", callback_data="statistics")]
        ])
    else:
        keyboard.extend([
            [InlineKeyboardButton("ℹ️ Информация", callback_data="info")],
            [InlineKeyboardButton("⚙️ Настройки", callback_data="settings")]
        ])
    
    return InlineKeyboardMarkup(keyboard)

def create_back_button(callback_data: str = "main_menu") -> InlineKeyboardMarkup:
    """Создать кнопку назад"""
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data=callback_data)]])

def create_cancel_button() -> InlineKeyboardMarkup:
    """Создать кнопку отмены"""
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отменить", callback_data="cancel")]])

def truncate_text(text: str, max_length: int = 100) -> str:
    """Обрезать текст до указанной длины"""
    if len(text) <= max_length:
        return text
    return text[:max_length-3] + "..."

def validate_url(url: str) -> bool:
    """Проверить валидность URL"""
    url_pattern = re.compile(
        r'^https?://'  # http:// or https://
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain...
        r'localhost|'  # localhost...
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
        r'(?::\d+)?'  # optional port
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)
    return url_pattern.match(url) is not None