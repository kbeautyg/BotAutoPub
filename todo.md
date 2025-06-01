# Telegram Bot Development Todo

## 1. Database Schema Design (SQL for Supabase)
- [ ] Design `users` table to store user-specific data (chat_id, timezone, etc.)
- [ ] Design `channels` table to store user's active channels (channel_id, channel_name, user_id)
- [ ] Design `posts` table to store post details (post_id, user_id, text, media, buttons, channels, scheduled_at, schedule_type, delete_after_publish, etc.)
- [ ] Design `post_media` table to store media files associated with posts (post_id, file_id, media_type)
- [ ] Design `post_buttons` table to store button details (post_id, button_text, button_url)
- [ ] Design `scheduled_tasks` table for cron-like tasks (task_id, post_id, task_type, scheduled_time, cron_schedule)
- [ ] Generate SQL migration script for Supabase.

## 2. Project Structure Setup
- [ ] Create `main.py` for bot entry point and main logic.
- [ ] Create `bot_states.py` for managing conversation states.
- [ ] Create `db_manager.py` for Supabase interactions.
- [ ] Create `telegram_utils.py` for Telegram API helpers (channel checks, media handling).
- [ ] Create `scheduler.py` for handling scheduled posts and deletions.
- [ ] Create `config.py` for bot token and Supabase credentials.
- [ ] Create `requirements.txt`.

## 3. Core Bot Logic - Initialization & State Management
- [ ] Implement `start` command.
- [ ] Implement conversation state machine.
- [ ] Implement "отмена" and "назад" commands for navigation.

## 4. Feature Implementation: Post Creation & Sending
- [ ] Implement "создать пост" command to initiate post creation.
- [ ] Step 1: Request text (Markdown/HTML or "–").
- [ ] Step 2: Request media (multiple files, "готово" or "пропустить").
- [ ] Step 3: Request channels (select from user's list).
- [ ] Step 4: Request buttons (optional, text and URL).
- [ ] Step 5: Request sending mode (instant or schedule).
    - [ ] If instant: send immediately, save to DB.
    - [ ] If schedule:
        - [ ] Request date/time for one-time post ("ДД.ММ.ГГГГ ЧЧ:ММ").
        - [ ] Validate future time, convert to UTC, save as scheduled.
        - [ ] Implement "запланировать циклически" option.
            - [ ] Request schedule type (daily/weekly/monthly/yearly).
            - [ ] Request specific details (days for weekly, date for monthly/yearly).
            - [ ] Request start date (or "сейчас") and optional end date (or "без конца").
            - [ ] Convert TZ to UTC, save as cron-like task.
- [ ] Step 6: Preview and confirmation.
- [ ] Implement automatic deletion after publication.
    - [ ] Request deletion rule (never, N hours/days, specific date/time).
    - [ ] Save parameters, create second task for deletion.

## 5. Feature Implementation: Channel Management
- [ ] Implement "добавить канал" command.
    - [ ] Request channel username/ID.
    - [ ] Verify user admin rights and bot admin rights via Telegram API.
    - [ ] Save as active channel.
    - [ ] Handle errors (no rights).
- [ ] Implement "удалить канал" command.
    - [ ] Request channel from user's list.
    - [ ] Mark as inactive.
    - [ ] Check related scheduled posts: remove channel, cancel post if no channels left, notify user.
- [ ] Implement "просмотр каналов" command.
    - [ ] Display active channels.
    - [ ] Suggest adding channels if none.

## 6. Feature Implementation: Scheduled Post Management
- [ ] Implement "просмотр постов" command.
    - [ ] Display all future scheduled posts (ID, text snippet, channels, schedule type, deletion rule).
    - [ ] Explain how to select ID for edit/cancel.
- [ ] Implement "редактировать пост [ID]" command.
    - [ ] Display current settings.
    - [ ] Allow step-by-step modification (text, media, buttons, channels, schedule, deletion rule).
    - [ ] Update DB, remove old task, create new task.
    - [ ] Preview and confirmation after changes.
- [ ] Implement "отменить пост [ID]" command.
    - [ ] Delete record, remove associated tasks.
    - [ ] Confirm cancellation.

## 7. Feature Implementation: Timezone Management
- [ ] Implement "сменить часовой пояс" command.
    - [ ] Request IANA timezone string.
    - [ ] Validate timezone.
    - [ ] Save to user profile.

## 8. General Checks & Validations
- [ ] Implement date/time format validation ("ДД.ММ.ГГГГ ЧЧ:ММ") and future time check.
- [ ] Implement admin rights checks for channels.
- [ ] Implement media file size (20MB) and format (jpg, png, mp4, gif, pdf) validation.
- [ ] Implement cyclic schedule correctness checks.
- [ ] Implement logging (INFO/WARNING/ERROR).

## 9. Deployment & Testing
- [ ] Set up environment variables for bot token and Supabase.
- [ ] Test all commands and flows.
- [ ] Ensure robust error handling.

## 10. Final Output
- [ ] Provide project structure.
- [ ] Provide SQL code for Supabase.
- [ ] Provide all file codes.