#!/usr/bin/env python3
"""Configure Telegram on the VPS without exposing tokens or sending messages."""
import getpass
import json
import os
import re
import sys
import tempfile
import urllib.request
from pathlib import Path


class SetupError(Exception):
    pass


def api(token, method):
    try:
        request = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/{method}", data=b"", method="POST"
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            result = json.load(response)
        if not result.get("ok"):
            raise SetupError("Telegram отклонил запрос.")
        return result["result"]
    except SetupError:
        raise
    except (OSError, ValueError, KeyError, TypeError):
        # Network exceptions may include a URL containing the token.
        raise SetupError("Не удалось проверить Telegram. Проверьте токен и сеть.") from None


def private_chats(updates):
    chats = {}
    for update in updates:
        message = update.get("message", {})
        chat = message.get("chat", {})
        if chat.get("type") == "private" and message.get("text", "").split(" ")[0] == "/start":
            chats[str(chat["id"])] = chat
    return chats


def save_settings(path, token, chat_id):
    if path.is_symlink() or not path.is_file():
        raise SetupError("Нужен обычный файл deploy/.env с настройками PostgreSQL.")
    settings = {
        "TELEGRAM_BOT_TOKEN": token,
        "TELEGRAM_CHAT_ID": chat_id,
        "SIGNAL_EMISSION_ENABLED": "false",
    }
    lines = []
    for line in path.read_text().splitlines():
        key = line.split("=", 1)[0].strip()
        if key not in settings:
            lines.append(line)
    lines.extend(f"{key}={value}" for key, value in settings.items())
    fd, temporary = tempfile.mkstemp(prefix=".telegram-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write("\n".join(lines) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main():
    if not sys.stdin.isatty():
        raise SetupError("Запустите настройку в интерактивном SSH-терминале.")
    path = Path(__file__).resolve().parent / ".env"
    if not path.is_file():
        raise SetupError("Не найден deploy/.env. Сначала настройте PostgreSQL.")
    token = getpass.getpass("Новый токен из BotFather (ввод скрыт): ").strip()
    if not re.fullmatch(r"[0-9]+:[A-Za-z0-9_-]+", token):
        raise SetupError("Неверный формат токена.")
    bot = api(token, "getMe")
    print(f"Бот проверен: @{bot['username']}")
    chat_id = input("CHAT_ID, если известен; иначе Enter для поиска личного чата: ").strip()
    if not chat_id:
        if api(token, "getWebhookInfo").get("url"):
            raise SetupError("У бота настроен webhook. Укажите CHAT_ID вручную; webhook не изменён.")
        input("Откройте этого бота в Telegram, нажмите Start и затем Enter здесь: ")
        chats = private_chats(api(token, "getUpdates"))
        if not chats:
            raise SetupError("Личный чат с командой /start не найден. Отправьте /start и повторите настройку.")
        print("Найдены личные чаты:")
        for identifier, chat in chats.items():
            print(f"  {identifier}: {chat.get('first_name', '')} @{chat.get('username', '')}")
        chat_id = input("Введите ID вашего чата из списка: ").strip()
        if chat_id not in chats:
            raise SetupError("Выберите ID из списка.")
    if not re.fullmatch(r"[0-9]+", chat_id):
        raise SetupError("Для личного чата нужен положительный числовой CHAT_ID.")
    # getChat checks access without sending a test message.
    chat = api(token, f"getChat?chat_id={chat_id}")
    if chat.get("type") != "private":
        raise SetupError("Выбранный чат не является личным.")
    save_settings(path, token, chat_id)
    print("Настройки сохранены в deploy/.env (права 600). Отправка сигналов выключена.")
    print("Сообщения не отправлялись. Пересоздайте контейнер app для применения настроек.")


if __name__ == "__main__":
    try:
        main()
    except (SetupError, EOFError, KeyboardInterrupt) as error:
        print(str(error) if isinstance(error, SetupError) else "Настройка отменена.")
        raise SystemExit(1) from None
