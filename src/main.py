import os
import db
import toml
import asyncio
import logging
import pyrogram
import globals as g

from pyrogram import Client, filters
from pyrogram.types import Message, BotCommand
from pyrogram.handlers import MessageHandler

# ROUTES
from info_handlers import start_command, help_command
from ai_handlers import set_gemini_token_command, gemini_ask
from administation_handlers import add_user_command

USER_SESSION_NAME_TEMPLATE = "user_{}"

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("rhgTelegramGroup")



async def pre_message(client: Client, message: Message):
    if str(message.from_user.id) not in g.cache:
        data = await g.adb.fetchone(f"SELECT userid, gemini_token FROM users WHERE userid == '{message.from_user.id}'")
        if not data:
            logger.info(f"Пользователь {message.from_user.username} ({message.from_user.id}) пытался получить доступ, но он не зарегистрирован.")
            message.stop_propagation()
            return
        else:
            g.cache[data[0]] = {"gemini_token": data[1], "context": []}



async def main():
    await bot.start()
    logger.info("Бот запущен.")
    
    await bot.set_bot_commands([
        BotCommand("start", "Стартовое сообщение"),
        BotCommand("help", "Инфомационное сообщение"),
        BotCommand("set_token", "Установить свой gemini токен"),
        BotCommand("add_user", "Только для администратора"),
        
    ])
    logger.info("Команды для автозаполнения отправлены.")
    
    bot.add_handler(MessageHandler(add_user_command, filters.command("add_user") & filters.private), group=0)
    
    bot.add_handler(MessageHandler(pre_message), 1)
    
    bot.add_handler(MessageHandler(start_command, filters.command("start") & filters.private), 2)
    bot.add_handler(MessageHandler(help_command, filters.command("help") & filters.private), 2)
    
    bot.add_handler(MessageHandler(set_gemini_token_command, filters.command("set_token") & filters.private), 2)
    bot.add_handler(MessageHandler(gemini_ask, filters.mentioned), 3)
    
    logger.info("Обработчики созданы.")
    
    try:
        logger.info("Запускаем бесконечный цикл.")
        await pyrogram.idle()
    except KeyboardInterrupt:
        logger.info("Получен сигнал KeyboardInterrupt. Завершение...")
        await bot.stop()
        quit()


    
if __name__ == "__main__":
    os.system("cls")
    
    bot_token = g.cfg.get("MAIN", {}).get("bot_token")
    app_id = g.cfg.get("MAIN", {}).get("app_id")
    app_hash = g.cfg.get("MAIN", {}).get("app_hash")
    
    if not bot_token or not app_id or not app_hash:
        raise ValueError("Expected bot_token, app_id, and app_hash in config.toml")
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    bot = Client("rhgTelegramGroupBot", bot_token=bot_token, api_id=app_id, api_hash=app_hash, workdir=os.path.join(".", "sessions"))
    
    if not bot:
        quit()
    
    bot.run(main())