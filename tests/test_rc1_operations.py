"""Exercise isolated fault recovery without changing real public artifacts."""
import pytest
from ml.rc1_operations import assert_manual_trigger, run, workflow_contract


def test_operational_faults_recovery_and_boundaries():
    result = run()
    assert result['passed_checks'] == 15
    assert not result['real_source_requests'] and not result['real_publication_writes']
    assert not result['scheduled_execution_enabled']
    assert all(row['passed'] for row in result['checks'])
    pair = next(row for row in result['checks'] if row['name'].startswith('partial_pair'))
    assert pair['cross_file_atomic'] is False


def test_only_reviewed_manual_workflow_is_active():
    workflows = workflow_contract()
    assert [row['file'] for row in workflows if row['active_manual_only']] == ['.github/workflows/ci.yml']


@pytest.mark.parametrize('trigger', [
    'on: {workflow_dispatch: null, push: null}\n',
    'on:\n  workflow_dispatch:\n  push:\n',
    'on:\n  workflow_dispatch:\non:\n  push:\n',
    'on:\n  workflow_dispatch:\non : [push]\n',
    'on:\n  workflow_dispatch:\n"on" : [push]\n',
    'on:\n  workflow_dispatch:\n  schedule:\n    - cron: 0 * * * *\n',
    'on: &events\n  workflow_dispatch:\n',
    '"on":\n  workflow_dispatch:\n',
])
def test_trigger_contract_rejects_extra_or_unsupported_yaml_forms(trigger):
    with pytest.raises(AssertionError): assert_manual_trigger(trigger)
