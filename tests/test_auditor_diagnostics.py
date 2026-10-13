import pytest
from pydantic import ValidationError

from research_os.auditor.diagnostics import failure_diagnostic
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
