from telethon import events


async def start_command(event):
    """handle the /start command and display welcome message"""
    await event.respond('hello. you can call me dotun! ✨\n\n'
                        'forward me any file, and i\'ll help you rename it.\n'
                        'to use, simply:\n'
                        '1. forward a file to me\n'
                        '2. tell me the new name you want\n'
                        '3. i\'ll send you back the renamed file')
    raise events.StopPropagation


async def help_command(event):
    """display help message with usage instructions"""
    await event.respond('📚 **dotun\'s help**\n\n'
                        'i can help you rename any file on telegram. here\'s how to use me:\n\n'
                        '**commands:**\n'
                        '/start - start me\n'
                        '/help - show this help message\n\n'
                        '**to rename a file:**\n'
                        '1. forward or send a file to me\n'
                        '2. tell me the new filename\n'
                        '3. i\'ll process and send back the renamed file\n\n'
                        '✅ works with files of any size!\n'
                        '✅ preserves file extension if you don\'t specify one')
    raise events.StopPropagation
