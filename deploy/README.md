# Развёртывание на VPS

Требуются Linux x86_64, Docker Engine и Docker Compose v2. SSH-пароли, bot token и реальные `.env` не включаются в образ и репозиторий.

Из каталога проекта:

```bash
cp deploy/env.example deploy/.env
chmod 600 deploy/.env
# В редакторе замените POSTGRES_PASSWORD случайной hex-строкой:
# openssl rand -hex 32
# Настоящие секреты вводятся только на сервере.
docker compose --env-file deploy/.env -f deploy/compose.yml build
docker compose --env-file deploy/.env -f deploy/compose.yml up -d
```

По умолчанию `SIGNAL_EMISSION_ENABLED=false`: бот принимает публичные данные, хранит market states и исследовательские outcomes, но не создаёт Telegram-клиент и не отправляет сообщения. Для исследовательских сообщений до калибровки используйте режим наблюдения ниже; production требует проверенную калибровку. Для уведомлений нужны TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID. Режим наблюдения не требует ключей Bybit.

Миграции выполняются отдельным контейнером до запуска приложения. PostgreSQL доступен только внутри Docker-сети; публичный порт БД не публикуется. Приложение работает от непривилегированного UID. Логи ограничены по размеру.

Проверки:

```bash
docker compose --env-file deploy/.env -f deploy/compose.yml ps -a
docker compose --env-file deploy/.env -f deploy/compose.yml exec app research-os health
docker compose --env-file deploy/.env -f deploy/compose.yml logs --tail 100 app
```

`health` проверяет только БД. Дополнительно нужно проверить поступление raw.events, market.candles и world.market_state_vectors, отсутствие непрерывных reconnect/ошибок, лаг данных и пропуски. Для этого нужны доступ VPS к api.bybit.com и stream.bybit.com по HTTPS/WSS. При включении уведомлений требуется api.telegram.org.

При разрыве соединения стакан становится недействительным, история окна очищается и признаки прогреваются заново. Повреждённый trade batch блокирует выдачу новых сигналов до перезапуска. Успешные unit tests не заменяют длительную проверку реального потока.

Обновление: сначала сделайте резервную копию БД, затем пересоберите образ и выполните `up -d`. Не используйте `down -v`: это удалит историю.

Пример резервной копии (хранить вне репозитория, с правами 600):

```bash
umask 077
docker compose --env-file deploy/.env -f deploy/compose.yml exec -T postgres pg_dump -U research_os -Fc research_os > research_os.dump
```

Проверка восстановления и внешнее хранение резервных копий обязательны до постоянного запуска. Для обновления установленных версий используйте deploy/constraints.txt; текущие ограничения отражают версии, проверенные в облачной среде. Образ и стек пока должны отдельно пройти проверку на целевом VPS.

Для сервера можно подготовить комплект с готовыми Python wheels, чтобы сборка приложения не зависела от доступа VPS к PyPI:

```bash
BTC_BUILD_PYTHON=.venv/bin/python ./deploy/package-release.sh
# Передайте dist/btc-signal-release на VPS и выполните команды выше из его корня.
```

Контрольные суммы wheels проверяются при сборке release-образа. Docker всё ещё должен получить базовые образы из реестра. Локально проверены: установка wheel, запуск от UID 10001, все миграции на чистой TimescaleDB, health и pg_dump/pg_restore структуры БД. Восстановление большого набора реальных рыночных данных ещё не проверено.

Для общей диагностики из корня проекта выполните `bash deploy/status.sh`: скрипт показывает контейнеры, health БД, количество и лаг событий/state, outcomes и очередь уведомлений. Он не выводит `.env` или секреты. Research outcomes рассчитываются отдельной задачей сразу после запуска и затем каждые 60 секунд, в том числе при отключённых Telegram-уведомлениях. При временной ошибке БД расчёт повторяется на следующем цикле.

Настройка личного Telegram-чата на VPS:

```bash
python3 deploy/configure-telegram.py
```

Если токен раскрыт, сначала перевыпустите его через `/revoke` в BotFather. Скрипт запрашивает токен скрыто, проверяет бота через getMe и доступ к личному чату через getChat. Для поиска CHAT_ID откройте бота и отправьте `/start`; выберите свой ID из списка. Существующий webhook не изменяется. Скрипт не отправляет сообщений, сохраняет `.env` атомарно с правами 600, сохраняет пароль PostgreSQL и устанавливает SIGNAL_EMISSION_ENABLED=false. После настройки примените параметры командой `docker compose --env-file deploy/.env -f deploy/compose.yml up -d app`. Не публикуйте `.env` или токен.

После прогрева каждый расчёт сигнала записывает диагностическую строку `Signal evaluation` в журнал app: направление анализа, достаточность данных, некалиброванные оценки long/short/no-signal, ATR и причины отказа движка/guard. Посмотрите их через `docker compose --env-file deploy/.env -f deploy/compose.yml logs --tail 100 app`. Строка `allowed=True` означает прохождение фильтров расчёта, а не подтверждённую запись outcome или доставку Telegram. Настройка токена при выключенной отправке не создаёт outcomes сама по себе.

Для VPS с диском 28 ГБ Compose по умолчанию устанавливает `RAW_RETENTION_HOURS=6`. Каждую минуту приложение удаляет до 20 порций по 1000 сырых событий Bybit типов trade/ticker/orderbook_update/orderbook_snapshot, полученных более 6 часов назад, вместе с fingerprint и нормализованными строками сделок, тикеров и стакана. Каждая порция выполняется одной транзакцией. Очистка использует время получения, а не биржевое время: поздно полученные события не удаляются сразу. Миграция 0013 создаёт индекс для очистки без блокировки записи. Свечи, отдельные события funding/open interest/liquidations, состояния рынка, outcomes и outbox не удаляются. Funding/open interest, созданные из удаляемых тикеров, удаляются вместе с ними. Значение 0 выключает очистку; вне deploy по умолчанию очистка отключена.

После удаления старые подробные события недоступны для replay и проверки происхождения сохранённых состояний; для долговременного исследования нужен внешний архив. Удаление освобождает место для повторного использования PostgreSQL, но не гарантирует немедленное уменьшение файлов базы. Не запускайте VACUUM FULL на работающем боте. Ограничение по времени не является жёсткой квотой в ГБ: при росте потока, сбоях очистки, росте сохранённых данных, WAL или Docker-образов диск всё ещё может заполниться. `bash deploy/status.sh` теперь показывает свободное место и размер базы. Проверяйте их ежедневно; держите минимум 5 ГБ свободными. Очистка не заменяет внешнюю резервную копию свечей и результатов.

Для анализа оценок текущей модели на последних 10 000 сохранённых состояниях:

```bash
docker compose --env-file deploy/.env -f deploy/compose.yml exec -T app python -m research_os.research.signal_diagnostics
```

Отчёт показывает период выборки, направления и причины анализа, медиану/p90/максимум направленной оценки, количество кандидатов выше 0.70 и доступность признаков. Это пересчёт текущей моделью, а не исторический replay: кандидаты ещё должны пройти проверки ATR, риск-уровней и live guard. Прибыльность, вероятность успеха и калибровка здесь не измеряются. Команда не записывает outcomes и не отправляет сообщения.


### Storage guard for a 28 GB disk

Compose enables a startup check and a check every 10 seconds against the actual
PostgreSQL volume (mounted read-only in the app). Defaults are decimal **18 GB
maximum database size** and **5 GB minimum free filesystem space**. WAL, other
images, logs and other databases consume the free-space reserve even though they
are not counted by `pg_database_size`. An inaccessible volume or database probe
fails closed. Set `STORAGE_MAX_DATABASE_GB` and `STORAGE_MIN_FREE_GB` in deploy/.env.
Outside Compose the guard requires an explicit `STORAGE_PATH` on the database filesystem;
leave it empty only when storage is managed separately.

A failed check stops live ingestion and the runtime. The writer checks the blocked
flag before each transaction. Docker retries startup, but cannot resume ingestion
until both checks pass. This is a protective threshold, **not a hard disk quota**:
writes between checks, in-flight transactions, migrations, other commands and
other processes may still use space. Migrations run before the app guard, so check
free space before deploying. Retention does not run while startup is blocked;
operator intervention is needed. Do not automatically VACUUM FULL on a nearly
full disk: it needs additional working space. Delete expired disposable data and
unused Docker images safely, or move storage, then verify the volume reserve.

The six-hour policy now also deletes funding/open-interest rows attached to the
expired high-frequency raw events. This bounds per-ticker duplicates; **their
long-term ticker-derived history is no longer preserved**. Standalone funding/OI
events, candles and research results are preserved. Rows orphaned by older retention
runs are not retroactively deleted by this migration; quantify those separately
before an intentional cleanup. Historical research data, outcomes and states still
grow, so the guard can eventually stop the service even with retention working.
For ongoing monitoring run `deploy/status.sh`; keep backups off this disk.


### Optional live macro context

`CROSS_MARKET_ENABLED=true` connects live analysis to existing FRED observations
in PostgreSQL. It does not start a network collector or ingest news. Sources are
pinned to `DEFAULT_FRED_SERIES`: broad dollar (not DXY), SPX, NASDAQ, VIX, US10Y.
The cold worker reads at most two distinct dates per asset within 14 days every
60 seconds. Returned rows exclude future event dates and future availability;
same-date revisions use the latest vintage known at load time. The cache is
replaced atomically, never accumulated, and cleared on database failures.

A cache older than 120 seconds, a cache loaded after a decision, or a latest
observation older than seven days is unavailable. Defaults tolerate daily reports
and weekends; these are daily reported observations, not real-time market quotes.
Returns compare the last two reported dates, not necessarily consecutive days.
The US10Y feature is relative yield change, not a bond price return. Missing macro
data does not veto the independent BTC analysis. Available macro evidence is
neutral with zero directional strength and cannot increase a probability score.
The MSV stores each pair's source, times, PIT availability and values in data-quality
metadata covered by the fingerprint. No original payloads or extra history are
copied; this adds a small bounded amount to the existing state records, whose
long-term growth remains subject to the storage guard.

Populate a short explicit date range with the existing command, for example:

```bash
docker compose --env-file deploy/.env -f deploy/compose.yml exec -T app \
  research-os cross-market --start 2026-10-01 --end 2026-10-08 --assets SPX,NASDAQ,VIX,DOLLAR_BROAD,US10Y
```

Configure `FRED_API_KEY` for that command. Availability is recorded after the
response is received and decoded; newly fetched historical data cannot support
backdated decisions. Fetching is manual; an empty database leaves context unavailable.
Calibration context and analyzer versions change in this release. Previously pinned
models must be refitted and re-evaluated for the new context, even though macro
features do not change the directional score. No real source feed or server has
been validated by the synthetic/integration tests.


### Наблюдение с сигналами и комментариями в Telegram

Для личного наблюдения настройте Telegram на сервере:

```bash
python3 deploy/configure-telegram.py --observe
docker compose --env-file deploy/.env -f deploy/compose.yml up -d --force-recreate app
```

Скрипт скрыто запросит токен, проверит бота и выбранный личный чат, сохранит
`ENVIRONMENT=shadow`, `SIGNAL_EMISSION_ENABLED=true`, `CROSS_MARKET_ENABLED=false`.
Пароль PostgreSQL, накопленные данные и ограничения хранения сохраняются.
Он не отправляет тестового сообщения; отправка начнётся после пересоздания app.
Сначала нужны собранный актуальный образ и применённые миграции.

Сообщения содержат LONG/SHORT, исследовательскую оценку, зону входа, SL/TP,
комментарий из направленных аргументов анализа и ограничения расчёта.
В shadow используется русский формат без кнопок согласования, поскольку
обработчика пользовательских подтверждений в live-цикле нет. Калиброванные
оценки выделяются отдельно. Некалиброванный балл не называется вероятностью успеха.
Порог 0.70, проверка качества данных/стакана и cooldown 15 минут сохраняются;
в отсутствие подходящих условий сообщений может не быть. Отправка Telegram
не отключает сохранение прогнозов и автоматическое отслеживание outcomes.
Автоматических сделок нет. При production некалиброванные сигналы блокируются.

Не передавайте токен через этот чат или командную строку; вводите его в SSH-терминале.
Защита диска остаётся: БД менее 18 GB и свободное место не менее 5 GB.
Эти изменения должны быть установлены на VPS; подготовка кода не означает запуск.
Исследовательское сравнение порогов 0.40/0.50/0.60/0.70 на сохранённых состояниях и минутных свечах:

```bash
docker compose --env-file deploy/.env -f deploy/compose.yml exec -T app python -m research_os.research.threshold_check
```

Данные разделяются по середине временного интервала, сделки первой половины не пересекают границу второй. Вход — market по открытию следующей свечи, стоп 1 ATR, цель 1.5 ATR, горизонт 30 свечей. Расчёт использует комиссию 5.5 bps и проскальзывание 2 bps на каждую сторону (исследовательские допущения, не подтверждённые тарифы счёта). Незавершённые горизонты и пропуски исключаются, одновременные касания стопа/цели остаются ambiguous без придуманного результата. При timeout используется закрытие последней свечи. Выбор порога производится только на первой части при наличии минимум 20 результатов без ambiguous; отдельно выводится результат выбранного порога на второй части. Это пересчёт текущей моделью, а не воспроизведение исторического кода или live guard. Используется базовый ATR-риск без кластеров ликвидности; кандидаты могут пересекаться и не моделируют единый портфель. Средняя доходность — незалевередженная доходность на сделку, не доходность счёта. Команда не меняет настройки, не пишет outcomes и не отправляет Telegram.
