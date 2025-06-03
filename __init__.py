# Texts for bot messages
TEXTS = {
    "ru": {
        # Start and basic
        "start_welcome": """
🤖 **Добро пожаловать в бот управления каналами!**

Этот бот поможет вам автоматизировать публикацию постов в Telegram каналах.

**Основные возможности:**
• 📝 Создание и планирование постов
• 📺 Управление несколькими каналами
• ⏰ Автоматическая публикация по расписанию
• 🔄 Повторяющиеся посты
• 📊 Статистика публикаций

**Быстрый старт:**
1. Добавьте канал: `/channels add @ваш_канал`
2. Создайте пост: `/create` или `/quickpost`
3. Просмотрите посты: `/list`

Используйте `/help` для полной справки или `/menu` для главного меню.
""",
        "help": "Используйте /help для получения справки",
        
        # Channels
        "channels_list_title": "📋 **Ваши каналы:**",
        "channels_item": "• {name} (ID: {id})",
        "channels_item_current": "• {name} ✅",
        "channels_no_channels": "❌ У вас нет добавленных каналов. Используйте /channels add @канал",
        "channels_added": "✅ Канал {name} успешно добавлен!",
        "channels_removed": "✅ Канал успешно удален",
        "channels_not_found": "❌ Канал не найден",
        "channels_remove_confirm": "Вы уверены, что хотите удалить канал {name}?",
        "channels_unknown_command": "❌ Неизвестная команда. Используйте /help",
        
        # Posts
        "no_text": "[Пост без текста]",
        "confirm_publish": "📋 **Подтверждение публикации**\n\nКанал: {channel}\nВремя: {time}\n\nОпубликовать пост?",
        "confirm_post_published": "✅ Пост успешно опубликован!",
        "confirm_post_scheduled": "⏰ Пост запланирован на {time}",
        "confirm_post_cancel": "❌ Операция отменена",
        "confirm_post_saved": "📝 Черновик сохранен",
        "confirm_changes_saved": "✅ Изменения в посте #{id} сохранены",
        
        # Time formats
        "time_past_error": "❌ Время публикации должно быть в будущем!",
        "time_format_error": "❌ Неверный формат времени. Используйте формат: {format}",
        
        # Edit post
        "edit_usage": "Использование: /edit <post_id>",
        "edit_invalid_id": "❌ Неверный ID поста",
        "edit_post_not_found": "❌ Пост не найден или у вас нет доступа",
        "edit_post_published": "❌ Нельзя редактировать опубликованный пост",
        "edit_begin": "📝 **Редактирование поста #{id}**\n\nТекущий текст:\n{text}\n\nОтправьте новый текст или /skip",
        "edit_current_media": "Текущее медиа: {info}\nОтправьте новое медиа или /skip",
        "edit_no_media": "Медиа не прикреплено. Отправьте фото/видео или /skip",
        "edit_current_format": "Текущий формат: {format}\nОтправьте: html, markdown, none или /skip",
        "edit_current_buttons": "Текущие кнопки:\n{buttons_list}\n\nОтправьте новые кнопки или /skip",
        "edit_no_buttons": "Кнопки не добавлены. Отправьте кнопки в формате 'Текст | URL' или /skip",
        "edit_current_time": "Текущее время: {time}\nОтправьте новое время в формате {format} или /skip",
        "edit_time_error": "❌ Неверный формат времени. Используйте: {format}",
        "edit_current_repeat": "Текущий интервал повтора: {repeat}\nОтправьте новый (например: 1h, 1d) или /skip",
        "edit_repeat_error": "❌ Неверный формат интервала. Используйте: 1m, 1h, 1d",
        "edit_cancelled": "❌ Редактирование отменено",
        
        # Delete post
        "delete_usage": "Использование: /delete <post_id>",
        "delete_invalid_id": "❌ Неверный ID поста",
        "delete_not_found": "❌ Пост не найден",
        "delete_already_published": "❌ Нельзя удалить опубликованный пост",
        "delete_success": "✅ Пост #{id} успешно удален",
        
        # Projects
        "projects_list_title": "📁 **Ваши проекты:**",
        "projects_item": "• {name}",
        "projects_item_current": "• {name} ✅",
        "projects_not_found": "❌ Проект не найден",
        "projects_created": "✅ Проект '{name}' создан и активирован",
        "projects_switched": "✅ Переключен на проект '{name}'",
        "projects_invite_usage": "Использование: /project invite <user_id>",
        "projects_invite_not_found": "❌ Пользователь не найден. Он должен сначала запустить бота",
        "projects_invite_success": "✅ Пользователь {user_id} добавлен в проект",
        "projects_invited_notify": "Вас пригласили в проект '{project}' пользователь {user}",
        
        # Notifications
        "notify_message": "⏰ Пост #{id} будет опубликован в канал {channel} через {minutes} минут",
        "notify_message_less_min": "⏰ Пост #{id} будет опубликован в канал {channel} менее чем через минуту",
        "error_post_failed": "❌ Ошибка публикации поста #{id} в канал {channel}: {error}",
        
        # Media
        "media_photo": "фото",
        "media_video": "видео",
        "media_media": "медиа",
        
        # Buttons
        "yes_btn": "✅ Да",
        "no_btn": "❌ Нет",
    },
    "en": {
        # Start and basic
        "start_welcome": """
🤖 **Welcome to the Channel Management Bot!**

This bot will help you automate post publishing in Telegram channels.

**Main features:**
• 📝 Create and schedule posts
• 📺 Manage multiple channels
• ⏰ Automatic scheduled publishing
• 🔄 Repeating posts
• 📊 Publishing statistics

**Quick start:**
1. Add a channel: `/channels add @your_channel`
2. Create a post: `/create` or `/quickpost`
3. View posts: `/list`

Use `/help` for full guide or `/menu` for main menu.
""",
        "help": "Use /help for help",
        
        # Channels
        "channels_list_title": "📋 **Your channels:**",
        "channels_item": "• {name} (ID: {id})",
        "channels_item_current": "• {name} ✅",
        "channels_no_channels": "❌ No channels added. Use /channels add @channel",
        "channels_added": "✅ Channel {name} successfully added!",
        "channels_removed": "✅ Channel successfully removed",
        "channels_not_found": "❌ Channel not found",
        "channels_remove_confirm": "Are you sure you want to remove channel {name}?",
        "channels_unknown_command": "❌ Unknown command. Use /help",
        
        # Posts
        "no_text": "[Post without text]",
        "confirm_publish": "📋 **Publish confirmation**\n\nChannel: {channel}\nTime: {time}\n\nPublish post?",
        "confirm_post_published": "✅ Post successfully published!",
        "confirm_post_scheduled": "⏰ Post scheduled for {time}",
        "confirm_post_cancel": "❌ Operation cancelled",
        "confirm_post_saved": "📝 Draft saved",
        "confirm_changes_saved": "✅ Changes to post #{id} saved",
        
        # Time formats
        "time_past_error": "❌ Publication time must be in the future!",
        "time_format_error": "❌ Invalid time format. Use format: {format}",
        
        # Edit post
        "edit_usage": "Usage: /edit <post_id>",
        "edit_invalid_id": "❌ Invalid post ID",
        "edit_post_not_found": "❌ Post not found or access denied",
        "edit_post_published": "❌ Cannot edit published post",
        "edit_begin": "📝 **Editing post #{id}**\n\nCurrent text:\n{text}\n\nSend new text or /skip",
        "edit_current_media": "Current media: {info}\nSend new media or /skip",
        "edit_no_media": "No media attached. Send photo/video or /skip",
        "edit_current_format": "Current format: {format}\nSend: html, markdown, none or /skip",
        "edit_current_buttons": "Current buttons:\n{buttons_list}\n\nSend new buttons or /skip",
        "edit_no_buttons": "No buttons added. Send buttons as 'Text | URL' or /skip",
        "edit_current_time": "Current time: {time}\nSend new time in format {format} or /skip",
        "edit_time_error": "❌ Invalid time format. Use: {format}",
        "edit_current_repeat": "Current repeat interval: {repeat}\nSend new (e.g.: 1h, 1d) or /skip",
        "edit_repeat_error": "❌ Invalid interval format. Use: 1m, 1h, 1d",
        "edit_cancelled": "❌ Editing cancelled",
        
        # Delete post
        "delete_usage": "Usage: /delete <post_id>",
        "delete_invalid_id": "❌ Invalid post ID",
        "delete_not_found": "❌ Post not found",
        "delete_already_published": "❌ Cannot delete published post",
        "delete_success": "✅ Post #{id} successfully deleted",
        
        # Projects
        "projects_list_title": "📁 **Your projects:**",
        "projects_item": "• {name}",
        "projects_item_current": "• {name} ✅",
        "projects_not_found": "❌ Project not found",
        "projects_created": "✅ Project '{name}' created and activated",
        "projects_switched": "✅ Switched to project '{name}'",
        "projects_invite_usage": "Usage: /project invite <user_id>",
        "projects_invite_not_found": "❌ User not found. They must start the bot first",
        "projects_invite_success": "✅ User {user_id} added to project",
        "projects_invited_notify": "You were invited to project '{project}' by {user}",
        
        # Notifications
        "notify_message": "⏰ Post #{id} will be published to {channel} in {minutes} minutes",
        "notify_message_less_min": "⏰ Post #{id} will be published to {channel} in less than a minute",
        "error_post_failed": "❌ Failed to publish post #{id} to {channel}: {error}",
        
        # Media
        "media_photo": "photo",
        "media_video": "video",
        "media_media": "media",
        
        # Buttons
        "yes_btn": "✅ Yes",
        "no_btn": "❌ No",
    }
}
