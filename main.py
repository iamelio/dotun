from telethon import TelegramClient, events
from telethon.tl.types import DocumentAttributeFilename
import os
import logging
import asyncio
from configparser import ConfigParser
from datetime import datetime, timedelta
import humanize

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Read configuration
config = ConfigParser()
config.read('config.ini')

# Telegram API credentials
API_ID = config.get('Telegram', 'api_id')
API_HASH = config.get('Telegram', 'api_hash')
BOT_TOKEN = config.get('Telegram', 'bot_token')
SESSION_NAME = 'renamer_bot'

# Initialize the client
client = TelegramClient(SESSION_NAME, API_ID, API_HASH)

# Dictionary to store pending rename operations
pending_renames = {}


@client.on(events.NewMessage(pattern='/start'))
async def start_command(event):
    """Handle the /start command."""
    await event.respond('Welcome to the File Renamer Bot! 📁✨\n\n'
                        'Forward me any file, and I\'ll help you rename it.\n'
                        'To use, simply:\n'
                        '1. Forward a file to me\n'
                        '2. Reply to the file with the new name you want\n'
                        '3. I\'ll send you back the renamed file')
    raise events.StopPropagation


@client.on(events.NewMessage(pattern='/help'))
async def help_command(event):
    """Handle the /help command."""
    await event.respond('📚 **File Renamer Bot Help**\n\n'
                        'This bot helps you rename any file on Telegram. Here\'s how to use it:\n\n'
                        '**Commands:**\n'
                        '/start - Start the bot\n'
                        '/help - Show this help message\n\n'
                        '**To rename a file:**\n'
                        '1. Forward or send a file to this bot\n'
                        '2. Reply to that file with the new filename\n'
                        '3. I\'ll process and send back the renamed file\n\n'
                        '✅ Works with files of any size!\n'
                        '✅ Preserves file extension if you don\'t specify one')
    raise events.StopPropagation


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


@client.on(events.NewMessage)
async def handle_messages(event):
    """Handle incoming messages."""
    user_id = event.sender_id

    # Handle file uploads
    if event.message.media and not event.message.text.startswith('/'):
        # Get file information
        file_info = get_file_info(event.message)
        if not file_info:
            await event.respond('Sorry, I could not process this file.')
            return

        # Store the message ID and file info for later reference
        pending_renames[user_id] = {
            'message_id': event.message.id,
            'file_info': file_info
        }

        # Reply with file information
        info_text = (
            f"📄 **File Information**\n\n"
            f"Name: `{file_info['name']}`\n"
            f"Size: {humanize.naturalsize(file_info['size'])}\n"
            f"Type: `{file_info['mime_type']}`\n\n"
            "Please reply with the new name for the file."
        )
        info_msg = await event.respond(info_text, parse_mode='md')

        # Store the info message ID to delete it later
        pending_renames[user_id]['info_msg_id'] = info_msg.id

    # Handle rename requests
    elif event.message.is_reply and not event.message.media and not event.message.text.startswith('/'):
        # Check if this is a reply to a file we're tracking
        replied_msg = await event.message.get_reply_message()

        if user_id in pending_renames and replied_msg.id == pending_renames[user_id]['message_id']:
            # This is a rename request
            new_name = event.message.text.strip()

            # Delete the info message
            try:
                await client.delete_messages(event.chat_id, pending_renames[user_id]['info_msg_id'])
            except Exception as e:
                logger.error(f"Error deleting info message: {e}")

            # Ask for file type selection
            file_type_msg = await event.respond(
                "Please select the output file type:\n\n"
                "1️⃣ Document (as_file=True)\n"
                "2️⃣ Original Format (as_file=False)\n\n"
                "Reply with 1 or 2 to choose."
            )

            # Store the new name and file type message ID
            pending_renames[user_id]['new_name'] = new_name
            pending_renames[user_id]['file_type_msg_id'] = file_type_msg.id
        else:
            # Reply to a message that isn't a file we're tracking
            await event.respond('Please send a file first, then reply to it with the new name.')

    # Handle file type selection
    elif user_id in pending_renames and 'file_type_msg_id' in pending_renames[user_id]:
        if event.message.text in ['1', '2']:
            # Delete the file type selection message
            try:
                await client.delete_messages(event.chat_id, pending_renames[user_id]['file_type_msg_id'])
            except Exception as e:
                logger.error(f"Error deleting file type message: {e}")

            as_file = event.message.text == '1'
            status_msg = await event.respond('Starting file processing... Please wait.')

            try:
                await rename_and_send_file(
                    event,
                    await event.client.get_messages(event.chat_id, ids=pending_renames[user_id]['message_id']),
                    pending_renames[user_id]['new_name'],
                    status_msg,
                    as_file
                )
                # Clear the pending rename after successful processing
                del pending_renames[user_id]
            except Exception as e:
                logger.error(f"Error renaming file: {e}")
                await status_msg.edit(f"Sorry, an error occurred while renaming your file: {str(e)}")
        else:
            await event.respond('Please reply with either 1 or 2 to select the file type.')


async def rename_and_send_file(event, file_message, new_name, status_msg, as_file):
    """Download, rename, and send back the file."""
    start_time = datetime.now()
    last_update_time = start_time
    downloaded_size = 0
    total_size = file_message.media.document.size

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
                f"📥 Downloading...\n\n"
                f"Progress: {progress:.1f}%\n"
                f"Downloaded: {humanize.naturalsize(current)} / {humanize.naturalsize(total)}\n"
                f"Speed: {humanize.naturalsize(speed)}/s\n"
                f"ETA: {humanize.naturaltime(datetime.now() + timedelta(seconds=eta), future=True)}"
            )
            asyncio.create_task(status_msg.edit(status_text))
            last_update_time = current_time

    # Get the file
    download_path = await file_message.download_media(
        'downloads/',
        progress_callback=progress_callback
    )

    if not download_path:
        await status_msg.edit('Failed to download the file. Please try again.')
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

        # Update status message
        await status_msg.edit(f'📤 Uploading "{new_name}"... This might take a while for large files.')

        # Send the renamed file
        await client.send_file(
            event.chat_id,
            new_path,
            caption=f'Here is your renamed file: **{new_name}**',
            parse_mode='md',
            as_file=as_file
        )

        # Update status message
        await status_msg.edit('✅ File renamed and uploaded successfully!')
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


async def main():
    """Start the bot."""
    # Connect and start the client
    await client.start(bot_token=BOT_TOKEN)

    # Print bot information
    me = await client.get_me()
    logger.info(f"Bot started as @{me.username}")

    # Run the client until disconnected
    await client.run_until_disconnected()

if __name__ == '__main__':
    # Create download directory if it doesn't exist
    os.makedirs('downloads', exist_ok=True)

    # Run the bot
    asyncio.run(main())
