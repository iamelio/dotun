from telethon import events
from telethon.tl.custom import Button
from utils.file_handler import get_file_info, FileTransfer, ensure_extension
import os
import logging
import humanize

logger = logging.getLogger(__name__)

# Dictionary to store pending rename operations
pending_renames = {}

# Dictionary to store active file transfer operations
active_operations = {}


async def handle_messages(event, client):
    """Handle incoming messages."""
    user_id = event.sender_id

    # Handle file uploads
    if event.message.media and not event.message.text.startswith('/'):
        # Get file information
        file_info = get_file_info(event.message)
        if not file_info:
            await event.respond('sorry, i could not process this file.')
            return

        # Store the message ID and file info for later reference
        pending_renames[user_id] = {
            'message_id': event.message.id,
            'file_info': file_info,
            'state': 'waiting_for_name'
        }

        # Reply with file information
        info_text = (
            f"📄 **file information**\n\n"
            f"name: `{file_info['name']}`\n"
            f"size: {humanize.naturalsize(file_info['size'])}\n"
            f"type: `{file_info['mime_type']}`\n\n"
            "please type the new name for the file."
        )
        info_msg = await event.respond(info_text, parse_mode='md')

        # Store the info message ID to delete it later
        pending_renames[user_id]['info_msg_id'] = info_msg.id

    # Handle new name input
    elif user_id in pending_renames and pending_renames[user_id]['state'] == 'waiting_for_name' and not event.message.media and not event.message.text.startswith('/'):
        new_name = event.message.text.strip()

        # Delete the info message and user's message
        try:
            await client.delete_messages(event.chat_id, [
                pending_renames[user_id]['info_msg_id'],
                event.message.id
            ])
        except Exception as e:
            logger.error(f"Error deleting messages: {e}")

        # Create inline keyboard for file type selection
        keyboard = [
            [
                Button.inline("📄 Document", "doc"),
                Button.inline("🖼️ Original Format", "orig")
            ]
        ]

        # Show the renamed file name before asking for the output file type
        file_type_msg = await event.respond(
            f"the new name for your file is \"`{new_name}`\". \n\nshould i give it back to you as a document or in the default format?",
            buttons=keyboard
        )

        # Store the new name and file type message ID
        pending_renames[user_id]['new_name'] = new_name
        pending_renames[user_id]['file_type_msg_id'] = file_type_msg.id
        pending_renames[user_id]['state'] = 'waiting_for_type'


async def handle_callback(event, client):
    """Handle callback queries (button clicks)."""
    user_id = event.sender_id

    # Handle cancel button
    if event.data.decode() == b'cancel':
        # Find the active operation for this user
        for operation_id, operation in active_operations.items():
            if operation_id.startswith(str(user_id)):
                operation['cancelled'] = True
                await event.message.edit('❌ Operation cancelled.')
                break
        return

    # Handle file type selection
    if user_id in pending_renames and pending_renames[user_id]['state'] == 'waiting_for_type':
        # Delete the file type selection message
        try:
            await event.message.delete()
        except Exception as e:
            logger.error(f"Error deleting file type message: {e}")

        as_file = event.data.decode() == b'doc'
        status_msg = await event.respond('starting file processing... please wait.')

        try:
            await rename_and_send_file(
                event,
                client,
                await event.client.get_messages(event.chat_id, ids=pending_renames[user_id]['message_id']),
                pending_renames[user_id]['new_name'],
                status_msg,
                as_file
            )
            # Clear the pending rename after successful processing
            del pending_renames[user_id]
        except Exception as e:
            logger.error(f"Error renaming file: {e}")
            await status_msg.edit(
                f"sorry, an error occurred while renaming your file: {str(e)}")


async def rename_and_send_file(event, client, file_message, new_name, status_msg, as_file):
    """Download, rename, and send back the file."""
    # Create file transfer handler
    transfer = FileTransfer(status_msg, file_message.media.document.size)
    pending_renames[event.sender_id]['transfer'] = transfer

    # Get the file with progress tracking
    download_path = await file_message.download_media(
        'downloads/',
        progress_callback=transfer.update_progress
    )

    if not download_path:
        await status_msg.edit('failed to download the file. please try again.')
        return

    if transfer.cancelled:
        return

    # Ensure correct extension
    new_name = ensure_extension(new_name, download_path)
    new_path = os.path.join('downloads', new_name)

    try:
        # Rename the file
        os.rename(download_path, new_path)

        # Send the renamed file with upload progress
        await client.send_file(
            event.chat_id,
            new_path,
            caption=f'**{new_name}**',
            parse_mode='md',
            as_file=as_file,
            progress_callback=transfer.update_progress
        )

        if not transfer.cancelled:
            await status_msg.edit('done. :)')
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
