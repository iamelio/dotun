from telethon import TelegramClient
from telethon.tl.types import DocumentAttributeFilename
from datetime import datetime, timedelta
import humanize
import os
import logging
import asyncio
from utils.FastTelethon import download_file, upload_file
from telethon.tl.custom import Button

logger = logging.getLogger(__name__)

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


def ensure_extension(new_name, original_path):
    """Ensure the new filename has the correct extension."""
    # If original_path is a filename, use it directly
    if os.path.isfile(original_path):
        _, original_ext = os.path.splitext(original_path)
    else:
        # If it's not a file (might be the original filename string)
        _, original_ext = os.path.splitext(original_path)

    # If no extension in new name, add the original extension
    if '.' not in new_name:
        new_name += original_ext
    return new_name


class FileTransfer:
    """Class to handle file transfers with progress tracking."""

    def __init__(self, status_msg, total_size):
        self.status_msg = status_msg
        self.total_size = total_size
        self.start_time = datetime.now()
        self.last_update = self.start_time
        self.cancelled = False
        self.operation_id = None

        # Register in active operations
        self.operation_id = f"{status_msg.chat_id}_{datetime.now().timestamp()}"
        active_operations[self.operation_id] = self

        # Create cancel button
        self.keyboard = [
            [Button.inline("❌ Cancel", f"cancel_{self.operation_id}")]]

    async def update_progress(self, current, total, prefix="📥"):
        """Update progress message."""
        current_time = datetime.now()

        # Update progress every 2 seconds
        if (current_time - self.last_update).total_seconds() >= 2:
            if self.cancelled:
                return

            speed = current / (current_time - self.start_time).total_seconds()
            eta = (total - current) / speed if speed > 0 else 0
            progress = (current / total) * 100

            status_text = (
                f"{prefix} {'downloading' if prefix == '📥' else 'uploading'}...\n\n"
                f"progress: {progress:.1f}%\n"
                f"{'downloaded' if prefix == '📥' else 'uploaded'}: {humanize.naturalsize(current)} / {humanize.naturalsize(total)}\n"
                f"speed: {humanize.naturalsize(speed)}/s\n"
                f"ETA: {humanize.naturaltime(datetime.now() + timedelta(seconds=eta), future=True)}"
            )

            asyncio.create_task(self.status_msg.edit(
                status_text, buttons=self.keyboard))
            self.last_update = current_time

    def cancel(self):
        """Cancel the transfer."""
        self.cancelled = True

    def cleanup(self):
        """Clean up operation state."""
        if self.operation_id in active_operations:
            del active_operations[self.operation_id]


async def download_and_rename(client, file_message, new_name, status_msg, as_file=False):
    """Download, rename, and send back the file with optimized performance."""
    # Create file transfer handler
    transfer = FileTransfer(status_msg, file_message.media.document.size)

    # Get original file info to preserve extension
    file_info = get_file_info(file_message)
    original_filename = file_info.get('name', 'Unknown')

    # Initialize status message
    await status_msg.edit("📥 starting download...", buttons=transfer.keyboard)

    # Create temporary file paths
    download_path = os.path.join('downloads', f'temp_{transfer.operation_id}')
    new_path = None

    try:
        # Download file using FastTelethon
        with open(download_path, 'wb') as file:
            await download_file(
                client,
                file_message.media.document,
                file,
                lambda current, total: transfer.update_progress(
                    current, total, "📥")
            )

        if transfer.cancelled:
            await status_msg.edit("❌ download cancelled.")
            return

        # Ensure correct extension
        _, original_ext = os.path.splitext(original_filename)
        if '.' not in new_name:
            new_name += original_ext

        new_path = os.path.join('downloads', new_name)

        # Rename the file
        os.rename(download_path, new_path)

        # Update status message for upload
        await status_msg.edit(f'📤 preparing to upload "{new_name}"...', buttons=transfer.keyboard)

        # Upload and send the renamed file
        with open(new_path, 'rb') as file:
            # Upload file using FastTelethon
            input_file = await upload_file(
                client,
                file,
                lambda current, total: transfer.update_progress(
                    current, total, "📤")
            )

            # Log the filename being used
            logger.info(f"Sending file with name: {new_name}")

            # Create filename attribute
            filename_attr = DocumentAttributeFilename(new_name)

            # Send the file using the InputFile returned from FastTelethon
            await client.send_file(
                status_msg.chat_id,
                input_file,
                caption=f'**{new_name}**',
                parse_mode='md',
                force_document=as_file,
                attributes=[filename_attr]
            )

        if not transfer.cancelled:
            await status_msg.edit('done. :)', buttons=None)
    except Exception as e:
        logger.error(f"Error in download_and_rename: {e}")
        if not transfer.cancelled:
            await status_msg.edit(f"❌ error: {str(e)}")
        raise
    finally:
        # Clean up files
        try:
            if new_path and os.path.exists(new_path):
                os.remove(new_path)
            if os.path.exists(download_path) and (not new_path or download_path != new_path):
                os.remove(download_path)
        except Exception as e:
            logger.error(f"Error cleaning up files: {e}")

        # Clean up operation state
        transfer.cleanup()


def cancel_operation(operation_id):
    """Cancel an ongoing operation by its ID."""
    if operation_id in active_operations:
        active_operations[operation_id].cancel()
        return True
    return False


def get_operation_id_from_callback(callback_data):
    """Extract operation ID from callback data."""
    if callback_data.startswith(b'cancel_'):
        return callback_data[7:].decode()
    return None
