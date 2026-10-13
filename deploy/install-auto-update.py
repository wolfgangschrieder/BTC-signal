#!/usr/bin/env python3
"""One-time local installation; no credentials or env contents are printed."""
import importlib.util
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path('/opt/BTC-signal')


def main():
    if os.geteuid()!=0 or Path(__file__).resolve().parent!=ROOT/'deploy':
        print('Запустите установщик от root в /opt/BTC-signal/deploy.')
        return 1
    directory = ROOT/'deploy/deployment-status'
    if directory.is_symlink():
        raise RuntimeError('Unsafe status directory')
    directory.mkdir(mode=0o755,exist_ok=True)
    os.chmod(directory,0o755)
    spec = importlib.util.spec_from_file_location('btc_updater',ROOT/'deploy/auto-update.py')
    updater = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(updater)
    revision = updater.run(['git','rev-parse','HEAD'])
    if updater.run(['git','branch','--show-current'])!='main' or updater.run(['git','status','--porcelain','--untracked-files=no']):
        print('Установка остановлена: нужна чистая main.')
        return 1
    if not updater.check_ci(revision):
        print('Установка остановлена: дождитесь успешного main CI и повторите установщик.')
        return 1
    updater.policy((ROOT/'deploy/auto-release.json').read_text(),[])
    if 'report-export' in updater.services():
        # Bootstrap the stable status reader before enabling updates, so first rollback is visible.
        if shutil.disk_usage(ROOT).free<8_000_000_000:
            print('Установка остановлена: для сборки нужно 8 ГБ свободного места.')
            return 1
        prior = updater.previous_images(['report-export'])
        tag = 'btc-signal:auto-'+revision
        updater.run(['docker','build','--label','org.btc-signal.auto-managed=true','-t',tag,
                     '-f','Dockerfile','.'],timeout=600)
        if shutil.disk_usage(ROOT).free<5_000_000_000:
            print('Установка остановлена: после сборки осталось меньше5 ГБ.')
            return 1
        override = directory/'bootstrap-compose.json'
        updater.write_json(override,{'services':{'report-export':{'image':tag}}})
        try:
            updater.run(updater.compose(override)+['up','-d','--no-deps','--force-recreate','report-export'],timeout=150)
        except Exception:  # noqa: BLE001 - retain the old exporter on bootstrap command failure
            updater.write_json(override,{'services':{'report-export':{'image':prior['report-export']}}})
            updater.run(updater.compose(override)+['up','-d','--no-deps','--force-recreate','report-export'],timeout=150)
            return 1
    target = Path('/usr/local/lib/btc-signal-auto-update.py')
    if target.is_symlink():
        raise RuntimeError('Unsafe updater destination')
    shutil.copyfile(ROOT/'deploy/auto-update.py',target)
    os.chmod(target,0o755)
    Path('/etc/systemd/system/btc-signal-auto-update.service').write_text('''[Unit]
Description=BTC-signal verified code updater
After=docker.service network-online.target
Wants=network-online.target
Requires=docker.service

[Service]
Type=oneshot
User=root
WorkingDirectory=/opt/BTC-signal
ExecStart=/usr/bin/python3 /usr/local/lib/btc-signal-auto-update.py
TimeoutStartSec=2400
Nice=10
UMask=0022
''')
    Path('/etc/systemd/system/btc-signal-auto-update.timer').write_text('''[Unit]
Description=Check verified BTC-signal releases hourly

[Timer]
OnBootSec=90s
OnUnitInactiveSec=1h
Unit=btc-signal-auto-update.service

[Install]
WantedBy=timers.target
''')
    subprocess.run(['systemctl','daemon-reload'],check=True)
    subprocess.run(['systemctl','enable','--now','btc-signal-auto-update.timer'],check=True)
    print('Таймер установлен: проверка раз в час, первый запуск после установки/старта таймера.')
    print('Миграции, PostgreSQL и секреты автоматически не изменяются.')
    return 0


if __name__=='__main__':
    raise SystemExit(main())
