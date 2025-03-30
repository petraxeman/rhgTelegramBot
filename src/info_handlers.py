import logging
from pyrogram import Client
from pyrogram.types import Message

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("rhgTelegramGroup")



async def start_command(client: Client, message: Message):
    logger.info(f"Пользователь {message.from_user.username} ({message.from_user.id}) вызвал /start")
    await message.reply_text(
        "Привет! Я Rough Telegram Group bot.\n"
        "Что бы узнать о моих возможностях можешь вызвать /help"
    )


async def help_command(client: Client, message: Message):
    logger.info(f"Пользователь {message.from_user.username} ({message.from_user.id}) вызвал /help")
    await message.reply_text(
        "Привет! Вот функционал который у меня сейчас есть:\n"
        "Командой /start ты можешь вызвать приветственное сообщение.\n"
        "А коммандой /help это.\n"
        "Коммандой же /set_token $token ты можещь добавить свой gemini токен, и тогда я буду разговаривать\n\n"
        "**Внимание:** Весь процесс требует полного доверия ко мне, так как ты будешь вводить свои данные для входа."
    )