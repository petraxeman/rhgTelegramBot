import os
import db
import toml
import asyncio
import logging
import pyrogram
import globals as g

from typing import Dict

from pyrogram import Client, filters, compose
from pyrogram.types import Message, BotCommand
from pyrogram.raw.types.wall_paper_settings import WallPaperSettings
from pyrogram.raw.functions.account.upload_wall_paper import UploadWallPaper
from pyrogram.errors import (
    ApiIdInvalid, AuthKeyUnregistered, FloodWait, PhoneCodeExpired,
    PhoneCodeInvalid, PhoneNumberInvalid, SessionPasswordNeeded, UserDeactivatedBan
)
from pyrogram.enums import ParseMode
from pyrogram.handlers import MessageHandler

# ROUTES
from info_handlers import start_command, help_command
from ai_handlers import set_gemini_token_command, gemini_ask

USER_SESSION_NAME_TEMPLATE = "user_{}"

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("rhgTelegramGroup")

main_states: Dict[int, int] = {}
auth_states: Dict[int, Dict] = {}
wallpaper_states: Dict[int, Dict] = {}

cached_gemini_tokens = {}


class MainState:
    IDLE = 0
    AUTH = 1
    WALLPAPER = 2
    AI = 3


class AuthState:
    IDLE = 0
    WAITING_PHONE = 1
    WAITING_CODE = 2
    WAITING_PASSWORD = 3
    LOGGED_IN = 4
    ERROR = 5


if __name__ == "__main__":

    
    bot_token = g.cfg.get("MAIN", {}).get("bot_token")
    app_id = g.cfg.get("MAIN", {}).get("app_id")
    app_hash = g.cfg.get("MAIN", {}).get("app_hash")
    
    if not bot_token or not app_id or not app_hash:
        raise ValueError("Expected bot_token, app_id, and app_hash in config.toml")
    
    adb = db.DB()
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    bot = Client("rhgTelegramGroupBot", bot_token=bot_token, api_id=app_id, api_hash=app_hash)



# --- Функции для аутентификации пользовательского клиента ---

async def start_user_auth(user_id: int, phone_number: str):
    """Начинает процесс аутентификации для пользовательского клиента."""
    state = auth_states.get(user_id)
    if not state:
        logger.error(f"Состояние для user_id {user_id} не найдено.")
        return

    session_name = USER_SESSION_NAME_TEMPLATE.format(user_id)
    user_client = Client(session_name, app_id, app_hash, in_memory=False, workdir=os.path.join(".", "sessions"))

    try:
        logger.info(f"[{user_id}] Подключение клиента {session_name}...")
        await user_client.connect()
        logger.info(f"[{user_id}] Отправка кода на номер {phone_number}...")
        sent_code_info = await user_client.send_code(phone_number)

        state['phone_code_hash'] = sent_code_info.phone_code_hash
        state['state'] = AuthState.WAITING_CODE
        state['user_client'] = user_client # Сохраняем клиент в состоянии
        state['phone_number'] = phone_number # Сохраняем номер

        logger.info(f"[{user_id}] Код отправлен. Ожидание кода от пользователя.")
        await bot.send_message(
            user_id,
            f"Код отправлен на номер `{phone_number}` через Telegram (или SMS/звонок).\n"
            f"Тип: `{sent_code_info.type.name}`\n"
            f"Пожалуйста, пришлите полученный код.",
            parse_mode=ParseMode.MARKDOWN
        )

    except FloodWait as e:
        logger.warning(f"[{user_id}] FloodWait: {e.value} секунд.")
        state['state'] = AuthState.ERROR
        state['last_error'] = f"Слишком много попыток. Пожалуйста, подождите {e.value} секунд и попробуйте снова командой /login."
        await bot.send_message(user_id, state['last_error'])
        if 'user_client' in state and state['user_client'].is_connected:
            await state['user_client'].disconnect()
        del state['user_client'] # Удаляем клиент из состояния
    except PhoneNumberInvalid:
        logger.warning(f"[{user_id}] Неверный формат номера телефона.")
        state['state'] = AuthState.ERROR
        state['last_error'] = "Вы ввели неверный формат номера телефона. Пожалуйста, попробуйте /login снова, используя международный формат (например, +1234567890)."
        await bot.send_message(user_id, state['last_error'])
        if 'user_client' in state and state['user_client'].is_connected:
            await state['user_client'].disconnect()
        del state['user_client']
    except Exception as e:
        logger.exception(f"[{user_id}] Ошибка при отправке кода: {e}")
        state['state'] = AuthState.ERROR
        state['last_error'] = f"Произошла ошибка при отправке кода: {e}. Попробуйте /login снова."
        await bot.send_message(user_id, state['last_error'])
        if 'user_client' in state and state['user_client'].is_connected:
            await state['user_client'].disconnect()
        del state['user_client']


async def process_user_code(user_id: int, code: str):
    """Обрабатывает введенный пользователем код."""
    state = auth_states.get(user_id)
    if not state or 'user_client' not in state or 'phone_number' not in state or 'phone_code_hash' not in state:
        logger.error(f"[{user_id}] Неверное состояние для обработки кода.")
        await bot.send_message(user_id, "Произошла внутренняя ошибка состояния. Пожалуйста, начните сначала: /login")
        return

    user_client: Client = state['user_client']
    phone_number = state['phone_number']
    phone_code_hash = state['phone_code_hash']

    try:
        logger.info(f"[{user_id}] Попытка входа с кодом...")
        await user_client.sign_in(phone_number, phone_code_hash, code)
        # Успешный вход без 2FA
        logger.info(f"[{user_id}] Успешный вход!")
        state['state'] = AuthState.LOGGED_IN
        await bot.send_message(user_id, "✅ Вы успешно вошли! Ваша сессия сохранена.")
        await user_client.disconnect() # Отключаем сразу после логина
        del state['user_client'] # Больше не нужен в состоянии
    except PhoneCodeInvalid:
        logger.warning(f"[{user_id}] Неверный код.")
        state['state'] = AuthState.WAITING_CODE # Остаемся в ожидании кода
        await bot.send_message(user_id, "❌ Неверный код подтверждения. Пожалуйста, попробуйте еще раз.")
        return
    except PhoneCodeExpired:
        logger.warning(f"[{user_id}] Код истек.")
        state['state'] = AuthState.ERROR
        state['last_error'] = "❌ Код подтверждения истек. Пожалуйста, начните сначала: /login"
        await bot.send_message(user_id, state['last_error'])
        await user_client.disconnect()
        del state['user_client']
    except SessionPasswordNeeded:
        logger.info(f"[{user_id}] Требуется пароль 2FA.")
        state['state'] = AuthState.WAITING_PASSWORD
        await bot.send_message(user_id, "🔑 Ваш аккаунт защищен двухфакторной аутентификацией (2FA). Пожалуйста, введите ваш пароль.")
    except FloodWait as e:
        logger.warning(f"[{user_id}] FloodWait при входе: {e.value} секунд.")
        state['state'] = AuthState.ERROR
        state['last_error'] = f"Слишком много попыток входа. Пожалуйста, подождите {e.value} секунд и попробуйте снова командой /login."
        await bot.send_message(user_id, state['last_error'])
        await user_client.disconnect()
        del state['user_client']
    except Exception as e:
        logger.exception(f"[{user_id}] Ошибка при входе: {e}")
        state['state'] = AuthState.ERROR
        state['last_error'] = f"Произошла ошибка при входе: {e}. Попробуйте /login снова."
        await bot.send_message(user_id, state['last_error'])
        if user_client.is_connected:
            await user_client.disconnect()
        del state['user_client']
    main_states[user_id] = MainState.IDLE


async def process_user_password(user_id: int, password: str):
    """Обрабатывает введенный пользователем пароль 2FA."""
    state = auth_states.get(user_id)
    if not state or 'user_client' not in state:
        logger.error(f"[{user_id}] Неверное состояние для обработки пароля.")
        await bot.send_message(user_id, "Произошла внутренняя ошибка состояния. Пожалуйста, начните сначала: /login")
        return

    user_client: Client = state['user_client']

    try:
        logger.info(f"[{user_id}] Проверка пароля 2FA...")
        await user_client.check_password(password)
        logger.info(f"[{user_id}] Успешный вход (с 2FA)!")
        state['state'] = AuthState.LOGGED_IN
        await bot.send_message(user_id, "✅ Вы успешно вошли! Ваша сессия сохранена.")
        # Сессия сохранена
        await user_client.disconnect()
        del state['user_client']
        main_states[user_id] = MainState.IDLE

    except FloodWait as e:
        logger.warning(f"[{user_id}] FloodWait при проверке пароля: {e.value} секунд.")
        state['state'] = AuthState.ERROR
        state['last_error'] = f"Слишком много попыток ввода пароля. Пожалуйста, подождите {e.value} секунд и попробуйте снова командой /login."
        await bot.send_message(user_id, state['last_error'])
        await user_client.disconnect()
        del state['user_client']
    except Exception as e: # Включая неверный пароль (PasswordHashInvalid)
        logger.warning(f"[{user_id}] Ошибка при проверке пароля: {e}")
        # Не говорим прямо "неверный пароль" для безопасности
        state['state'] = AuthState.WAITING_PASSWORD # Даем еще попытку? Или сбросить? Лучше сбросить.
        state['state'] = AuthState.ERROR
        state['last_error'] = f"Произошла ошибка при проверке пароля (возможно, он неверный). Попробуйте /login снова."
        # state['state'] = STATE_WAITING_PASSWORD # Даем еще попытку
        # await bot.send_message(user_id, "❌ Неверный пароль. Попробуйте еще раз:")
        await bot.send_message(user_id, state['last_error'])
        await user_client.disconnect()
        del state['user_client']




@bot.on_message(filters.command("set_wallpaper") & filters.private)
async def set_wallpaper_command(client: Client, message: Message):
    if main_states.get(message.from_user.id, MainState.IDLE) != MainState.IDLE:
        await message.reply_text("Эй, ты уже что-то делаешь. Покончи сначала с этим!")
        return
    
    main_states[message.from_user.id] = MainState.WALLPAPER
    
    args = message.command[1:]
    if int(args[0]) % 30 != 0:
        await message.reply_text(f"Вы указали градус равный {args[0]}, но градус должен быть кратен 30.\nНапример 0, 30, 60, 90, 120, 150, 180")
        main_states[message.from_user.id] = MainState.IDLE
        return

    available_weather_types = ["clear", "drizzle", "rain", "shower", "mist", "broken_clouds", "over_clouds"]
    if args[1] not in available_weather_types:
        await message.reply_text(f"Вы указали неправильный тип погоды ожидаемой погоды.\nВот доступные типы: {', '.join(available_weather_types)}")
        main_states[message.from_user.id] = MainState.IDLE
        return
    
    if int(args[2]) not in [-1, 0, 1]:
        await message.reply_text(f"Вы указали темепуратуру равную {args[2]}, но разрешены только -1, 0 и 1")
        main_states[message.from_user.id] = MainState.IDLE
        return
    
    try:
        args[3]
    except:
        await message.reply_text(f"Не найден group_id. Пожайлуйста укажите для какой конкретно!")
        main_states[message.from_user.id] = MainState.IDLE
        return
    
    wallpaper_states[message.from_user.id] = {"groupid": args[3], "weather": args[1], "temp": args[2], "degree": args[0]}
    await message.reply_text("Отлично, теперь отправте картинку.")
    

@bot.on_message(filters.command("cancel_all") & filters.private)
async def cancel_all_command(client: Client, message: Message):
    main_states[message.from_user.id] = MainState.IDLE
    await message.reply_text("Вы отменили все операции.")



@bot.on_message(filters.command("login") & filters.private)
async def login_command(client: Client, message: Message):
    if main_states.get(message.from_user.id, MainState.IDLE) != MainState.IDLE:
        await message.reply_text("Эй, ты уже что-то делаешь. Покончи сначала с этим!")
        return
    
    main_states[message.from_user.id] = MainState.AUTH
    user_id = message.from_user.id
    if user_id in auth_states and auth_states[user_id]['state'] not in [AuthState.IDLE, AuthState.ERROR, AuthState.LOGGED_IN]:
        await message.reply_text("Вы уже находитесь в процессе входа. Чтобы начать заново, дождитесь завершения или ошибки.")
        return

    # Сбрасываем предыдущее состояние, если оно было (ошибка или успешный вход)
    if user_id in auth_states and 'user_client' in auth_states[user_id]:
         if auth_states[user_id]['user_client'].is_connected:
             await auth_states[user_id]['user_client'].disconnect()

    auth_states[user_id] = {
        'state': AuthState.WAITING_PHONE,
        'user_client': None,
        'phone_number': None,
        'phone_code_hash': None,
        'last_error': None,
    }
    logger.info(f"Пользователь {user_id} начал процесс входа.")
    await message.reply_text("Пожалуйста, введите ваш номер телефона в международном формате (например, +1234567890).")


@bot.on_message(filters.photo & filters.private)
async def photo_upload(client: Client, message: Message):
    if main_states.get(message.from_user.id, MainState.IDLE) == MainState.WALLPAPER:
        app = Client(USER_SESSION_NAME_TEMPLATE.format(message.from_user.id), api_id=app_id, api_hash=app_hash, workdir=os.path.join(".", "sessions"))
        await app.start()
        try:
            print("login")
            await app.get_me()
        except Exception as e:
            print(e)
            await message.reply_text("Вы не аутентифицированы. Введите команду /login")
        print("login")
        
        with app:
            wallpaper_settings = WallPaperSettings()
            
            try:
                file_path = os.path.join(".", "temp", f"image_{message.photo.file_id}.jpeg")
                
                await client.download_media(message, file_name=file_path)
                os.remove(file_path)
                uploaded_file = await app.save_file(file_path)
                uploaded_wallpaper = await app.invoke(UploadWallPaper(file=uploaded_file, mime_type="image/jpeg", settings=wallpaper_settings, for_chat=True))
                
            except Exception as e:
                print(f"Ошибка при скачивании изображения: {e}")
                await message.reply_text("Произошла ошибка при скачивании изображения.")
            
            try:
                groupid = wallpaper_states.get(message.from_user.id, {}).get("groupid", None)
                temp = wallpaper_states.get(message.from_user.id, {}).get("temp", None)
                weather = wallpaper_states.get(message.from_user.id, {}).get("weather", None)
                degree = wallpaper_states.get(message.from_user.id, {}).get("degree", None)

                if not groupid or not temp or not weather or not degree:
                    await message.reply_text("Кажется что-то пошло не так. Попробуйте ещё раз.")
                    await cancel_all_command(client, message)
                    return

                await adb.execute(f"INSERT INTO weather_wallpaper (groupid, temp, weather, degree, wpid, wpah) VALUES ('{groupid}', {temp}, '{weather}', {degree}, {uploaded_wallpaper.id}, {uploaded_wallpaper.access_hash})")
            except Exception as e:
                print(f"Ошибка при сохранении изображения: {e}")
                await message.reply_text("Произошла ошибка при загрузке и сохранении изображения.")

            await message.reply_text("Отлично, все загружено!")


@bot.on_message(filters.text & filters.private)
async def handle_private_text(client: Client, message: Message):
    user_id = message.from_user.id
    text = message.text.strip()

    match main_states.get(message.from_user.id, MainState.IDLE):
        case MainState.IDLE:
            pass
        case MainState.AUTH:
            ast =  auth_states.get(message.from_user.id, {}).get("state", AuthState.IDLE)
            if ast == AuthState.WAITING_PHONE:
                logger.info(f"[{user_id}] Получен номер телефона: {text}")
                phone_number = text
                asyncio.create_task(start_user_auth(user_id, phone_number))
                await message.reply_text("⏳ Отправляю код подтверждения...")
            elif ast == AuthState.WAITING_CODE:
                logger.info(f"[{user_id}] Получен код: {'*' * len(text)}")
                code = text
                asyncio.create_task(process_user_code(user_id, code))
                await message.reply_text("⏳ Проверяю код...")
            elif ast == AuthState.WAITING_PASSWORD:
                logger.info(f"[{user_id}] Получен пароль: {'*' * len(text)}")
                password = text
                asyncio.create_task(process_user_password(user_id, password))
                await message.reply_text("⏳ Проверяю пароль...")
            elif ast == AuthState.LOGGED_IN:
                await message.reply_text("Вы уже вошли. Если хотите войти с другим аккаунтом, используйте /login.")
            elif ast == AuthState.ERROR:
                last_error = auth_states.get(user_id, {}).get('last_error', 'Произошла ошибка. Используйте /login для повторной попытки.')
                await message.reply_text(last_error)
            else:
                await message.reply_text("Неожиданное состояние. Используйте /login для начала.")
        case MainState.WALLPAPER:
            pass
        case MainState.AI: # AI
            pass


async def pre_message(client: Client, message: Message):
    if message.from_user.id not in g.cache:
        data = await g.adb.fetchone(f"SELECT userid, gemini_token FROM users WHERE userid == '{message.from_user.id}'")
        if not data:
            logger.info(f"Пользователь {message.from_user.username} ({message.from_user.id}) пытался получить доступ, но он не")
            message.stop_propagation()
            return
        else:
            g.cache[data[0]] = {"gemini_token": data[1], "context": []}



async def main():
    await bot.start()
    logger.info("Бот запущен.")
    
    await bot.set_bot_commands([
        BotCommand("start", "Стартовое сообщение"),
        BotCommand("set_token", "Установить свой gemini токен"),
    ])
    logger.info("Команды для автозаполнения отправлены.")
    
    bot.add_handler(MessageHandler(pre_message), -100)
    bot.add_handler(MessageHandler(start_command, filters.command("start") & filters.private), 1)
    bot.add_handler(MessageHandler(help_command, filters.command("help") & filters.private), 1)
    
    bot.add_handler(MessageHandler(set_gemini_token_command, filters.command("set_token") & filters.private), 1)
    bot.add_handler(MessageHandler(gemini_ask, filters.mentioned), 2)
    
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
    if not bot:
        quit()
    bot.run(main())
    #asyncio.run(main())