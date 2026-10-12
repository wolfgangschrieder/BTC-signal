import inspect
import json
from uuid import uuid4

import httpx
import pytest

from research_os.auditor.client import SYSTEM, DeepSeekAnalyst, prepare_prompt
from research_os.auditor.context import project_evidence
from research_os.auditor.tasks import QUESTIONS
from research_os.intelligence.analyzer import MarketAnalyzer


def test_feature_brief_describes_inspected_analyzer_without_claiming_live_version():
    evidence = project_evidence()
    groups = evidence['project.feature_groups']
    source = inspect.getsource(MarketAnalyzer)
    for name in groups['technical_direction']:
        if name.startswith('tf_'):
            assert name.split('_')[1] in source
        else:
            assert name in source
    for name in groups['microstructure_direction']:
        assert name in source
    assert 'not verification' in evidence['project.code_versions']['scope']
    assert 'NOT account tariffs' in evidence['project.cost_scenarios']['label']
    assert 'perpetual' in evidence['project.instrument']


def test_design_questions_do_not_require_outcomes_or_fake_execution():
    for kind in ('costs','experiment','hypothesis'):
        assert 'DESIGN ONLY' in QUESTIONS[kind]
    assert 'ASSESS' in QUESTIONS['signal_review']
    assert 'completed' in QUESTIONS['experiment']
    assert 'изменения оценить нельзя' in SYSTEM


def test_realistic_three_task_context_and_history_fit_existing_byte_budget():
    evidence = project_evidence() | {'cohort.completed':0, 'sample.states':239}
    # Allow for the existing numeric snapshot and two bounded previous summaries.
    evidence.update({f'metric.{i}':i for i in range(60)})
    tasks = [{'task_id':str(uuid4()),'kind':kind,'question':QUESTIONS[kind],
              'context':{'source':'operator'}} for kind in ('costs','experiment','hypothesis')]
    previous = [{'comment':'я'*300,'findings':[{'topic':'methodology','statement':'п'*200}],
                 'evidence':{f'metric.{i}':i for i in range(13)}} for _ in range(2)]
    history = [{'kind':'experiment','status':'insufficient_data','conclusion':'я'*180,
                'next_check':'п'*120} for _ in range(3)]
    payload, size = prepare_prompt({'evidence':evidence,'limitations':'л'*700,
                                   'tasks':tasks,'task_history':history},previous)
    assert size<=16000
    assert json.loads(payload)['task_history']==history


@pytest.mark.asyncio
async def test_empty_cohort_can_accept_a_design_without_claiming_experiment_execution():
    identity = str(uuid4())
    evidence = project_evidence() | {'cohort.completed':0}
    tasks = [{'task_id':identity,'kind':'experiment','question':QUESTIONS['experiment'],'context':{}}]
    payload, _ = prepare_prompt({'evidence':evidence,'limitations':'','tasks':tasks},[])
    data = {'verdict':'insufficient_data','comment':'Результаты ещё не измерены.',
            'comment_evidence_ids':['cohort.completed'],'findings':[],
            'task_results':[{'task_id':identity,'status':'completed',
                'conclusion':'План: TA / микроструктура / вместе; одинаковые затраты, риск и временные сплиты.',
                'evidence_ids':['project.feature_groups','project.experiment_protocol'],
                'next_check':'Реализовать абляцию и измерить net return на независимом тесте.'}]}
    transport = httpx.MockTransport(lambda _:httpx.Response(200,json={'choices':[{
        'finish_reason':'stop','message':{'content':json.dumps(data)}}]}))
    value, _ = await DeepSeekAnalyst('placeholder','deepseek-flash',transport=transport).analyze(payload,evidence)
    assert value.task_results[0].status=='completed'
    assert value.verdict=='insufficient_data'
