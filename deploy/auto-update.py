#!/usr/bin/env python3
"""Fixed-repository updater. No shell, no Drive commands, no database rollback."""
import fcntl
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

REPO = Path('/opt/BTC-signal')
INSTALLED = Path('/usr/local/lib/btc-signal-auto-update.py')
ORIGIN = 'https://github.com/wolfgangschrieder/BTC-signal.git'
STATUS = REPO/'deploy/deployment-status'
SHA = re.compile(r'[a-f0-9]{40}')
IMAGE = re.compile(r'sha256:[a-f0-9]{64}')
REASONS = frozenset(('command_failed','unsafe_status_path','ci_response_too_large',
    'release_disabled_or_unsupported','migration_requires_operator','baseline_container_missing',
    'baseline_image_invalid','unexpected_repository','repository_not_clean_main',
    'insufficient_build_space','invalid_revision','insufficient_runtime_space','health_check_failed',
    'interrupted_deployment_requires_operator'))


class UpdateError(RuntimeError):
    pass


def run(args, timeout=60):
    result = subprocess.run(args,check=False,cwd=REPO,capture_output=True,text=True,timeout=timeout,
                            env={**os.environ,'GIT_TERMINAL_PROMPT':'0'})
    if result.returncode:
        raise UpdateError('command_failed')
    return result.stdout.strip()


def write_json(path, value):
    if path.is_symlink() or path.parent.is_symlink():
        raise UpdateError('unsafe_status_path')
    path.parent.mkdir(mode=0o755,parents=True,exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent,prefix='.status-')
    try:
        with os.fdopen(descriptor,'w') as stream:
            json.dump(value,stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary,0o644)
        os.replace(temporary,path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def ci_ready(payload, sha):
    matches = [item for item in payload.get('workflow_runs',[]) if item.get('head_sha')==sha
               and item.get('head_branch')=='main' and item.get('event')=='push'
               and item.get('name')=='CI']
    latest = max(matches,key=lambda item:item.get('id',0),default={})
    return latest.get('status')=='completed' and latest.get('conclusion')=='success'


def check_ci(sha):
    query = urllib.parse.urlencode({'head_sha':sha,'branch':'main','event':'push','per_page':20})
    request = urllib.request.Request(
        'https://api.github.com/repos/wolfgangschrieder/BTC-signal/actions/workflows/ci.yml/runs?'+query,
        headers={'Accept':'application/vnd.github+json','User-Agent':'BTC-signal-auto-update',
                 'X-GitHub-Api-Version':'2026-03-10'})
    with urllib.request.urlopen(request,timeout=15) as response:
        body = response.read(512001)
    if len(body)>512000:
        raise UpdateError('ci_response_too_large')
    return ci_ready(json.loads(body),sha)


def services():
    # Values are only used for fixed service selection; never logged or exported.
    values = {}
    for line in (REPO/'deploy/.env').read_text().splitlines():
        key,separator,value = line.partition('=')
        if separator and key.strip() in ('AUDITOR_ENABLED','DRIVE_EXPORT_FOLDER_ID'):
            values[key.strip()] = value.strip().strip('\"\'')
    result = ['app']
    if values.get('AUDITOR_ENABLED','').lower() in ('true','1'):
        result.append('auditor')
    if values.get('DRIVE_EXPORT_FOLDER_ID'):
        result.append('report-export')
    return result


def compose(override=None):
    command = ['docker','compose','--env-file',str(REPO/'deploy/.env'),
               '-f',str(REPO/'deploy/compose.yml')]
    if override:
        command += ['-f',str(override)]
    return command+['--profile','auditor','--profile','report-export']


def build_image(tag, override):
    """Build through Compose so servers without the legacy docker buildx plugin work."""
    write_json(override,{'services':{'migrate':{
        'image':tag,
        'build':{'labels':{'org.btc-signal.auto-managed':'true'}},
    }}})
    run(compose(override)+['build','migrate'],timeout=600)


def policy(text_body, changed):
    data = json.loads(text_body)
    if data!={'schema_version':1,'enabled':True,'migration_policy':'none'}:
        raise UpdateError('release_disabled_or_unsupported')
    if any(path.startswith('alembic/') or path=='alembic.ini' for path in changed):
        raise UpdateError('migration_requires_operator')


def previous_images(selected):
    images = {}
    for service in selected:
        identity = run(compose()+['ps','-q',service])
        if not identity or '\n' in identity:
            raise UpdateError('baseline_container_missing')
        image = run(['docker','inspect','--format','{{.Image}}',identity])
        if not IMAGE.fullmatch(image):
            raise UpdateError('baseline_image_invalid')
        images[service] = image
    return images


def healthy(selected, override, started):
    for service in selected:
        identity = run(compose(override)+['ps','-q',service])
        if not identity or '\n' in identity:
            return False
        state = json.loads(run(['docker','inspect','--format','{{json .State}}',identity]))
        if not state.get('Running') or state.get('OOMKilled') or state.get('Restarting'):
            return False
    # Require a NEW market decision, not a merely running container or pre-deploy row.
    program = ("from sqlalchemy import text; from research_os.database.session import SessionLocal; "
        "s=SessionLocal(); s.execute(text('SET TRANSACTION READ ONLY')); "
        "s.execute(text(\"SET LOCAL statement_timeout = '5s'\")); "
        "r=s.execute(text(\"SELECT decision_time FROM world.market_state_vectors WHERE symbol='BTCUSDT' ORDER BY decision_time DESC LIMIT 1\")).scalar_one_or_none(); "
        "print(r.timestamp() if r else 0); s.close()")
    latest = float(run(compose(override)+['exec','-T','app','python','-c',program],timeout=15))
    return started<=latest<=time.time()+5 and time.time()-latest<=180


def wait_health(selected, override, started, seconds=480):
    deadline = time.monotonic()+seconds
    while time.monotonic()<deadline:
        try:
            if healthy(selected,override,started):
                return True
        except Exception:  # noqa: BLE001,S110 - health failure never publishes env or command output
            pass
        time.sleep(10)
    return False


def update():
    status = {'schema_version':1,'status':'checking','stage':'preflight',
              'updated_at_utc':datetime.now(UTC).isoformat()}
    previous = None
    images = None
    switched = False
    def report(state, stage):
        status.update(status=state,stage=stage,updated_at_utc=datetime.now(UTC).isoformat())
        write_json(STATUS/'status.json',status)
    try:
        existing = STATUS/'status.json'
        if existing.exists() and json.loads(existing.read_text()).get('status')=='deploying':
            record = json.loads(existing.read_text())
            old = record.get('previous_revision','')
            target = record.get('candidate_revision','')
            restored = record.get('previous_images',{})
            if (not SHA.fullmatch(old) or not SHA.fullmatch(target) or not restored
                or any(key not in ('app','auditor','report-export') or not IMAGE.fullmatch(value)
                       for key,value in restored.items())):
                return 1
            if (run(['git','status','--porcelain','--untracked-files=no'])
                or run(['git','branch','--show-current'])!='main'
                or run(['git','remote','get-url','origin']) not in (ORIGIN,ORIGIN.removesuffix('.git'))
                or run(['git','rev-parse','HEAD']) not in (old,target)):
                return 1  # do not overwrite an operator's concurrent changes
            status.update(previous_revision=old,candidate_revision=target,previous_images=restored)
            previous,images,switched = old,restored,True
            raise UpdateError('interrupted_deployment_requires_operator')  # common rollback path
        report('checking','preflight')
        if run(['git','remote','get-url','origin']) not in (ORIGIN,ORIGIN.removesuffix('.git')):
            raise UpdateError('unexpected_repository')
        if run(['git','branch','--show-current'])!='main' or run(['git','status','--porcelain','--untracked-files=no']):
            raise UpdateError('repository_not_clean_main')
        if shutil.disk_usage(REPO).free<8_000_000_000:
            raise UpdateError('insufficient_build_space')
        previous = run(['git','rev-parse','HEAD'])
        run(['git','fetch','--no-tags','origin','main'],timeout=60)
        candidate = run(['git','rev-parse','FETCH_HEAD'])
        if not SHA.fullmatch(candidate) or not SHA.fullmatch(previous):
            raise UpdateError('invalid_revision')
        status.update(candidate_revision=candidate,previous_revision=previous)
        saved = STATUS/'last-success.json'
        if saved.exists() and json.loads(saved.read_text()).get('revision')==candidate:
            report('up_to_date','done')
            return 0
        failed = STATUS/'failed-release.json'
        if failed.exists() and json.loads(failed.read_text()).get('revision')==candidate:
            report('blocked','failed_release')
            return 1
        if not check_ci(candidate):
            report('waiting_for_ci','ci')
            return 0
        run(['git','merge-base','--is-ancestor',previous,candidate])
        changed = run(['git','diff','--name-only',previous,candidate]).splitlines()
        policy(run(['git','show',candidate+':deploy/auto-release.json']),changed)
        selected = services()
        images = previous_images(selected)
        status['previous_images'] = images
        report('deploying','checkout')
        run(['git','merge','--ff-only',candidate])
        switched = True
        tag = 'btc-signal:auto-'+candidate
        report('deploying','build')
        build_image(tag,STATUS/'build-compose.json')
        if shutil.disk_usage(REPO).free<5_000_000_000:
            raise UpdateError('insufficient_runtime_space')
        override = STATUS/'runtime-compose.json'
        write_json(override,{'services':{name:{'image':tag} for name in selected}})
        report('deploying','restart')
        started = time.time()
        run(compose(override)+['up','-d','--no-deps','--force-recreate',*selected],timeout=150)
        report('deploying','health')
        if not wait_health(selected,override,started):
            raise UpdateError('health_check_failed')
        # Refresh only this already installed updater after a validated deployment.
        if INSTALLED.exists():
            try:
                descriptor,temporary = tempfile.mkstemp(dir=INSTALLED.parent,prefix='.btc-updater-')
                try:
                    with os.fdopen(descriptor,'wb') as stream:
                        stream.write((REPO/'deploy/auto-update.py').read_bytes())
                        stream.flush()
                        os.fsync(stream.fileno())
                    os.chmod(temporary,0o755)
                    os.replace(temporary,INSTALLED)
                finally:
                    if os.path.exists(temporary):
                        os.unlink(temporary)
            except OSError:
                status['housekeeping_failed'] = True
        # Remove only unused updater-managed images; preserve current and rollback images.
        protected = set(images.values())
        try:
            protected.add(run(['docker','image','inspect','--format','{{.Id}}',tag]))
            for identity in set(run(['docker','image','ls','--filter','label=org.btc-signal.auto-managed=true',
                                     '--format','{{.ID}}','--no-trunc']).splitlines()):
                if identity and identity not in protected:
                    try:
                        run(['docker','image','rm',identity])  # no force; Docker protects in-use images
                    except UpdateError:
                        pass
        except Exception:  # noqa: BLE001 - housekeeping never undoes a healthy deployment
            status['housekeeping_failed'] = True
        write_json(STATUS/'last-success.json',{'revision':candidate})
        report('deployed','done')
        return 0
    except Exception as error:  # noqa: BLE001 - rollback boundary never exports exception bodies
        status['error_type'] = type(error).__name__
        if isinstance(error,UpdateError) and str(error) in REASONS:
            status['reason'] = str(error)
        if switched and previous and images:
            write_json(STATUS/'failed-release.json',{'revision':status['candidate_revision']})
            try:
                run(['git','reset','--hard',previous])  # clean managed checkout only; ignored secrets untouched
                override = STATUS/'runtime-compose.json'
                write_json(override,{'services':{name:{'image':image} for name,image in images.items()}})
                started = time.time()
                run(compose(override)+['up','-d','--no-deps','--force-recreate',*images],timeout=150)
                report('rolled_back' if wait_health(list(images),override,started) else 'rollback_failed','rollback')
            except Exception:  # noqa: BLE001 - rollback failure is an explicit operational state
                report('rollback_failed','rollback')
        else:
            report('blocked',status['stage'])
        return 1


def main():
    if os.geteuid()!=0:
        return 1
    STATUS.mkdir(mode=0o755,parents=True,exist_ok=True)
    with (STATUS/'update.lock').open('a') as lock:
        try:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            return 0
        return update()


if __name__=='__main__':
    raise SystemExit(main())
