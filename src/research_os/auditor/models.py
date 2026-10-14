from __future__ import annotations

import json
import re
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator


def unique_evidence_ids(value):
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return list(dict.fromkeys(value))
    return value


# Provider output is byte-bounded by the client. Allow complete supporting ID
# lists while still bounding them and validating every ID against the snapshot.
EvidenceIds = Annotated[
    list[str], Field(min_length=1, max_length=128), BeforeValidator(unique_evidence_ids)
]


class Finding(BaseModel):
    model_config = ConfigDict(extra='forbid')
    kind: Literal['finding', 'hypothesis']
    topic: Literal['data_quality', 'signal_quality', 'execution_costs', 'profitability',
                   'delivery', 'storage', 'methodology', 'other']
    severity: Literal['critical', 'high', 'medium', 'low', 'unspecified'] = 'unspecified'
    statement: str = Field(min_length=1, max_length=500)
    evidence_ids: EvidenceIds
    verification: str = Field(min_length=1, max_length=500)


class TaskResult(BaseModel):
    model_config = ConfigDict(extra='forbid')
    task_id: str = Field(min_length=36, max_length=36)
    status: Literal['completed', 'insufficient_data']
    conclusion: str = Field(min_length=1, max_length=600)
    evidence_ids: EvidenceIds
    next_check: str = Field(min_length=1, max_length=400)


class AnalystReport(BaseModel):
    model_config = ConfigDict(extra='forbid')
    verdict: Literal['insufficient_data', 'negative_evidence', 'operational_issue', 'needs_review']
    comment: str = Field(min_length=1, max_length=1200)
    comment_evidence_ids: EvidenceIds
    findings: list[Finding] = Field(default_factory=list, max_length=4)

    task_results: list[TaskResult] = Field(default_factory=list, max_length=3)

    @model_validator(mode='after')
    def reject_credentials(self):
        value = json.dumps(self.model_dump(), ensure_ascii=False)
        if re.search(r'sk-[A-Za-z0-9_-]{12,}|\b\d{6,}:[A-Za-z0-9_-]{20,}', value):
            raise ValueError('Credential-like output rejected')
        return self

    def validate_tasks(self, tasks):
        expected = {task['task_id'] for task in tasks}
        actual = [result.task_id for result in self.task_results]
        if len(actual) != len(set(actual)) or set(actual) != expected:
            raise ValueError('Task result identities do not match assigned tasks')
        return self

    def validate_evidence(self, evidence):
        if any(identifier not in evidence for identifier in self.comment_evidence_ids):
            raise ValueError("Unknown comment evidence identifier")
        for finding in [*self.findings, *self.task_results]:
            if any(identifier not in evidence for identifier in finding.evidence_ids):
                raise ValueError('Unknown evidence identifier')
        return self


def message(report: AnalystReport, kind: str, start, end, evidence=None):
    heading = 'ТЕХНИЧЕСКИЙ КОНТРОЛЬ' if kind == 'alert' else ('СУТОЧНЫЙ РАЗБОР' if kind == 'daily' else f'АНАЛИТИК · {int((end-start).total_seconds() // 60)} МИНУТ')
    lines = [f'🔬 {heading}', f'Интервал отчёта UTC: {start:%d.%m %H:%M}–{end:%d.%m %H:%M}',
             'Цель: проверять предпосылки доходности после затрат.',
             'Интерпретация DeepSeek; выводы требуют проверки.', '', report.comment]
    if evidence is not None:
        lines.insert(2, f"Окно данных UTC: {evidence.get('window.start_utc', '?')} — {evidence.get('window.end_utc', '?')}")
        lines.append('Основания комментария: ' + ', '.join(f'{key}={str(evidence[key])[:80]}' for key in report.comment_evidence_ids))
    for finding in report.findings:
        label = 'Гипотеза' if finding.kind == 'hypothesis' else 'Замечание'
        severity = 'не указана' if finding.severity == 'unspecified' else finding.severity
        lines.extend(['', f'{label} [{severity}]: {finding.statement}',
                      f'Основания: {", ".join(finding.evidence_ids)}',
                      f'Проверка: {finding.verification}'])
    for result in report.task_results:
        lines.extend(['', f'Задача {result.task_id} · {result.status}', result.conclusion,
                      f'Следующая проверка: {result.next_check}'])
    return '\n'.join(lines)


def message_parts(body: str) -> list[str]:
    # Keep all text, including whitespace and supplementary Unicode characters.
    chunks, current, units = [], [], 0
    for character in body:
        width = len(character.encode('utf-16-le')) // 2
        if units + width > 3400:
            chunks.append(''.join(current))
            current, units = [], 0
        current.append(character)
        units += width
    if current:
        chunks.append(''.join(current))
    if len(chunks) <= 1:
        return chunks
    return [f'Часть {index}/{len(chunks)}\n{chunk}' for index, chunk in enumerate(chunks, 1)]


def summary_message(report, kind, start, end, identity):
    heading = 'СУТОЧНЫЙ РАЗБОР' if kind == 'daily' else 'АНАЛИТИК · 4 ЧАСА'
    lines = [f'🔬 {heading}', f'UTC: {start:%d.%m %H:%M}–{end:%d.%m %H:%M}',
             'Интерпретация DeepSeek; выводы требуют проверки.', report.comment,
             f'Замечаний: {len(report.findings)} · задач: {len(report.task_results)}']
    for result in report.task_results:
        lines.append(f'Задача {result.task_id}: {result.status}')
    lines.append(f'Полный отчёт в базе · ID: {identity}')
    return '\n'.join(lines)
