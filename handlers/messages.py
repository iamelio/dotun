from telethon import events
from telethon.tl.custom import Button
import logging
import asyncio
import humanize
import telegram_file_transfer as tft
from telethon.tl.types import InputFileLocation
from telethon.tl.functions.upload import GetFileRequest

logger = logging.getLogger(__name__)

# Dictionary to store pending rename operations
pending_renames = {}


async def handle_messages(event, client):
    """Handle incoming messages."""
    user_id = event.sender_id

    # Handle file uploads
    if event.message.media and not event.message.text.startswith('/'):
        # Get file information
        file_info = tft.get_file_info(event.message)
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
    callback_data = event.data

    # Handle cancel button for specific operations
    operation_id = tft.get_operation_id_from_callback(callback_data)
    if operation_id:
        if tft.cancel_operation(operation_id):
            await event.answer('❌ Operation cancelled.')
        return

    # Handle simple cancel button (legacy)
    if callback_data == b'cancel':
        # Look for any operations in the active_operations dict
        for op_id in list(tft.active_operations.keys()):
            if op_id.startswith(str(user_id)):
                tft.cancel_operation(op_id)
                await event.answer('❌ Operation cancelled.')
                break
        return

    # Handle file type selection
    if user_id in pending_renames and pending_renames[user_id]['state'] == 'waiting_for_type':
        # Delete the file type selection message
        try:
            await client.delete_messages(event.chat_id, [pending_renames[user_id]['file_type_msg_id']])
        except Exception as e:
            logger.error(f"Error deleting file type message: {e}")

        as_file = callback_data == b'doc'
        status_msg = await event.respond('starting file processing... please wait.')

        try:
            # Get the original file message
            file_message = await event.client.get_messages(event.chat_id, ids=pending_renames[user_id]['message_id'])

            # Use the centralized download_and_rename function
            await tft.download_and_rename(
                client,
                file_message,
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
