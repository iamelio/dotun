import os
from datetime import datetime, timedelta
import humanize
import asyncio
from telethon.tl.types import DocumentAttributeFilename


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


class FileTransfer:
    def __init__(self, status_msg, total_size):
        self.status_msg = status_msg
        self.total_size = total_size
        self.start_time = datetime.now()
        self.last_update = self.start_time
        self.cancelled = False
        self._progress_task = None

    async def update_progress(self, current, total, prefix="📥"):
        """Update progress message."""
        current_time = datetime.now()

        # Update progress every 2 seconds
        if (current_time - self.last_update).total_seconds() >= 2:
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

            if not self.cancelled:
                await self.status_msg.edit(status_text)
            self.last_update = current_time

    def cancel(self):
        """Cancel the transfer."""
        self.cancelled = True
        if self._progress_task:
            self._progress_task.cancel()

    async def start_progress_tracking(self, callback, prefix="📥"):
        """Start tracking progress with a cancel button."""
        keyboard = [[Button.inline("❌ Cancel", "cancel")]]
        await self.status_msg.edit(
            f"{prefix} preparing...",
            buttons=keyboard
        )

        self._progress_task = asyncio.create_task(
            self.update_progress(0, self.total_size, prefix)
        )
        return callback


def ensure_extension(new_name, original_path):
    """Ensure the new filename has the correct extension."""
    _, original_ext = os.path.splitext(original_path)
    if '.' not in new_name:
        new_name += original_ext
    return new_name
