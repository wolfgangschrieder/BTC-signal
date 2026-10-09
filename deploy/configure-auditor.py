#!/usr/bin/env python3
"""Enable the analyst with hidden server-side credential entry; no API request."""
import getpass
import os
import re
import sys
import tempfile
from pathlib import Path


def save(path, key):
    if not re.fullmatch(r'sk-[A-Za-z0-9_-]{20,200}', key):
        raise ValueError('Неверный формат ключа')
    if path.is_symlink() or not path.is_file():
        raise ValueError('Нужен обычный файл deploy/.env с существующими настройками')
    updates = {'DEEPSEEK_API_KEY':key,'AUDITOR_ENABLED':'true','AUDITOR_TELEGRAM_ENABLED':'true'}
    lines = [line for line in path.read_text().splitlines() if line.split('=',1)[0].strip() not in updates]
    lines.extend(f'{name}={value}' for name,value in updates.items())
    descriptor, temporary = tempfile.mkstemp(prefix='.auditor-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w') as stream:
            stream.write('\n'.join(lines)+'\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main():
    if not sys.stdin.isatty():
        raise ValueError('Запустите в интерактивном SSH-терминале')
    key = getpass.getpass('Новый ключ DeepSeek (ввод скрыт): ').strip()
    save(Path(__file__).resolve().parent/'.env', key)
    print('Аналитик включён в настройках. Интервал 30 минут; ключ сохранён с правами 600.')
    print('API не вызывался. Для запуска нужен актуальный образ, миграции и profile auditor.')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, EOFError, KeyboardInterrupt):
        print('Настройка не завершена. Проверьте файл deploy/.env и формат нового ключа.')
        raise SystemExit(1) from None
