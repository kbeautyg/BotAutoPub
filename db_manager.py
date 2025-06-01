from supabase import create_client, Client
import config
from datetime import datetime

class DBManager:
    def __init__(self):
        self.supabase: Client = create_client(config.SUPABASE_URL, config.SUPABASE_KEY)

    async def get_user(self, chat_id: int):
        response = self.supabase.from_('users').select('*').eq('chat_id', chat_id).execute()
        if response.data:
            return response.data[0]
        return None

    async def create_user(self, chat_id: int, username: str = None, first_name: str = None, last_name: str = None):
        response = self.supabase.from_('users').insert({
            'chat_id': chat_id,
            'username': username,
            'first_name': first_name,
            'last_name': last_name
        }).execute()
        return response.data[0]

    async def update_user_timezone(self, user_id: str, timezone: str): # Changed from chat_id to user_id
        response = self.supabase.from_('users').update({'timezone': timezone}).eq('id', user_id).execute()
        return response.data[0]

    async def get_user_channels(self, user_id: str):
        response = self.supabase.from_('channels').select('*').eq('user_id', user_id).eq('is_active', True).execute()
        return response.data

    async def add_channel(self, user_id: str, telegram_channel_id: int, channel_name: str):
        response = self.supabase.from_('channels').insert({
            'user_id': user_id,
            'telegram_channel_id': telegram_channel_id,
            'channel_name': channel_name
        }).execute()
        return response.data[0]

    async def deactivate_channel(self, user_id: str, channel_db_id: str): # Changed from telegram_channel_id to channel_db_id
        response = self.supabase.from_('channels').update({'is_active': False}).eq('user_id', user_id).eq('id', channel_db_id).execute()
        return response.data[0]

    async def get_post(self, post_id: str):
        response = self.supabase.from_('posts').select('*').eq('id', post_id).execute()
        if response.data:
            return response.data[0]
        return None

    async def create_post(self, user_id: str, text: str = None, status: str = 'draft'):
        response = self.supabase.from_('posts').insert({
            'user_id': user_id,
            'text': text,
            'status': status
        }).execute()
        return response.data[0]

    async def update_post(self, post_id: str, data: dict):
        response = self.supabase.from_('posts').update(data).eq('id', post_id).execute()
        return response.data[0]

    async def add_post_media(self, post_id: str, telegram_file_id: str, media_type: str):
        response = self.supabase.from_('post_media').insert({
            'post_id': post_id,
            'telegram_file_id': telegram_file_id,
            'media_type': media_type
        }).execute()
        return response.data[0]

    async def get_post_media(self, post_id: str):
        response = self.supabase.from_('post_media').select('*').eq('post_id', post_id).execute()
        return response.data

    async def delete_post_media(self, post_id: str):
        response = self.supabase.from_('post_media').delete().eq('post_id', post_id).execute()
        return response.data

    async def add_post_button(self, post_id: str, button_text: str, button_url: str, button_order: int):
        response = self.supabase.from_('post_buttons').insert({
            'post_id': post_id,
            'button_text': button_text,
            'button_url': button_url,
            'button_order': button_order
        }).execute()
        return response.data[0]

    async def get_post_buttons(self, post_id: str):
        response = self.supabase.from_('post_buttons').select('*').eq('post_id', post_id).order('button_order').execute()
        return response.data

    async def delete_post_buttons(self, post_id: str):
        response = self.supabase.from_('post_buttons').delete().eq('post_id', post_id).execute()
        return response.data

    async def add_post_channel(self, post_id: str, channel_id: str):
        response = self.supabase.from_('post_channels').insert({
            'post_id': post_id,
            'channel_id': channel_id
        }).execute()
        return response.data[0]

    async def get_post_channels(self, post_id: str):
        response = self.supabase.from_('post_channels').select('*, channels(channel_name, telegram_channel_id)').eq('post_id', post_id).execute()
        return response.data

    async def delete_post_channels(self, post_id: str):
        response = self.supabase.from_('post_channels').delete().eq('post_id', post_id).execute()
        return response.data

    async def get_scheduled_posts(self, user_id: str):
        response = self.supabase.from_('posts').select('*, post_channels(channels(channel_name)), post_media(telegram_file_id, media_type)').eq('user_id', user_id).in_('status', ['scheduled', 'draft']).execute()
        return response.data

    async def delete_post_full(self, post_id: str):
        # Supabase cascade delete should handle related tables, but explicit deletion can be safer
        await self.supabase.from_('post_media').delete().eq('post_id', post_id).execute()
        await self.supabase.from_('post_buttons').delete().eq('post_id', post_id).execute()
        await self.supabase.from_('post_channels').delete().eq('post_id', post_id).execute()
        await self.supabase.from_('scheduled_tasks').delete().eq('post_id', post_id).execute()
        response = self.supabase.from_('posts').delete().eq('id', post_id).execute()
        return response.data

    async def add_scheduled_task(self, post_id: str, task_type: str, scheduled_time: datetime = None, cron_expression: str = None):
        data = {
            'post_id': post_id,
            'task_type': task_type,
            'is_active': True
        }
        if scheduled_time:
            data['scheduled_time'] = scheduled_time.isoformat() # Convert datetime to ISO string for Supabase
        if cron_expression:
            data['cron_expression'] = cron_expression
        response = self.supabase.from_('scheduled_tasks').insert(data).execute()
        return response.data[0]

    async def get_active_scheduled_tasks(self):
        response = self.supabase.from_('scheduled_tasks').select('*, posts(*, post_media(*), post_buttons(*), post_channels(channels(*)))').eq('is_active', True).execute()
        return response.data

    async def deactivate_scheduled_task(self, task_id: str):
        response = self.supabase.from_('scheduled_tasks').update({'is_active': False}).eq('id', task_id).execute()
        return response.data[0]

    async def get_user_by_id(self, user_id: str):
        response = self.supabase.from_('users').select('*').eq('id', user_id).execute()
        if response.data:
            return response.data[0]
        return None

    async def get_channel_by_telegram_id(self, telegram_channel_id: int):
        response = self.supabase.from_('channels').select('*').eq('telegram_channel_id', telegram_channel_id).execute()
        if response.data:
            return response.data[0]
        return None

    async def get_channel_by_id(self, channel_id: str):
        response = self.supabase.from_('channels').select('*').eq('id', channel_id).execute()
        if response.data:
            return response.data[0]
        return None

    async def get_posts_by_channel_id(self, channel_id: str):
        response = self.supabase.from_('post_channels').select('post_id').eq('channel_id', channel_id).execute()
        return [item['post_id'] for item in response.data]

    async def remove_channel_from_post(self, post_id: str, channel_id: str):
        response = self.supabase.from_('post_channels').delete().eq('post_id', post_id).eq('channel_id', channel_id).execute()
        return response.data

    async def get_post_channel_count(self, post_id: str):
        response = self.supabase.from_('post_channels').select('count', count='exact').eq('post_id', post_id).execute()
        return response.count