import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from research_os.auditor.deployment_status import read_deployment_status


def updater():
    spec = importlib.util.spec_from_file_location('auto_update',Path(__file__).parents[1]/'deploy/auto-update.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_ci_requires_latest_success_for_exact_main_push():
    module = updater()
    sha = 'a'*40
    run = {'id':1,'head_sha':sha,'head_branch':'main','event':'push','name':'CI',
           'status':'completed','conclusion':'success'}
    assert module.ci_ready({'workflow_runs':[run]},sha)
    assert not module.ci_ready({'workflow_runs':[run,{**run,'id':2,'conclusion':'failure'}]},sha)
    assert not module.ci_ready({'workflow_runs':[{**run,'event':'pull_request'}]},sha)
    assert not module.ci_ready({'workflow_runs':[run]},'b'*40)


def test_migrations_require_operator_and_manifest_cannot_enable_shell():
    module = updater()
    manifest = json.dumps({'schema_version':1,'enabled':True,'migration_policy':'none'})
    module.policy(manifest,['src/research_os/auditor/client.py'])
    with pytest.raises(module.UpdateError):
        module.policy(manifest,['alembic/versions/new.py'])
    with pytest.raises(module.UpdateError):
        module.policy(json.dumps({'schema_version':1,'enabled':True,'migration_policy':'auto'}),[])


def prepare(module, tmp_path, monkeypatch, healthy=True, migration=False):
    old,new = 'a'*40,'b'*40
    monkeypatch.setattr(module,'REPO',tmp_path)
    monkeypatch.setattr(module,'STATUS',tmp_path/'deployment-status')
    monkeypatch.setattr(module,'INSTALLED',tmp_path/'not-installed')
    monkeypatch.setattr(module.shutil,'disk_usage',lambda p:SimpleNamespace(free=9_000_000_000))
    monkeypatch.setattr(module,'check_ci',lambda sha:True)
    monkeypatch.setattr(module,'services',lambda:['app'])
    monkeypatch.setattr(module,'previous_images',lambda s:{'app':'sha256:'+'a'*64})
    results = iter([healthy,True])
    monkeypatch.setattr(module,'wait_health',lambda *args:next(results))
    calls = []
    def fake(args,**kwargs):
        calls.append(args)
        if args[:4]==['git','remote','get-url','origin']: return module.ORIGIN
        if args[:3]==['git','branch','--show-current']: return 'main'
        if args[:2]==['git','rev-parse']: return old if args[-1]=='HEAD' else new
        if args[:3]==['git','diff','--name-only']: return 'alembic/versions/new.py' if migration else 'src/fix.py'
        if args[:2]==['git','show']: return '{"schema_version":1,"enabled":true,"migration_policy":"none"}'
        if args[:3]==['docker','image','inspect']: return 'sha256:'+'b'*64
        return ''
    monkeypatch.setattr(module,'run',fake)
    return calls,old,new


def test_success_only_recreates_selected_services_without_postgres_or_migrations(tmp_path,monkeypatch):
    module = updater()
    calls,_,new = prepare(module,tmp_path,monkeypatch)
    assert module.update()==0
    status = json.loads((module.STATUS/'status.json').read_text())
    assert status['status']=='deployed'
    assert json.loads((module.STATUS/'last-success.json').read_text())['revision']==new
    assert any('--no-deps' in args and args[-1]=='app' for args in calls)
    assert not any('postgres' in args or 'alembic' in args for args in calls)


def test_health_failure_restores_code_and_exact_image_without_retrying_failed_release(tmp_path,monkeypatch):
    module = updater()
    calls,old,new = prepare(module,tmp_path,monkeypatch,healthy=False)
    assert module.update()==1
    assert ['git','reset','--hard',old] in calls
    assert json.loads((module.STATUS/'status.json').read_text())['status']=='rolled_back'
    override = json.loads((module.STATUS/'runtime-compose.json').read_text())
    assert override['services']['app']['image']=='sha256:'+'a'*64
    assert not (module.STATUS/'last-success.json').exists()
    assert json.loads((module.STATUS/'failed-release.json').read_text())['revision']==new
    calls.clear()
    assert module.update()==1
    assert not any(args[:2]==['git','merge'] for args in calls)


def test_migration_does_not_change_checkout_or_images(tmp_path,monkeypatch):
    module = updater()
    calls,_,_ = prepare(module,tmp_path,monkeypatch,migration=True)
    assert module.update()==1
    assert not any(args[:2]==['git','merge'] or args[:2]==['docker','build'] for args in calls)
    assert json.loads((module.STATUS/'status.json').read_text())['reason']=='migration_requires_operator'


def test_interrupted_deployment_uses_durable_rollback_record(tmp_path,monkeypatch):
    module = updater()
    calls,old,new = prepare(module,tmp_path,monkeypatch)
    module.write_json(module.STATUS/'status.json',{'status':'deploying','previous_revision':old,
        'candidate_revision':new,'previous_images':{'app':'sha256:'+'a'*64}})
    assert module.update()==1
    assert ['git','reset','--hard',old] in calls
    assert json.loads((module.STATUS/'status.json').read_text())['status']=='rolled_back'


def test_health_requires_new_decision_after_deployment(monkeypatch):
    module = updater()
    def fake(args,**kwargs):
        if '--format' in args:
            return '{"Running":true,"OOMKilled":false,"Restarting":false}'
        if 'exec' in args:
            return '1'
        return 'container'
    monkeypatch.setattr(module,'run',fake)
    assert not module.healthy(['app'],None,2)


def test_deployment_export_drops_unrecognized_host_fields_and_values(tmp_path,monkeypatch):
    path = tmp_path/'status.json'
    monkeypatch.setenv('DEPLOY_STATUS_PATH',str(path))
    assert read_deployment_status()['status']=='not_installed'
    path.write_text(json.dumps({'status':'deployed','stage':'done','updated_at_utc':'2026-10-14T00:00:00+00:00',
                               'candidate_revision':'a'*40,'secret':'do not export','reason':'private provider body'}))
    data = read_deployment_status()
    assert data['candidate_revision']=='a'*40 and 'secret' not in data and 'reason' not in data
    path.write_text('{"status":"private body","stage":"done"}')
    assert read_deployment_status()=={'status':'unreadable'}
