from telethon import TelegramClient, events, types
from telethon.tl.types import KeyboardButton, KeyboardButtonRow
import os
import logging
import asyncio
from configparser import ConfigParser
import humanize
import re
from utils.config import load_config
from handlers.commands import start_command, help_command
from handlers.messages import handle_messages, handle_callback
import aiohttp
# Import from our centralized module instead
import telegram_file_transfer as tft

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Load configuration
config = load_config()

# Initialize the client with optimized settings
client = TelegramClient(
    config['session_name'],
    int(config['api_id']),
    config['api_hash'],
    # Optimize connection settings
    connection_retries=5,
    retry_delay=1,
    timeout=30,
    # Use aiohttp for better performance
    proxy=None
)

# Configure client for FastTelethon
client.upload_threads = 8
client.download_threads = 8

# Register command handlers
client.add_event_handler(start_command, events.NewMessage(pattern='/start'))
client.add_event_handler(help_command, events.NewMessage(pattern='/help'))

# Register message and callback handlers
client.add_event_handler(lambda e: handle_messages(
    e, client), events.NewMessage())
client.add_event_handler(lambda e: handle_callback(
    e, client), events.CallbackQuery())


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
