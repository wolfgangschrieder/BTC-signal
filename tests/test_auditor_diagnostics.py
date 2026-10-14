import pytest
from pydantic import ValidationError

from research_os.auditor.diagnostics import failure_diagnostic, safe_validation_diagnostic
from research_os.auditor.models import AnalystReport


def test_field_and_type_without_provider_text():
    with pytest.raises(ValidationError) as error:
        AnalystReport.model_validate({'verdict':'provider-private-value',
            'comment':'x','comment_evidence_ids':['sample.states'],'unexpected-secret-key':'private'})
    diagnostic = failure_diagnostic(error.value)
    assert 'verdict:literal_error' in diagnostic and 'unknown:extra_forbidden' in diagnostic
    assert 'private' not in diagnostic and 'unexpected-secret' not in diagnostic
    assert len(diagnostic)<=96


def test_generic_failure_does_not_include_exception_message():
    assert failure_diagnostic(ValueError('secret'))=='ValueError'


def test_multiple_nested_errors_survive_storage_and_export_without_truncated_issue():
    with pytest.raises(ValidationError) as error:
        AnalystReport.model_validate({'verdict': 'needs_review', 'comment': 'x',
            'comment_evidence_ids': ['sample.states'], 'findings': [{
                'kind': 'finding', 'topic': 'other', 'severity': 'low',
                'statement': 123, 'evidence_ids': 123, 'verification': 123}]})
    diagnostic = failure_diagnostic(error.value)
    assert diagnostic == ('ValidationError findings.0.statement:string_type;'
                          'findings.0.evidence_ids:list_type')
    assert safe_validation_diagnostic(diagnostic) == diagnostic
    assert len(diagnostic) <= 96


def test_historical_truncation_recovers_only_complete_allowlisted_prefix():
    old = ('ValidationError findings.0.statement:string_type;'
           'findings.0.evidence_ids:list_type;findings.0.verification:string_type')[:96]
    assert safe_validation_diagnostic(old) == (
        'ValidationError findings.0.statement:string_type;findings.0.evidence_ids:list_type')


@pytest.mark.parametrize('suffix', [
    'sk-private-value:missing', 'comment:private-type', 'comment', ':missing',
    'findings.\u0661.statement:missing',
])
def test_untrusted_suffix_is_not_exported(suffix):
    assert safe_validation_diagnostic('ValidationError verdict:literal_error;' + suffix) == (
        'ValidationError verdict:literal_error')
    assert safe_validation_diagnostic('ValidationError ' + suffix) == 'ValidationError'


def test_unrecognized_pydantic_type_keeps_safe_path_and_generic_code():
    error = ValidationError.from_exception_data('Report', [{
        'type': 'int_parsing', 'loc': ('comment',), 'input': 'private-provider-value'}])
    diagnostic = failure_diagnostic(error)
    assert diagnostic == 'ValidationError comment:validation_error'
    assert safe_validation_diagnostic(diagnostic) == diagnostic
