#!/usr/bin/env python3
"""One-time local installation; no credentials or env contents are printed."""
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
