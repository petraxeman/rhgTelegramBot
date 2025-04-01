import logging
import globals as g

from pyrogram import Client
from pyrogram.types import Message

from google import genai
from google.genai import types

from utils import model_decode, str_to_bool, parse_ask_msg

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("rhgTelegramGroup")



async def set_gemini_token_command(client: Client, message: Message):
    logger.info(f"Пользователь {message.from_user.username} ({message.from_user.id}) запросил установку токена")
    args = message.command[1:]
    
    if len(args) < 1:
        await message.reply_text("Вы забыли про токен?")
        return
    if len(args[0]) < 30:
        await message.reply_text("Слишком коротко для токена?")
        return
    
    with g.db.transaction() as conn:
        conn.root.users[message.from_user.id]["gemini_token"] = args[0]

    stars = ' ' + '* ' * (len(args[0][4:-4]) // 3)
    logger.info(f"Токен для пользователя {message.from_user.username} ({message.from_user.id}) установлен на {args[0][:4]}{'*' * (len(args[0][4:-4]) // 3)}{args[0][-4:]}")
    text = f"Услышал тебя родной. Запомнил следующий токен: \n{args[0][:4]}{stars}{args[0][-4:]}"
    await message.reply_text(text)


async def gemini_ask(client: Client, message: Message):
    user_id = message.from_user.id
    with g.db.transaction() as conn:
        token = conn.root.users[user_id]["gemini_token"]

    if not token:
        logger.info(f"Пользователь {message.from_user.username} ({message.from_user.id}) пытался спросить gemini без токена.")
        return
    
    tg_bot_name = g.cfg.get("CREDIT", {}).get("tg_bot_name", ""); hr_bot_name = g.cfg.get("CREDIT", {}).get("hr_bot_name", "")
    flags, direction, clear_msg = parse_ask_msg(message.text, tg_bot_name, hr_bot_name)

    tools = []
    with g.db.transaction() as conn:
        chat = conn.root.users[user_id]["chat"]
        user_params = conn.root.users[user_id]["gemini_config"]
    
    f_flag = "f" in flags; forgot_param = user_params.get("forgot", False)
    if (f_flag or forgot_param) and not (f_flag and forgot_param):
        with g.db.transaction() as conn:
            conn.root.users[user_id]["chat"] = []
    
    s_flag = "s" in flags; search_param = user_params.get("search", False)
    if (s_flag or search_param) and not (s_flag and search_param):
        tools.append(types.Tool(google_search=types.GoogleSearch))
    
    model = user_params.get("model", "gemini-2.0-flash")
    if "0" in flags:
        model = "gemini-1.5-flash"
    elif "1" in flags:
        model = "gemini-2.0-flash"
    elif "2" in flags:
        model = "gemini-2.5-pro-exp-03-25"
    
    if direction:
        chat.append({"role": "user", "parts": [{"text": "История пересланых сообщений:\n" + await read_by_direction(client, message, direction)}]})
    
    chat.append({"role": "user", "parts": [{"text": clear_msg}]})
    print(user_params.get("system_instruction"))
    logger.info(f"Пользователь {message.from_user.username} ({message.from_user.id}) совершил следующий запрос: \"{clear_msg[:30]}\".")
    client = genai.Client(api_key=token)
    response = client.models.generate_content(
        model=model,
        config=types.GenerateContentConfig(system_instruction = [user_params.get("system_instruction")], tools = tools),
        contents=chat,
    )
    
    chat.append({"role": "model", "parts": [{"text": response.text}]})
    
    await message.reply_text(response.text)
    
    if not ( "n" in flags ):
        if len(chat) > user_params.get("max_chat_size", 16):
            chat.pop(0); chat.pop(0)
        
        with g.db.transaction() as conn:
            conn.root.users[user_id]["chat"] = chat
    
    d_flag = "d" in flags; delete_param = user_params.get("delete", False)
    if (d_flag or delete_param) and not (d_flag and delete_param):
        await message.delete()


async def read_by_direction(client: Client, message: Message, direction: dict):
    if not message.reply_to_message:
        return
    
    chat_id = message.reply_to_message.chat.id
    curr_msg_id = message.reply_to_message.id
    reply_usr_id = message.reply_to_message.from_user.id
    
    total_chat_history = ""
    strict = direction["strict"]
    vector = direction["vector"] * -1
    count = direction["count"] if direction["count"] < 50 else 50
    
    catched_count = 0; fallback = 0
    while catched_count < count:
        ids = [curr_msg_id + (i * vector) for i in range(20)]
        msgs = await client.get_messages(chat_id=chat_id, message_ids=ids)
        if strict:
            msgs = [msg for msg in msgs if hasattr(msg.from_user, "id") and msg.from_user.id == reply_usr_id]
        msgs = list(sorted(msgs, key=lambda x: x.id))
        
        if not msgs:
            fallback += 1
        
        if fallback >= 3:
            return total_chat_history
        
        for msg in msgs:
            if not msg.text:
                continue
                
            total_chat_history += f"**{msg.from_user.username} написал:** {msg.text}\n\n"
            catched_count += 1
        
        curr_msg_id = ids[-1] + vector
        
    return total_chat_history


async def set_gmn_arg_command(client: Client, message: Message):
    user_id = message.from_user.id
    
    if len(message.command) < 3:
        await message.reply_text("Недостаточно аргументов")
        return
    
    param, value = message.command[1:3]
    
    match param:
        case "forgot" | "search" | "delete":
            value = str_to_bool(value)
            with g.db.transaction() as conn:
                conn.root.users[user_id]["gemini_config"][param] = value
        case "model":
            value = model_decode(value)
            with g.db.transaction() as conn:
                conn.root.users[user_id]["gemini_config"]["model"] = value
        case "system_instruction":
            with g.db.transaction() as conn:
                conn.root.users[user_id]["gemini_config"]["system_instruction"] = value #match.group("system")
        case "max_chat_size":
            try:
                value = int(value)
            except:
                value = 30
            with g.db.transaction() as conn:
                conn.root.users[user_id]["gemini_config"]["max_chat_size"] = value
    
    await message.reply_text(f"Параметр: {repr(param)}\nУспешно установлен на:\n{value}")