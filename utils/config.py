from configparser import ConfigParser
import logging
import os

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)


def load_config():
    """Load configuration from environment variables or config.ini file."""
    # Try to load from environment variables first
    config = {
        'api_id': os.getenv('API_ID'),
        'api_hash': os.getenv('API_HASH'),
        'bot_token': os.getenv('BOT_TOKEN'),
        'session_name': os.getenv('SESSION_NAME', 'dotun_bot')
    }

    # If any required values are missing, try to load from config file
    if not all([config['api_id'], config['api_hash'], config['bot_token']]):
        logger.info("Loading configuration from config.ini file...")
        config_parser = ConfigParser()
        config_parser.read('config.ini')

        config.update({
            'api_id': config_parser.get('Telegram', 'api_id', fallback=config['api_id']),
            'api_hash': config_parser.get('Telegram', 'api_hash', fallback=config['api_hash']),
            'bot_token': config_parser.get('Telegram', 'bot_token', fallback=config['bot_token']),
            'session_name': config_parser.get('Telegram', 'session_name', fallback=config['session_name'])
        })

    # Validate configuration
    if not all([config['api_id'], config['api_hash'], config['bot_token']]):
        raise ValueError(
            "Missing required configuration values. Please set environment variables or check config.ini file.")

    return config
