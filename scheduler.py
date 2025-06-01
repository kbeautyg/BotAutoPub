from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime, timedelta
import pytz
import logging

from db_manager import DBManager
from telegram_utils import send_post_to_channel
import config

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class Scheduler:
    def __init__(self, bot, db_manager: DBManager):
        self.scheduler = AsyncIOScheduler()
        self.bot = bot
        self.db_manager = db_manager
        self.scheduler.start()
        logging.info("Scheduler started.")

    async def _send_post_job(self, post_id: str):
        """Job to send a post."""
        logging.info(f"Attempting to send post {post_id}")
        post = await self.db_manager.get_post(post_id)
        if not post or post['status'] != 'scheduled':
            logging.warning(f"Post {post_id} not found or not in 'scheduled' status. Skipping send.")
            return

        media_files = await self.db_manager.get_post_media(post_id)
        buttons_data = await self.db_manager.get_post_buttons(post_id)
        post_channels_data = await self.db_manager.get_post_channels(post_id)

        sent_messages = []
        for pc_data in post_channels_data:
            channel_info = pc_data['channels']
            if channel_info:
                try:
                    message_obj = await send_post_to_channel(
                        self.bot,
                        channel_info['telegram_channel_id'],
                        post['text'],
                        media_files,
                        buttons_data
                    )
                    if message_obj: # Check if message was actually sent and returned
                        sent_messages.append({'channel_id': channel_info['id'], 'message_id': message_obj.message_id})
                        logging.info(f"Post {post_id} sent to channel {channel_info['channel_name']} ({channel_info['telegram_channel_id']})")
                    else:
                        logging.warning(f"send_post_to_channel returned None for post {post_id} to channel {channel_info['channel_name']}.")
                except Exception as e:
                    logging.error(f"Failed to send post {post_id} to channel {channel_info['channel_name']}: {e}")
        
        if sent_messages:
            await self.db_manager.update_post(post_id, {'status': 'sent'})
            logging.info(f"Post {post_id} status updated to 'sent'.")
            
            # Schedule deletion if configured
            if post['delete_after_publish_type'] != 'never':
                delete_time = None
                if post['delete_after_publish_type'] == 'hours':
                    delete_time = datetime.now(pytz.utc) + timedelta(hours=post['delete_after_publish_value'])
                elif post['delete_after_publish_type'] == 'days':
                    delete_time = datetime.now(pytz.utc) + timedelta(days=post['delete_after_publish_value'])
                elif post['delete_after_publish_type'] == 'specific_date':
                    # Ensure delete_at is a datetime object, not string
                    if isinstance(post['delete_at'], str):
                        delete_time = datetime.fromisoformat(post['delete_at'])
                    else:
                        delete_time = post['delete_at']

                if delete_time:
                    # IMPORTANT: sent_messages are not persisted across restarts for deletion jobs in this example.
                    # A robust solution would store sent message IDs in the DB (e.g., in a new table linked to posts)
                    # and retrieve them here. For this project, we acknowledge this limitation.
                    self.add_one_time_job(
                        job_func=self._delete_post_job,
                        run_date=delete_time,
                        args=[post_id, sent_messages], # sent_messages will be lost on restart
                        job_id=f"delete_post_{post_id}_{delete_time.timestamp()}" # Unique ID for deletion job
                    )
                    logging.info(f"Deletion job for post {post_id} scheduled for {delete_time}.")
        else:
            logging.warning(f"Post {post_id} was not sent to any channel. Status remains 'scheduled'.")


    async def _delete_post_job(self, post_id: str, sent_messages: list):
        """Job to delete a post from channels."""
        logging.info(f"Attempting to delete post {post_id} from channels.")
        if not sent_messages:
            logging.warning(f"No sent_messages provided for deletion of post {post_id}. Cannot delete from channels.")
            # In a robust system, we would fetch sent message IDs from DB here.
            return

        for msg_info in sent_messages:
            channel_db_info = await self.db_manager.get_channel_by_id(msg_info['channel_id'])
            if channel_db_info:
                try:
                    await self.bot.delete_message(chat_id=channel_db_info['telegram_channel_id'], message_id=msg_info['message_id'])
                    logging.info(f"Post {post_id} deleted from channel {channel_db_info['channel_name']}.")
                except Exception as e:
                    logging.error(f"Failed to delete message {msg_info['message_id']} from channel {channel_db_info['channel_name']}: {e}")
            else:
                logging.warning(f"Channel with ID {msg_info['channel_id']} not found for deletion of post {post_id}.")
        
        # Optionally, update post status to 'deleted' or similar in DB
        # await self.db_manager.update_post(post_id, {'status': 'deleted'})
        logging.info(f"Deletion process for post {post_id} completed.")


    def add_one_time_job(self, job_func, run_date: datetime, args: list = None, job_id: str = None):
        """Adds a one-time job to the scheduler."""
        if run_date < datetime.now(pytz.utc):
            logging.warning(f"Attempted to schedule job {job_id} in the past. Skipping.")
            return None
        
        job = self.scheduler.add_job(job_func, 'date', run_date=run_date, args=args, id=job_id)
        logging.info(f"One-time job '{job_id}' scheduled for {run_date.isoformat()}")
        return job

    def add_recurring_job(self, job_func, cron_expression: str, args: list = None, job_id: str = None, start_date: datetime = None, end_date: datetime = None):
        """Adds a recurring job to the scheduler using a cron expression."""
        try:
            trigger = CronTrigger.from_crontab(cron_expression, timezone=pytz.utc)
            job = self.scheduler.add_job(job_func, trigger, args=args, id=job_id, start_date=start_date, end_date=end_date)
            logging.info(f"Recurring job '{job_id}' scheduled with cron: '{cron_expression}' (start: {start_date}, end: {end_date})")
            return job
        except Exception as e:
            logging.error(f"Failed to add recurring job {job_id} with cron '{cron_expression}': {e}")
            return None

    def remove_job(self, job_id: str):
        """Removes a job from the scheduler."""
        try:
            self.scheduler.remove_job(job_id)
            logging.info(f"Job '{job_id}' removed from scheduler.")
            return True
        except Exception as e:
            logging.warning(f"Job '{job_id}' not found or could not be removed: {e}")
            return False

    async def load_existing_tasks(self):
        """Loads active scheduled tasks from the database and adds them to the scheduler."""
        logging.info("Loading existing scheduled tasks from DB...")
        tasks = await self.db_manager.get_active_scheduled_tasks()
        for task in tasks:
            post_id = task['post_id']
            job_id = f"{task['task_type']}_{task['id']}" # Unique job ID
            
            if task['task_type'] == 'send_post':
                if task['scheduled_time']: # One-time send
                    run_date = datetime.fromisoformat(task['scheduled_time'])
                    self.add_one_time_job(self._send_post_job, run_date, args=[post_id], job_id=job_id)
                elif task['cron_expression']: # Recurring send
                    start_date = datetime.fromisoformat(task['posts']['start_date']) if task['posts']['start_date'] else None
                    end_date = datetime.fromisoformat(task['posts']['end_date']) if task['posts']['end_date'] else None
                    self.add_recurring_job(self._send_post_job, task['cron_expression'], args=[post_id], job_id=job_id, start_date=start_date, end_date=end_date)
            elif task['task_type'] == 'delete_post':
                if task['scheduled_time']: # One-time delete
                    # As noted, sent_messages are not persisted. This job will likely fail to delete.
                    # A robust solution needs to store sent_messages in DB.
                    run_date = datetime.fromisoformat(task['scheduled_time'])
                    self.add_one_time_job(self._delete_post_job, run_date, args=[post_id, []], job_id=job_id) # Empty list for sent_messages
            
        logging.info(f"Loaded {len(tasks)} active tasks.")