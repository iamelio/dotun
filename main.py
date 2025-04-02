from telethon import TelegramClient, events
from telethon.tl.types import DocumentAttributeFilename, KeyboardButton, KeyboardButtonRow
from telethon.tl.custom import Button
import os
import logging
import asyncio
from configparser import ConfigParser
from datetime import datetime, timedelta
import humanize
import re
from utils.config import load_config
from handlers.commands import start_command, help_command
from handlers.messages import handle_messages, handle_callback

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Load configuration
config = load_config()

# Initialize the client
client = TelegramClient(config['session_name'],
                        config['api_id'], config['api_hash'])

# Register command handlers
client.add_event_handler(start_command, events.NewMessage(pattern='/start'))
client.add_event_handler(help_command, events.NewMessage(pattern='/help'))

# Register message and callback handlers
client.add_event_handler(lambda e: handle_messages(
    e, client), events.NewMessage())
client.add_event_handler(lambda e: handle_callback(
    e, client), events.CallbackQuery())

# Dictionary to store pending rename operations
pending_renames = {}

# Dictionary to store active operations
active_operations = {}


def get_file_info(message):
    """Extract file information from the message."""
    if not message.media:
        return None

    file_attrs = []
    for attr in message.media.document.attributes:
        if isinstance(attr, DocumentAttributeFilename):
            file_attrs.append(attr)

    file_name = file_attrs[0].file_name if file_attrs else "Unknown"
    file_size = message.media.document.size
    mime_type = message.media.document.mime_type

    return {
        'name': file_name,
        'size': file_size,
        'mime_type': mime_type
    }


async def rename_and_send_file(event, file_message, new_name, status_msg, as_file):
    """download, rename, and send back the file."""
    user_id = event.sender_id
    operation_id = f"{user_id}_{file_message.id}"
    active_operations[operation_id] = {'cancelled': False}

    start_time = datetime.now()
    last_update_time = start_time
    downloaded_size = 0
    total_size = file_message.media.document.size

    # Add cancel button to status message
    keyboard = [[Button.inline("❌ Cancel", "cancel")]]
    await status_msg.edit("📥 preparing to download...", buttons=keyboard)

    def progress_callback(current, total):
        nonlocal downloaded_size, last_update_time
        downloaded_size = current
        current_time = datetime.now()

        # Update progress every 2 seconds
        if (current_time - last_update_time).total_seconds() >= 2:
            speed = current / (current_time - start_time).total_seconds()
            eta = (total - current) / speed if speed > 0 else 0

            progress = (current / total) * 100
            status_text = (
                f"📥 downloading...\n\n"
                f"progress: {progress:.1f}%\n"
                f"downloaded: {humanize.naturalsize(current)} / {humanize.naturalsize(total)}\n"
                f"speed: {humanize.naturalsize(speed)}/s\n"
                f"ETA: {humanize.naturaltime(datetime.now() + timedelta(seconds=eta), future=True)}"
            )
            if not active_operations[operation_id]['cancelled']:
                asyncio.create_task(status_msg.edit(
                    status_text, buttons=keyboard))
            last_update_time = current_time

    # Get the file
    download_path = await file_message.download_media(
        'downloads/',
        progress_callback=progress_callback
    )

    if active_operations[operation_id]['cancelled']:
        await status_msg.edit("❌ Download cancelled.")
        return

    if not download_path:
        await status_msg.edit('failed to download the file. please try again.')
        return

    # Get original file extension
    _, original_ext = os.path.splitext(download_path)

    # Check if new name has an extension
    if '.' not in new_name:
        # If no extension in new name, use the original
        new_name += original_ext

    # Create a new path for the renamed file
    new_path = os.path.join('downloads', new_name)

    try:
        # Rename the file
        os.rename(download_path, new_path)

        # Update status message for upload with cancel button
        await status_msg.edit(f'📤 preparing to upload "{new_name}"...', buttons=keyboard)

        # Create upload progress callback
        upload_start_time = datetime.now()
        upload_last_update = upload_start_time

        def upload_progress_callback(current, total):
            nonlocal upload_last_update
            current_time = datetime.now()

            # Update progress every 2 seconds
            if (current_time - upload_last_update).total_seconds() >= 2:
                speed = current / \
                    (current_time - upload_start_time).total_seconds()
                eta = (total - current) / speed if speed > 0 else 0
                progress = (current / total) * 100

                status_text = (
                    f"📤 uploading...\n\n"
                    f"progress: {progress:.1f}%\n"
                    f"uploaded: {humanize.naturalsize(current)} / {humanize.naturalsize(total)}\n"
                    f"speed: {humanize.naturalsize(speed)}/s\n"
                    f"ETA: {humanize.naturaltime(datetime.now() + timedelta(seconds=eta), future=True)}"
                )
                if not active_operations[operation_id]['cancelled']:
                    asyncio.create_task(status_msg.edit(
                        status_text, buttons=keyboard))
                upload_last_update = current_time

        # Send the renamed file with upload progress
        await client.send_file(
            event.chat_id,
            new_path,
            caption=f'**{new_name}**',
            parse_mode='md',
            as_file=as_file,
            progress_callback=upload_progress_callback
        )

        if not active_operations[operation_id]['cancelled']:
            await status_msg.edit('✅ done!', buttons=None)
    except Exception as e:
        logger.error(f"Error in rename_and_send_file: {e}")
        raise
    finally:
        # Clean up files
        try:
            if os.path.exists(new_path):
                os.remove(new_path)
            if os.path.exists(download_path) and download_path != new_path:
                os.remove(download_path)
        except Exception as e:
            logger.error(f"Error cleaning up files: {e}")
        # Clean up operation state
        if operation_id in active_operations:
            del active_operations[operation_id]


async def main():
    """Start the bot."""
    # Create download directory if it doesn't exist
    os.makedirs('downloads', exist_ok=True)

    # Connect and start the client
    await client.start(bot_token=config['bot_token'])

    # Print bot information
    me = await client.get_me()
    print(f"Bot started as @{me.username}")

    # Run the client until disconnected
    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
