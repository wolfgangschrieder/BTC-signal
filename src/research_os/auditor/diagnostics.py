"""Allowlisted validation diagnostics; never provider values/messages/extra names."""
from pydantic import ValidationError

FIELDS = frozenset(('verdict','comment','comment_evidence_ids','findings','task_results',
    'kind','topic','severity','statement','evidence_ids','verification','task_id','status',
    'conclusion','next_check'))
TYPES = frozenset(('missing','extra_forbidden','string_too_long','string_too_short',
    'too_long','too_short','literal_error','string_type','list_type','model_type',
    'dict_type','value_error','json_invalid'))


def failure_diagnostic(error):
    if not isinstance(error,ValidationError):
        return type(error).__name__[:96]
    issues = []
    for item in error.errors(include_url=False,include_context=False,include_input=False)[:3]:
        path = '.'.join(str(part) if type(part) is int and 0<=part<100 else
                        part if type(part) is str and part in FIELDS else 'unknown'
                        for part in item['loc']) or 'root'
        code = item['type'] if item['type'] in TYPES else 'validation_error'
        issues.append(path+':'+code)
    return ('ValidationError '+';'.join(issues))[:96]
