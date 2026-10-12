#!/usr/bin/env python3
"""Install a server-owned Google key without printing its contents or calling APIs."""
import argparse
import json
import os
import re
import stat
import tempfile
from pathlib import Path


def setup(source, env, folder, json_id, text_id):
    for value in (folder,json_id,text_id):
        if not re.fullmatch(r'[A-Za-z0-9_-]{10,160}',value):
            raise ValueError('Invalid file identifier')
    if len({folder,json_id,text_id})!=3 or source.is_symlink() or not source.is_file():
        raise ValueError('Expected distinct IDs and a regular key file')
    if source.stat().st_size>32000 or env.is_symlink() or not env.is_file():
        raise ValueError('Invalid setup files')
    body = source.read_bytes()
    data = json.loads(body)
    if data.get('type')!='service_account' or data.get('token_uri')!='https://oauth2.googleapis.com/token':
        raise ValueError('Expected Google service-account key')
    email = data.get('client_email','')
    if not re.fullmatch(r'[A-Za-z0-9._-]+@[A-Za-z0-9.-]+\.iam\.gserviceaccount\.com',email):
        raise ValueError('Invalid service account email')
    directory = env.parent/'secrets'
    if directory.is_symlink():
        raise ValueError('Secret directory cannot be a symlink')
    directory.mkdir(mode=0o700,exist_ok=True)
    os.chmod(directory,0o700)
    destination = directory/'drive-service-account.json'
    if destination.is_symlink():
        raise ValueError('Key destination cannot be a symlink')
    descriptor, temporary = tempfile.mkstemp(dir=directory,prefix='.drive-')
    try:
        with os.fdopen(descriptor,'wb') as stream:
            stream.write(body)
        os.chown(temporary,10001,10001)
        os.chmod(temporary,stat.S_IRUSR)
        os.replace(temporary,destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    updates = {'DRIVE_EXPORT_KEY_PATH':str(destination.resolve()),'DRIVE_EXPORT_FOLDER_ID':folder,
               'DRIVE_EXPORT_JSON_ID':json_id,'DRIVE_EXPORT_TEXT_ID':text_id}
    lines = [line for line in env.read_text().splitlines() if line.split('=',1)[0].strip() not in updates]
    lines.extend(f'{key}={value}' for key,value in updates.items())
    descriptor, temporary = tempfile.mkstemp(dir=env.parent,prefix='.drive-env-')
    try:
        with os.fdopen(descriptor,'w') as stream:
            stream.write('\n'.join(lines)+'\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary,env)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return email


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--key-file',type=Path,required=True)
    parser.add_argument('--folder',required=True)
    parser.add_argument('--json-file',required=True)
    parser.add_argument('--text-file',required=True)
    args = parser.parse_args()
    try:
        email = setup(args.key_file,Path(__file__).resolve().parent/'.env',args.folder,args.json_file,args.text_file)
    except Exception:  # noqa: BLE001 - never print private-key content through parser errors
        print('Настройка не завершена. Проверьте JSON-ключ, IDs и права root.')
        return 1
    print('Конфигурация сохранена; API не вызывался.')
    print('Дайте доступ редактора только к папке отчётов сервисному аккаунту:',email)
    return 0


if __name__=='__main__':
    raise SystemExit(main())
