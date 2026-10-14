"""Allowlisted validation diagnostics; never provider values/messages/extra names."""
from pydantic import ValidationError

FIELDS = frozenset(('verdict','comment','comment_evidence_ids','findings','task_results',
    'kind','topic','severity','statement','evidence_ids','verification','task_id','status',
    'conclusion','next_check'))
TYPES = frozenset(('missing','extra_forbidden','string_too_long','string_too_short',
    'too_long','too_short','literal_error','string_type','list_type','model_type',
    'dict_type','value_error','json_invalid','validation_error'))


def _bounded_validation_issues(issues):
    diagnostic = 'ValidationError'
    for issue in issues:
        candidate = diagnostic + (' ' if diagnostic == 'ValidationError' else ';') + issue
        if len(candidate) <= 96:
            diagnostic = candidate
    return diagnostic


def safe_validation_diagnostic(value):
    """Export only complete allowlisted issues, including a safe historical prefix."""
    issues = []
    for issue in value[len('ValidationError '):].split(';')[:3]:
        path, separator, code = issue.partition(':')
        if not separator or code not in TYPES:
            break
        if any(part not in FIELDS and part not in ('root', 'unknown') and
               not (part.isascii() and part.isdigit() and len(part) <= 2)
               for part in path.split('.')):
            break
        issues.append(issue)
    # Older rows may end mid-issue after a 96-character slice. Never return that
    # fragment, but retain preceding complete safe fields for investigation.
    return _bounded_validation_issues(issues)


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
    return _bounded_validation_issues(issues)
