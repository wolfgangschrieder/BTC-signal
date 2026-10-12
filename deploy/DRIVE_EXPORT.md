# Private Drive report export

The optional `report-export` Compose service reads PostgreSQL without writes or
DeepSeek calls. Once a minute it checks the latest completed periodic/daily
reports and 20 current task results. It replaces two fixed, pre-created user-owned
files in a private folder. It never creates files, changes permissions, or exports
raw market events, environment variables, keys or database connection strings.
Canonical JSON is updated last; the text file is a readable mirror. A failed
partial upload retries. Unchanged content is skipped; restart may upload once.
Each payload is bounded to 512 KB. No permanent local report archive is created.
Existing journal retention is unchanged. Memory 128 MB, CPU 0.25, Docker logs 4 MB.

## One-time credentials

1. In your Google Cloud project enable the Google Drive API.
2. Create a dedicated service account, without project IAM roles or domain-wide
   delegation. Download its JSON key locally. Do not paste or upload it to chat.
3. Give that exact service-account email writer access ONLY to the report folder.
   Keep general access Restricted. Files remain owned by your Google user:
   service accounts have no Drive storage quota; pre-create files using your user.
4. Copy the JSON to the VPS with SCP. Run the setup script as root:

```bash
python3 deploy/configure-drive-export.py --key-file /root/drive-key.json --folder FOLDER_ID --json-file JSON_FILE_ID --text-file TEXT_FILE_ID
```

Setup copies the key to `deploy/secrets/drive-service-account.json`, owned by UID
10001, mode 0400; `.env` stays mode 0600. The credentials directory is excluded
from git and Docker build context. The key is mounted only into report-export.
Existing app and auditor do not receive Google credentials. The original key copy
is not automatically deleted. Protect it and rotate/revoke via Google Cloud.

Drive permissions, target MIME types and direct parents are checked before every
update; public/domain/group permissions or unavailable permission metadata stop
publication. These checks are not atomic with external sharing changes. A
service-account token has Drive scope but can access only assets shared with that
account; keep the account dedicated. Both permissions and upload must be tested
live before claiming export works. No real service-account key was available in
implementation tests; actual quota/permission behavior must be verified at setup.

Sources: https://developers.google.com/workspace/drive/api/reference/rest/v3/files/update
and https://developers.google.com/identity/protocols/oauth2/service-account

## Deploy and verify

```bash
cd /opt/BTC-signal
git pull --ff-only origin main
docker compose --env-file deploy/.env -f deploy/compose.yml build migrate
```

No new migration needed. After credentials and fixed IDs are configured:

```bash
docker compose --env-file deploy/.env -f deploy/compose.yml --profile report-export run --rm --no-deps report-export research-os auditor-export --once
```

Expect `Private Drive export completed`, verify readable files and private
permissions through Drive, then start the loop:

```bash
docker compose --env-file deploy/.env -f deploy/compose.yml --profile report-export up -d --no-deps report-export
```

This does not restart the market app or analyst. Stale reports retain their real
period timestamps. A ChatGPT scheduled reader must check freshness and report a
missing export rather than treating a placeholder or old report as new.
Stop/revoke access: `--profile report-export stop report-export` and revoke the
Google key. Never post the full Compose configuration, `.env` or key contents.
# Двусторонняя исследовательская очередь

Необязательный `DRIVE_RESEARCH_INBOX_ID` включает чтение отдельного пользовательского
`research-inbox.json` в той же закрытой папке. Сервер никогда не пишет в inbox.
Файл должен быть обычным application/json, не Google Doc. Обновлять его нужно на месте,
сохраняя ID. Подтверждения экспортируются в `research_inbox` текущего JSON-отчёта и
в раздел «ПОДТВЕРЖДЕНИЯ DRIVE» текста; отдельный файл ответов не требуется.

```json
{
  "schema_version": 1,
  "tasks": [{
    "task_id": "239e6e24-8558-4a0b-96ef-949fd8aa227b",
    "created_at_utc": "2026-10-12T22:30:00+00:00",
    "expires_at_utc": "2026-10-14T22:30:00+00:00",
    "kind": "experiment",
    "objective": "Спроектировать сравнение TA-only, microstructure-only и combined.",
    "evidence_refs": ["project.feature_groups"],
    "acceptance_criteria": "Одинаковые данные, расходы, хронологический split и метрики net return.",
    "reject_criteria": "Отсутствие преимущества на отложенной выборке после затрат.",
    "priority": 3
  }]
}
```

Не копировать пример как новую задачу после его срока действия. Генерировать новый UUID
для новой задачи, сохранять неизменными все поля уже принятой. До 10 записей/64 КБ,
каждая запись до 2000 UTF-8 байт; objective до 300 символов, criteria до 200,
8 references до 160 символов. Только UTC, срок до 7 суток, priority 2 или 3.
Доступные kinds: data_quality, signal_review, costs, experiment, hypothesis.
Прочие поля и credential-like значения отклоняются. Не помещать инструкции к shell,
SQL или изменению торговых настроек: задача — только исследовательские данные.

Приём транзакционный под существующим advisory lock. Один внешний UUID получает один
внутренний task_id. Повтор возвращает текущий статус; изменение принятого UUID —
`rejected/id_conflict`. Максимум три внешние задачи waiting/running, остальные deferred
до следующего опроса (не принятие!). Общий предел очереди 100 сохраняется. Ошибка загрузки
inbox не блокирует выгрузку отчётов, отмечается `research_inbox.status=unavailable`;
`--once` возвращает ненулевой код. Нельзя считать успешную выгрузку подтверждением приёма:
проверить receipt конкретного request_id.

Просроченная новая запись rejected/expired; принятая, но не назначенная до expires_at,
переходит в failed без API. Running не отменяется из-за наступления срока. Failed не
перезапускается автоматически: возможен оплаченный запрос без известного результата.
Удаление записи из inbox не отменяет уже принятую задачу. Дедуп хранится в существующей
90-дневной очереди; семидневный срок входа предотвращает повтор после очистки.

Аналитик использует фиксированную системную роль, задачи — недоверенный контекст.
LLM не исполняет код. Задачи выполняются в обычном четырёхчасовом цикле, максимум три
на запрос, с текущим атомарным бюджетом; импорт сам DeepSeek API не вызывает.
Для costs/experiment/hypothesis completed означает план, не выполненный эксперимент.
Подтверждения относятся к текущему содержимому inbox; последние 20 внутренних задач
также экспортируются. Для исторической задачи сохраняйте ID до чтения результата.

Для настройки повторно запустите configure-drive-export.py с прежними аргументами
и `--inbox-file ID`. Можно использовать уже установленный ключ
`deploy/secrets/drive-service-account.json` как --key-file, не выводя содержимое.
Пересоберите общий образ, пересоздайте auditor (для проверки expiry) и report-export.
Новых миграций нет. Приёмник по умолчанию выключен; пустой ENV сохраняет прежнее поведение.

