from __future__ import annotations

import json
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Finding(BaseModel):
    model_config = ConfigDict(extra='forbid')
    kind: Literal['finding', 'hypothesis']
    topic: Literal['data_quality', 'signal_quality', 'execution_costs', 'profitability',
                   'delivery', 'storage', 'methodology', 'other']
    severity: Literal['critical', 'high', 'medium', 'low']
    statement: str = Field(min_length=1, max_length=500)
    evidence_ids: list[str] = Field(min_length=1, max_length=6)
    verification: str = Field(min_length=1, max_length=500)


class AnalystReport(BaseModel):
    model_config = ConfigDict(extra='forbid')
    verdict: Literal['insufficient_data', 'negative_evidence', 'operational_issue', 'needs_review']
    comment: str = Field(min_length=1, max_length=1200)
    comment_evidence_ids: list[str] = Field(min_length=1, max_length=8)
    findings: list[Finding] = Field(default_factory=list, max_length=4)

    @model_validator(mode='after')
    def reject_credentials(self):
        value = json.dumps(self.model_dump(), ensure_ascii=False)
        if re.search(r'sk-[A-Za-z0-9_-]{12,}|\b\d{6,}:[A-Za-z0-9_-]{20,}', value):
            raise ValueError('Credential-like output rejected')
        return self

    def validate_evidence(self, evidence):
        if any(identifier not in evidence for identifier in self.comment_evidence_ids):
            raise ValueError("Unknown comment evidence identifier")
        for finding in self.findings:
            if any(identifier not in evidence for identifier in finding.evidence_ids):
                raise ValueError('Unknown evidence identifier')
        return self


def message(report: AnalystReport, kind: str, start, end, evidence=None):
    heading = 'СУТОЧНЫЙ РАЗБОР' if kind == 'daily' else 'АНАЛИТИК · 30 МИНУТ'
    lines = [f'🔬 {heading}', f'Интервал отчёта UTC: {start:%d.%m %H:%M}–{end:%d.%m %H:%M}',
             'Цель: проверять предпосылки доходности после затрат.',
             'Интерпретация DeepSeek; выводы требуют проверки.', '', report.comment]
    if evidence is not None:
        lines.insert(2, f"Окно данных UTC: {evidence.get('window.start_utc', '?')} — {evidence.get('window.end_utc', '?')}")
        lines.append('Основания комментария: ' + ', '.join(f'{key}={str(evidence[key])[:80]}' for key in report.comment_evidence_ids))
    for finding in report.findings:
        label = 'Гипотеза' if finding.kind == 'hypothesis' else 'Замечание'
        lines.extend(['', f'{label} [{finding.severity}]: {finding.statement}',
                      f'Основания: {", ".join(finding.evidence_ids)}',
                      f'Проверка: {finding.verification}'])
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
