"""Unit tests for Testing Farm workflow plugin."""
import unittest
from unittest.mock import Mock, patch

from libpermian.events.base import Event
from libpermian.settings import Settings
from libpermian.result import Result

from . import TestingFarmWorkflow


class FakeTestCase:
    """Mock test case for testing."""
    def __init__(self):
        self.name = 'test-basic'
        self.id = 'test-basic-id'
        self.execution = Mock()
        self.execution.automation_data = {
            'test': '/test-basic',
        }


class FakeConfiguration:
    """Mock configuration for testing."""
    def __init__(self):
        self._data = {
            'variant': 'BaseOS',
            'architecture': 'x86_64',
        }

    def get(self, key, default=None):
        return self._data.get(key, default)

    def items(self):
        return self._data.items()

    def values(self):
        return self._data.values()


class FakeEvent(Event):
    """Mock event for testing."""
    def __init__(self, settings):
        super().__init__(
            settings,
            'testing_farm_test',
            compose={
                'id': 'COMP-9.8.0-20260324.7',
            }
        )


class TestTestingFarmWorkflow(unittest.TestCase):
    """Test TestingFarmWorkflow class."""

    def setUp(self):
        """Set up test fixtures."""
        self.settings = Settings(
            cmdline_overrides={
                'testingFarm': {
                    'api_url': 'https://api.testing-farm.io/v0.1',
                    'api_token': 'test-token',
                    'poll_interval': '1',
                    'default_test_repo': 'https://github.com/example/tests.git',
                    'default_test_branch': 'main',
                }
            },
            environment={},
            settings_locations=[],
        )

        self.event = FakeEvent(self.settings)
        self.testcase = FakeTestCase()
        self.configuration = FakeConfiguration()

        # Create mock CRC
        self.crc = Mock()
        self.crc.testcase = self.testcase
        self.crc.configuration = self.configuration
        self.crc.id = 'crc-test-id'
        self.crc.result = Result('not started', None, False)

        # Mock openLogfile to return a file-like context manager
        mock_file = Mock()
        mock_file.__enter__ = Mock(return_value=mock_file)
        mock_file.__exit__ = Mock(return_value=False)
        self.crc.openLogfile = Mock(return_value=mock_file)

        # Create mock TestRuns
        self.testRuns = Mock()
        self.testRuns.event = self.event
        self.testRuns.settings = self.settings

        self.crcList = [self.crc]

    def test_setup(self):
        """Test setup method builds payload correctly."""
        workflow = TestingFarmWorkflow(self.testRuns, self.crcList)

        self.testcase.execution.automation_data['env_vars'] = {
            'CUSTOM_VAR': 'custom_value',
            'TEST_PARAM_COMPOSE': 'OVERRIDE-COMPOSE'
        }

        workflow.setup()

        # Check payload structure
        self.assertIn('test', workflow.payload)
        self.assertIn('environments', workflow.payload)
        self.assertEqual(workflow.payload['test']['fmf']['url'], 'https://github.com/example/tests.git')
        self.assertEqual(workflow.payload['test']['fmf']['ref'], 'main')
        self.assertEqual(workflow.payload['test']['fmf']['test_name'], '/test-basic')

        # Check environment variables
        env_vars = workflow.payload['environments'][0]['variables']
        self.assertEqual(env_vars['CUSTOM_VAR'], 'custom_value')
        self.assertEqual(env_vars['TEST_PARAM_COMPOSE'], 'OVERRIDE-COMPOSE')
        self.assertEqual(env_vars['TEST_PARAM_VARIANT'], 'BaseOS')
        self.assertEqual(env_vars['TEST_PARAM_ARCH'], 'x86_64')

    @patch('libpermian.plugins.testing_farm.requests.post')
    def test_submit_test_success(self, mock_post):
        """Test successful test submission."""
        mock_response = Mock()
        mock_response.json.return_value = {'id': 'request-123'}
        mock_post.return_value = mock_response

        workflow = TestingFarmWorkflow(self.testRuns, self.crcList)
        workflow.setup()

        request_id = workflow.submit_test()

        self.assertEqual(request_id, 'request-123')
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        self.assertEqual(call_args[0][0], 'https://api.testing-farm.io/v0.1/requests')
        self.assertEqual(call_args[1]['headers']['Authorization'], 'Bearer test-token')
        self.assertEqual(call_args[1]['headers']['Connection'], 'close')
        self.assertEqual(call_args[1]['json'], workflow.payload)
        self.assertEqual(call_args[1]['timeout'], (10, 60))


    @patch('libpermian.plugins.testing_farm.requests.get')
    def test_get_status(self, mock_get):
        """Test getting status from Testing Farm."""
        mock_response = Mock()
        mock_response.json.return_value = {
            'state': 'running',
            'result': None,
        }
        mock_get.return_value = mock_response

        workflow = TestingFarmWorkflow(self.testRuns, self.crcList)
        workflow.request_id = 'request-123'

        status = workflow.get_status()

        self.assertEqual(status['state'], 'running')
        mock_get.assert_called_once_with(
            'https://api.testing-farm.io/v0.1/requests/request-123',
            headers={'Authorization': 'Bearer test-token', 'Connection': 'close'},
            timeout=(10, 30)
        )

    @patch('libpermian.plugins.testing_farm.requests.delete')
    def test_delete_request(self, mock_delete):
        """Test deleting a request."""
        mock_response = Mock()
        mock_delete.return_value = mock_response

        workflow = TestingFarmWorkflow(self.testRuns, self.crcList)
        workflow.request_id = 'request-123'

        workflow.delete_request()

        mock_delete.assert_called_once_with(
            'https://api.testing-farm.io/v0.1/requests/request-123',
            headers={'Authorization': 'Bearer test-token', 'Connection': 'close'},
            timeout=(10, 30)
        )

    @patch('libpermian.plugins.testing_farm.requests.get')
    def test_collect_artifacts_success(self, mock_get):
        """Test artifact collection."""
        mock_response = Mock()
        mock_response.text = '''
<testsuites overall-result="failed">
    <testsuite name="/plans/default" result="failed" tests="1" stage="complete">
        <logs>
        <log href="https://artifacts.osci.redhat.com/testing-farm/request-123/work-defaultygmiv05l/plans/default/execute/data/guest/default-0/example-test/data" name="data" schedule-entry="RHEL-9.7.0-Nightly:x86_64:/plans/default" schedule-stage="running"/>
        <log href="https://artifacts.osci.redhat.com/testing-farm/request-123/work-defaultygmiv05l/plans/default/execute/data/guest/default-0/example-test/data/Cleanup/output.txt" name="data/Cleanup/output.txt" schedule-entry="RHEL-9.7.0-Nightly:x86_64:/plans/default" schedule-stage="running"/>
        <log href="https://artifacts.osci.redhat.com/testing-farm/request-123/work-defaultygmiv05l/plans/default/execute/data/guest/default-0/example-test/data/RTT_AUTOBUG_1234abcd.ini" name="data/RTT_AUTOBUG_1234abcd.ini" schedule-entry="RHEL-9.7.0-Nightly:x86_64:/plans/default" schedule-stage="running"/>
        <log href="https://artifacts.osci.redhat.com/testing-farm/request-123/work-defaultygmiv05l/plans/default/execute/data/guest/default-0/example-test/data/Setup/output.txt" name="data/Setup/output.txt" schedule-entry="RHEL-9.7.0-Nightly:x86_64:/plans/default" schedule-stage="running"/>
        <log href="https://artifacts.osci.redhat.com/testing-farm/request-123/work-defaultygmiv05l/plans/default/execute/data/guest/default-0/example-test/data/Test/output.txt" name="data/Test/output.txt" schedule-entry="RHEL-9.7.0-Nightly:x86_64:/plans/default" schedule-stage="running"/>
        <log href="https://artifacts.osci.redhat.com/testing-farm/request-123/work-defaultygmiv05l/plans/default/execute/data/guest/default-0/example-test/failures.yaml" name="failures.yaml" schedule-entry="RHEL-9.7.0-Nightly:x86_64:/plans/default" schedule-stage="running"/>
        <log href="https://artifacts.osci.redhat.com/testing-farm/request-123/work-defaultygmiv05l/plans/default/execute/data/guest/default-0/example-test/journal.xml" name="journal.xml" schedule-entry="RHEL-9.7.0-Nightly:x86_64:/plans/default" schedule-stage="running"/>
        <log href="https://artifacts.osci.redhat.com/testing-farm/request-123/work-defaultygmiv05l/plans/default/execute/data/guest/default-0/example-test" name="log_dir" schedule-entry="RHEL-9.7.0-Nightly:x86_64:/plans/default" schedule-stage="running"/>
        <log href="https://artifacts.osci.redhat.com/testing-farm/request-123/work-defaultygmiv05l/plans/default/execute/data/guest/default-0/example-test/output.txt" name="testout.log" schedule-entry="RHEL-9.7.0-Nightly:x86_64:/plans/default" schedule-stage="running"/>
        </logs>
    </testsuite>
</testsuites>
        '''
        mock_get.return_value = mock_response

        workflow = TestingFarmWorkflow(self.testRuns, self.crcList)
        workflow.addLog = Mock()

        workflow.collect_artifacts('https://artifacts.testing-farm.io/request-123')

        # Check that logs were added
        calls = workflow.addLog.call_args_list
        self.assertEqual(len(calls), 7)

        # Check that data/ prefix is stripped
        log_names = [call[0][0] for call in calls]
        self.assertIn('RTT_AUTOBUG_1234abcd.ini', log_names)  # data/ prefix stripped
        self.assertIn('Setup/output.txt', log_names)
        self.assertIn('Test/output.txt', log_names)
        self.assertIn('Cleanup/output.txt', log_names)
        self.assertIn('failures.yaml', log_names)
        self.assertIn('journal.xml', log_names)
        self.assertIn('testout.log', log_names)

    def test_dry_execute(self):
        """Test dry execution mode."""
        workflow = TestingFarmWorkflow(self.testRuns, self.crcList)
        workflow.setup()

        with patch('libpermian.plugins.testing_farm.LOGGER') as mock_logger:
            workflow.dry_execute()

            # Check that info was logged
            mock_logger.info.assert_called_once()
            logged_message = mock_logger.info.call_args[0][0]
            self.assertIn('DRY RUN', logged_message)
            self.assertIn(workflow.api_url, logged_message)

    @patch('libpermian.plugins.testing_farm.time.sleep')
    @patch('libpermian.plugins.testing_farm.requests.get')
    @patch('libpermian.plugins.testing_farm.requests.post')
    def test_execute(self, mock_post, mock_get, mock_sleep):
        """Test execute with full state transitions: new → queued → running → complete (passed)."""
        # Mock submit_test response
        mock_post_response = Mock()
        mock_post_response.json.return_value = {'id': 'request-123'}
        mock_post.return_value = mock_post_response

        # Mock status responses - simulate state transitions
        status_responses = [
            {'state': 'new', 'result': None,'notes': [], 'run': {}},
            {'state': 'queued', 'result': None,'notes': [], 'run': {}},
            {'state': 'running', 'result': None,'notes': [], 'run': {}},
            {'state': 'running', 'result': None,'notes': [{"level": "info", "message": "http://testing-farm.example.com/request-123"}], 'run': {}},
            {'state': 'running', 'result': None, 'notes': [{"level": "info", "message": "http://testing-farm.example.com/request-123"}], 'run': {'artifacts': 'https://artifacts.example.com/123'}},
            {'state': 'complete', 'result': {'overall': 'passed', 'xunit_url': 'https://artifacts.example.com/123/xunit.xml'}, 'notes': [{"level": "info", "message": "http://testing-farm.example.com/request-123"}], 'run': {'artifacts': 'https://artifacts.example.com/123'}},
        ]

        mock_get_responses = []
        for status in status_responses:
            mock_response = Mock()
            mock_response.json.return_value = status
            mock_get_responses.append(mock_response)

        # For artifacts collection
        artifacts_response = Mock()
        artifacts_response.text = '<log href="test.log" name="test.log" />'
        mock_get_responses.append(artifacts_response)

        mock_get.side_effect = mock_get_responses

        workflow = TestingFarmWorkflow(self.testRuns, self.crcList)
        workflow.setup()

        # Track reportResult calls
        original_reportResult = workflow.reportResult
        reportResult_calls = []

        def track_reportResult(result):
            reportResult_calls.append((result.state, result.result))
            self.crc.result = result

        workflow.reportResult = track_reportResult

        # Execute workflow
        workflow.execute()

        # Verify submit was called
        self.assertEqual(mock_post.call_count, 1)

        # Verify status was polled 5 times
        self.assertEqual(mock_get.call_count, 7)  # 5 status checks + 1 artifact collection

        # Check that the request_id was set
        self.assertEqual(workflow.request_id, 'request-123')
        self.assertEqual(workflow.weblink, 'https://artifacts.example.com/123')

        # Verify the result was updated only when needed and final result is PASS
        self.assertEqual(reportResult_calls, [('queued', None), ('running', None), ('complete', 'PASS')])

if __name__ == '__main__':
    unittest.main()
