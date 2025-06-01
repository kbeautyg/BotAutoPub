from aiogram import Bot
from aiogram.types import ChatMemberAdministrator, ChatMemberOwner, Message, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto, InputMediaVideo, InputMediaDocument, InputMedia
from aiogram.exceptions import TelegramBadRequest
import config
import mimetypes

async def check_bot_admin_in_channel(bot: Bot, channel_id: int) -> bool:
    """Checks if the bot is an administrator in the given channel."""
    try:
        member = await bot.get_chat_member(chat_id=channel_id, user_id=bot.id)
        return isinstance(member, (ChatMemberAdministrator, ChatMemberOwner))
    except TelegramBadRequest:
        return False # Channel not found or bot not a member

async def check_user_admin_in_channel(bot: Bot, channel_id: int, user_id: int) -> bool:
    """Checks if the user is an administrator or owner in the given channel."""
    try:
        member = await bot.get_chat_member(chat_id=channel_id, user_id=user_id)
        return isinstance(member, (ChatMemberAdministrator, ChatMemberOwner))
    except TelegramBadRequest:
        return False

async def get_channel_info(bot: Bot, channel_identifier: str):
    """
    Gets channel info by username or ID.
    Returns (channel_id, channel_name) or None.
    """
    try:
        chat = await bot.get_chat(chat_id=channel_identifier)
        if chat.type in ['channel', 'supergroup']: # Supergroups can be used as channels
            return chat.id, chat.title
        return None
    except TelegramBadRequest:
        return None

def validate_media_file(message: Message) -> bool:
    """Validates if the attached media file meets size and type requirements."""
    file_size = 0
    file_type = None
    file_extension = None

    if message.photo:
        file_size = message.photo[-1].file_size # Get the largest photo size
        file_type = 'photo'
        # Photos don't have explicit extensions in message, rely on Telegram's handling
    elif message.video:
        file_size = message.video.file_size
        file_type = 'video'
        file_extension = message.video.mime_type.split('/')[-1] if message.video.mime_type else None
    elif message.document:
        file_size = message.document.file_size
        file_type = 'document'
        file_extension = message.document.file_name.split('.')[-1].lower() if message.document.file_name else None
    else:
        return False # No supported media found

    if file_size > config.MAX_MEDIA_SIZE_MB * 1024 * 1024:
        return False # File too large

    if file_type not in config.ALLOWED_MEDIA_TYPES:
        return False # Unsupported media type

    # Validate file extension for videos and documents
    if file_extension and file_type in config.ALLOWED_MEDIA_EXTENSIONS:
        if file_extension not in config.ALLOWED_MEDIA_EXTENSIONS[file_type]:
            return False

    return True

def get_media_file_id_and_type(message: Message):
    """Extracts file_id and media_type from a message."""
    if message.photo:
        return message.photo[-1].file_id, 'photo'
    elif message.video:
        return message.video.file_id, 'video'
    elif message.document:
        return message.document.file_id, 'document'
    return None, None

def create_inline_buttons(buttons_data: list) -> InlineKeyboardMarkup:
    """Creates an InlineKeyboardMarkup from a list of button data."""
    keyboard = []
    for btn in buttons_data:
        keyboard.append([InlineKeyboardButton(text=btn['button_text'], url=btn['button_url'])])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

async def send_post_to_channel(bot: Bot, channel_id: int, text: str, media_files: list, buttons_data: list = None):
    """Sends a post to a specified channel, handling media groups."""
    reply_markup = None
    if buttons_data:
        reply_markup = create_inline_buttons(buttons_data)

    if media_files:
        # Prepare media group
        media_group = []
        for i, media_item in enumerate(media_files):
            caption = text if i == 0 else None # Only first item has caption
            if media_item['media_type'] == 'photo':
                media_group.append(InputMediaPhoto(media=media_item['telegram_file_id'], caption=caption))
            elif media_item['media_type'] == 'video':
                media_group.append(InputMediaVideo(media=media_item['telegram_file_id'], caption=caption))
            elif media_item['media_type'] == 'document':
                # Documents cannot be part of a media group with photos/videos
                # If there's a document, it must be sent separately or as the only media.
                # For simplicity, if there's a document, we send it alone.
                # A more complex logic would separate documents from photo/video groups.
                if len(media_files) > 1 or media_item['media_type'] == 'document':
                    # If multiple media or the first is a document, send document alone
                    return await bot.send_document(chat_id=channel_id, document=media_item['telegram_file_id'], caption=text, reply_markup=reply_markup)
                else:
                    # This case should not be reached if document is handled above
                    pass
        
        if media_group:
            # Send media group if it contains photos/videos
            try:
                # send_media_group returns a list of messages, we need the first one for message_id
                sent_messages = await bot.send_media_group(chat_id=channel_id, media=media_group)
                # Attach reply_markup to the first message of the group if possible
                # Aiogram's send_media_group doesn't directly support reply_markup for the group.
                # It needs to be attached to the caption of the first item, but that's not a direct markup.
                # For now, buttons will only work if there's no media group, or if sent as single media.
                # This is a known limitation for media groups with buttons.
                # A workaround would be to send buttons as a separate message or use a different approach.
                # For this project, we'll accept this limitation for media groups.
                return sent_messages[0] if sent_messages else None
            except TelegramBadRequest as e:
                # If media group fails (e.g., mixed types not allowed), try sending first item alone
                if "can't be mixed" in str(e) and len(media_files) > 1:
                    # Fallback to sending only the first media item if group fails due to mixing
                    first_media = media_files[0]
                    if first_media['media_type'] == 'photo':
                        return await bot.send_photo(chat_id=channel_id, photo=first_media['telegram_file_id'], caption=text, reply_markup=reply_markup)
                    elif first_media['media_type'] == 'video':
                        return await bot.send_video(chat_id=channel_id, video=first_media['telegram_file_id'], caption=text, reply_markup=reply_markup)
                    elif first_media['media_type'] == 'document':
                        return await bot.send_document(chat_id=channel_id, document=first_media['telegram_file_id'], caption=text, reply_markup=reply_markup)
                raise e # Re-raise if it's another error
        else:
            # This case should only be reached if media_files was not empty but media_group was (e.g., only documents)
            # If there's only one document, it's handled above.
            # If there are multiple documents, this needs more complex handling.
            # For now, if media_group is empty, it means no photos/videos were suitable for group.
            # We'll send text only as a fallback.
            return await bot.send_message(chat_id=channel_id, text=text, reply_markup=reply_markup)
    else:
        return await bot.send_message(chat_id=channel_id, text=text, reply_markup=reply_markup)