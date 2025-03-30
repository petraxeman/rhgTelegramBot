import logging
import globals as g
from pyrogram import Client
from pyrogram.types import Message

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("rhgTelegramGroup")



async def add_user_command(client: Client, message: Message):
    if len(message.command) < 2:
        await message.reply_text("Недостаточно аргументов")
        return
    
    
    username = message.command[1]
    
    logger.info(f"Вы решили добавить пользователя {username}")
    
    userinfo = await client.get_users(username)
    if not userinfo:
        await message.reply_text(f"Пользователь {username} не найден")
        return
    
    if message.from_user.username == g.cfg.get("MAIN", {}).get("admin_username", "xqxqxq"):
        await g.adb.execute(f"INSERT INTO users (userid, username) VALUES ('{userinfo.id}', '{username}');")
        await message.reply_text(f"Пользователь {username} успешно добавлен")
    
        logger.info(f"Пользователь {username} ({userinfo.id}) успешно добавлен")