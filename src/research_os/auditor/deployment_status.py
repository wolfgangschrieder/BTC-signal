"""Only allowlisted deployment metadata crosses the host/Drive boundary."""
import json
import os
import re
from pathlib import Path

STATES = {'checking','waiting_for_ci','up_to_date','deploying','deployed','blocked','rolled_back','rollback_failed'}
STAGES = {'preflight','ci','checkout','build','restart','health','rollback','done','failed_release'}
REASONS = {'command_failed','unsafe_status_path','ci_response_too_large','release_disabled_or_unsupported',
    'migration_requires_operator','baseline_container_missing','baseline_image_invalid','unexpected_repository',
    'repository_not_clean_main','insufficient_build_space','invalid_revision','insufficient_runtime_space',
    'health_check_failed','interrupted_deployment_requires_operator'}


def read_deployment_status():
    path = os.environ.get('DEPLOY_STATUS_PATH','')
    if not path:
        return {'status':'not_configured'}
    try:
        target = Path(path)
        if target.is_symlink():
            return {'status':'unreadable'}
        with target.open('rb') as stream:
            body = stream.read(16385)
        if len(body)>16384:
            return {'status':'unreadable'}
        data = json.loads(body)
        if data.get('status') not in STATES or data.get('stage') not in STAGES:
            return {'status':'unreadable'}
        output = {'status':data['status'],'stage':data['stage']}
        for key in ('candidate_revision','previous_revision'):
            if re.fullmatch('[a-f0-9]{40}',str(data.get(key,''))):
                output[key] = data[key]
        if data.get('reason') in REASONS:
            output['reason'] = data['reason']
        from datetime import datetime
        timestamp = datetime.fromisoformat(data['updated_at_utc'])
        if timestamp.utcoffset() is None:
            return {'status':'unreadable'}
        output['updated_at_utc'] = timestamp.isoformat()
        return output
    except FileNotFoundError:
        return {'status':'not_installed'}
    except Exception:  # noqa: BLE001 - malformed host data never stops analyst exports
        return {'status':'unreadable'}
