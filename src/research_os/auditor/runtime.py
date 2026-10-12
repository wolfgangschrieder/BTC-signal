from __future__ import annotations

import asyncio
import logging
import signal
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import text

from research_os.auditor.client import DeepSeekAnalyst, prepare_prompt
from research_os.auditor.models import AnalystReport, message, message_parts, summary_message
from research_os.auditor.repository import AuditorRepository
from research_os.auditor.snapshot import collect_snapshot
from research_os.auditor.tasks import TaskRepository, discover_tasks, operational_findings
from research_os.core.config import get_settings
from research_os.database.session import SessionLocal
from research_os.notifications.telegram_client import TelegramClient
from research_os.pipeline.storage import StorageBudget

logger = logging.getLogger(__name__)
MOSCOW = ZoneInfo('Europe/Moscow')
INTERVAL = 14400
MONITOR_INTERVAL = 1800


def windows(now):
    local = now.astimezone(MOSCOW)
    end = local.replace(hour=local.hour // 4 * 4, minute=0, second=0, microsecond=0).astimezone(UTC)
    day_end = end.astimezone(MOSCOW).replace(hour=0, minute=0, second=0, microsecond=0)
    return [('periodic', end-timedelta(seconds=INTERVAL), end),
            ('daily', (day_end-timedelta(days=1)).astimezone(UTC), day_end.astimezone(UTC))]


class AuditorService:
    def __init__(self, settings, *, session_factory=SessionLocal, analyst=None, telegram=None, storage=None):
        self.settings = settings
        self.session_factory = session_factory
        self.repository = AuditorRepository()
        self.tasks = TaskRepository()
        self.analyst = analyst or DeepSeekAnalyst(settings.deepseek_api_key.get_secret_value(), settings.auditor_model)
        self.telegram = telegram
        self.storage = storage

    def _write(self, method, *args, **kwargs):
        if self.storage is not None:
            self.storage.check()
            self.storage.require_writable()
        with self.session_factory() as session:
            session.execute(text("SET LOCAL statement_timeout = '5s'"))
            result = method(session, *args, **kwargs)
            session.commit()
            return result

    def _exists(self, kind, start):
        with self.session_factory() as session:
            session.execute(text("SET LOCAL statement_timeout = '5s'"))
            return bool(session.execute(text('SELECT 1 FROM intelligence.auditor_runs WHERE kind=:kind AND period_start=:start'),
                                        {'kind':kind,'start':start}).first())

    def _snapshot(self, kind, end):
        with self.session_factory() as session:
            snapshot = collect_snapshot(session, end, kind, self.settings)
            previous = self.repository.previous(session, kind)
            if kind == 'periodic':
                snapshot['tasks'] = self.tasks.pending(session)
                for task in snapshot['tasks']:
                    for key, value in task['context'].items():
                        snapshot['evidence'][f"task.{task['task_id']}.{key}"] = value
        return snapshot, previous

    async def audit(self, kind, start, end, now):
        if await asyncio.to_thread(self._exists, kind, start):
            return
        snapshot, previous = await asyncio.to_thread(self._snapshot, kind, end)
        payload, size = prepare_prompt(snapshot, previous)
        reserved = size + self.settings.auditor_max_output_tokens + 512
        budget_start = now.astimezone(MOSCOW).replace(hour=0,minute=0,second=0,microsecond=0).astimezone(UTC)
        identity = await asyncio.to_thread(self._write, self.repository.reserve, kind=kind,start=start,end=end,
                                          snapshot=snapshot,model=self.settings.auditor_model,tokens=reserved,
                                          budget_start=budget_start,budget_end=budget_start+timedelta(days=1),
                                          daily_budget=self.settings.auditor_daily_token_budget)
        if identity is None:
            logger.info('Auditor slot already reserved or daily budget reached')
            return
        try:
            report, usage = await asyncio.wait_for(
                self.analyst.analyze(payload, snapshot['evidence'], self.settings.auditor_max_output_tokens), timeout=75)
            report.validate_tasks(snapshot.get('tasks', []))
            text_message = message(report, kind, start, end, snapshot['evidence'])
            await asyncio.to_thread(self._write, self.repository.complete, identity, report, text_message, usage,
                                    summary_message(report,kind,start,end,identity))
            logger.info("Auditor report saved id=%s kind=%s parts=%s", identity, kind, len(message_parts(text_message)))
        except Exception as error:  # noqa: BLE001 - preserve spent reservation; never log provider body/key
            await asyncio.to_thread(self._write, self.repository.fail, identity, error)
            logger.warning('Auditor analysis failed (%s)', type(error).__name__)

    async def deliver_once(self):
        if self.telegram is None:
            return
        item = await asyncio.to_thread(self._write, self.repository.claim)
        if item is None:
            return
        try:
            parts = message_parts(item['message'])
            index = item.get('message_part', 0)
            await asyncio.wait_for(self.telegram.send(parts[index]), timeout=20)
        except Exception as error:  # noqa: BLE001 - store exception type only
            await asyncio.to_thread(self._write, self.repository.retry, item, error)
        else:
            await asyncio.to_thread(self._write, self.repository.delivered, item, index + 1 < len(parts))
            logger.info("Auditor Telegram part delivered part=%s total=%s", index + 1, len(parts))

    async def delivery_loop(self, stop):
        while not stop.is_set():
            try:
                await self.deliver_once()
            except Exception as error:  # noqa: BLE001 - isolated notification failure
                logger.warning('Auditor delivery failed (%s)', type(error).__name__)
            try:
                await asyncio.wait_for(stop.wait(), timeout=10)
            except TimeoutError:
                pass

    def _monitor(self, now):
        # Current operational metrics must not be backdated to a report boundary.
        if self.storage is not None:
            self.storage.check()
            self.storage.require_writable()
        with self.session_factory() as session:
            snapshot = collect_snapshot(session, now, 'monitor', self.settings)
            session.commit()  # collect_snapshot uses a read-only transaction
            session.execute(text("SET LOCAL statement_timeout = '5s'"))
            session.execute(text('SELECT pg_advisory_xact_lock(8247132)'))
            self.tasks.prune(session, now)
            discover_tasks(session, snapshot['evidence'], now, self.tasks)
            issues = operational_findings(snapshot['evidence'])
            # One alert per issue per Moscow day; every check still updates task discovery.
            fresh = []
            for key, description in issues:
                identity = self.tasks.enqueue(session, 'data_quality',
                    'alert:'+now.astimezone(MOSCOW).date().isoformat()+':'+key,
                    {'metric':key,'value':snapshot['evidence'][key]},1)
                if identity:
                    fresh.append((key,description))
            if fresh:
                report = AnalystReport(verdict='operational_issue',
                    comment='\n'.join(description for _,description in fresh),
                    comment_evidence_ids=[key for key,_ in fresh])
                start = now-timedelta(seconds=MONITOR_INTERVAL)
                identity = self.repository.reserve(session, kind='alert', start=start, end=now,
                    snapshot=snapshot,model='local-monitor',tokens=0,budget_start=now,
                    budget_end=now,daily_budget=self.settings.auditor_daily_token_budget)
                if identity:
                    body = message(report,'alert',start,now,snapshot['evidence'])
                    body = body.replace('Интерпретация DeepSeek; выводы требуют проверки.',
                                        'Автоматическая техническая проверка; API DeepSeek не вызывался.')
                    self.repository.complete(session,identity,report,body,0)
            session.commit()

    async def run(self, stop):
        delivery = asyncio.create_task(self.delivery_loop(stop))
        try:
            while not stop.is_set():
                now = datetime.now(UTC)
                try:
                    await asyncio.to_thread(self._monitor, now)
                    await asyncio.to_thread(self._write, self.repository.prune, now, self.settings.auditor_retention_days)
                    for kind, start, end in windows(now):
                        if stop.is_set():
                            break
                        await self.audit(kind, start, end, now)
                except Exception as error:  # noqa: BLE001 - analyst must not stop the market app
                    logger.warning('Auditor cycle failed (%s)', type(error).__name__)
                remaining = MONITOR_INTERVAL - datetime.now(UTC).timestamp() % MONITOR_INTERVAL
                try:
                    await asyncio.wait_for(stop.wait(), timeout=remaining)
                except TimeoutError:
                    pass
        finally:
            stop.set()
            await delivery


async def run():
    settings = get_settings()
    if not settings.auditor_enabled or not settings.deepseek_api_key.get_secret_value():
        raise RuntimeError('Enable auditor and configure DEEPSEEK_API_KEY on the server')
    telegram = None
    if settings.auditor_telegram_enabled:
        if not settings.telegram_bot_token or not settings.telegram_chat_id:
            raise RuntimeError('Auditor Telegram credentials are required')
        telegram = TelegramClient(settings.telegram_bot_token, settings.telegram_chat_id)
    storage = StorageBudget(settings.storage_path, settings.storage_max_database_gb,
                            settings.storage_min_free_gb) if settings.storage_path else None
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for name in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(name, stop.set)
    await AuditorService(settings, telegram=telegram, storage=storage).run(stop)


def main():
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(name)s %(message)s')
    # HTTP libraries must not emit provider bodies or credential-bearing Telegram URLs.
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('httpcore').setLevel(logging.WARNING)
    asyncio.run(run())
