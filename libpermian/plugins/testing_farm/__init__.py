import json
import logging
import time
import requests
import re

from .. import api
from ...workflows.isolated import IsolatedWorkflow
from libpermian.result import Result


LOGGER = logging.getLogger(__name__)

# Maps Testing Farm request states to Permian state values
state2state_map = {
    'canceled': 'canceled',
    'new': 'not started',
    'queued': 'queued',
    'running': 'running',
    'complete': 'complete',
    'error': 'DNF',
}

# Maps terminal Testing Farm states to Permian result values
state2result_map = {
    'canceled': None,
    'error': 'ERROR',
}
# Maps Testing Farm test results to Permian result values
result2result_map = {
    'passed': 'PASS',
    'failed': 'FAIL',
}


@api.workflows.register("testingFarm")
class TestingFarmWorkflow(IsolatedWorkflow):
    """
    Workflow for executing tests on Testing Farm infrastructure.
    """

    def __init__(self, testRuns, crcList):
        """
        Initialize the Testing Farm workflow.

        Loads API credentials, test configuration, and initializes tracking variables.

        Args:
            testRuns: Test run instances.
            crcList: List of case run configurations.
        """
        super().__init__(testRuns, crcList)

        self.api_url = self.settings.get('testingFarm', 'api_url')
        self.api_token = self.settings.get('testingFarm', 'api_token')
        self.poll_interval = self.settings.getint('testingFarm', 'poll_interval')
        self.max_status_retry = self.settings.getint('testingFarm', 'max_status_retry')
        default_test_repo = self.settings.get('testingFarm', 'default_test_repo')
        default_test_branch = self.settings.get('testingFarm', 'default_test_branch')

        self.test_repo = self.crc.testcase.execution.automation_data.get('test_repo', default_test_repo)
        self.test_branch = self.crc.testcase.execution.automation_data.get('test_branch', default_test_branch)
        self.tmt_test = self.crc.testcase.execution.automation_data['test']

        self.variant = self.crc.configuration.get('variant')
        self.architecture = self.crc.configuration.get('architecture')
        self.tested_compose = self.event.compose.id
        self.execution_os = self.crc.testcase.execution.automation_data.get('compose', self.tested_compose)
        self.execution_arch = self.crc.testcase.execution.automation_data.get('arch', self.architecture)

        self.provision_weblink = None
        self.weblink = None
        self.request_id = None

    def setup(self):
        """
        Build the test payload and report initial state.

        Constructs the Testing Farm API request payload with environment
        variables, test configuration, and compose information. Merges
        any custom env_vars from test metadata. Reports 'not started' state.
        """

        env_vars = {
            'TEST_PARAM_COMPOSE': self.tested_compose,
            'TEST_PARAM_VARIANT': self.variant,
            'TEST_PARAM_ARCH': self.architecture
        }
        if 'env_vars' in self.crc.testcase.execution.automation_data:
            env_vars.update(self.crc.testcase.execution.automation_data['env_vars'])

        self.payload = {
            "test": {
                "fmf": {
                    "url": self.test_repo,
                    "ref": self.test_branch,
                    "test_name": self.tmt_test
                }
            },
            "environments": [
                {
                    "arch": self.execution_arch,
                    "os": {
                        "compose": self.execution_os
                    },
                    "variables": env_vars
                }
            ]
        }

        self.reportResult(Result('not started'))

    def execute(self):
        """
        Execute the test on Testing Farm.

        Submits the test request, polls for status updates, and reports
        results. Collects artifacts when the test completes.
        """
        self.log(f'Submitting test request to Testing Farm, payload:\n{json.dumps(self.payload, indent=2)}')

        try:
            self.request_id = self.submit_test()
        except requests.HTTPError as e:
            LOGGER.error(f'Can\'t submit test {e}')
            self.reportResult(Result('not started', 'ERROR', final=True))
            return
        
        self.log(f"Test submitted. Request ID: {self.request_id}")

        status_attempts = 0
        status = dict()

        while not self.crc.result.final:
            try:
                status = self.get_status()
                status_attempts = 0
                state = status['state']
                self.log(f"Current state: {state}")

                # Try to get link to a web page with info about provisioning
                try:
                    if self.provision_weblink is None and status['notes'][0]['message'].startswith('http'):
                        self.provision_weblink = status['notes'][0]['message']
                        self.log(f'New link: {self.provision_weblink}')
                except (KeyError, IndexError, TypeError):
                    pass

                # Try to get link to a web page with info about test run
                try:
                    if self.weblink is None:
                        self.weblink = status['run']['artifacts']
                        self.log(f'New link: {self.weblink}')
                except (KeyError, IndexError, TypeError):
                    pass

                # Update result
                if state == 'complete':
                    if status['result']['overall'] in result2result_map:
                        self.reportResult(Result('complete',
                                                result2result_map[status['result']['overall']],
                                                final=True))
                        break
                    else:
                        self.reportResult(Result('complete', 'ERROR', final=True))
                        break

                elif state in ['error', 'canceled']:
                    self.reportResult(Result(state2state_map[state],
                                            state2result_map[state],
                                            final=True))
                    break

                elif state in state2state_map and self.crc.result.state != state2state_map[state]:
                    self.reportResult(Result(state2state_map[state]))

            except requests.HTTPError as e:
                LOGGER.error(f'Can\'t get test status {e}')
                status_attempts += 1
                if status_attempts == self.max_status_retry:
                    self.reportResult(Result('DNF', 'ERROR', final=True))
                    return
                
            time.sleep(self.poll_interval)

        try:
            artifacts_url = status['result'].get('xunit_url', None)
            if artifacts_url is not None:
                self.collect_artifacts(artifacts_url)
            else:
                LOGGER.warning('No xunit, can\'t collect artifacts')
        except (KeyError, AttributeError):
            LOGGER.warning('No result, can\'t collect artifacts')

    def dry_execute(self):
        """
        Simulate test execution without actually submitting to Testing Farm.

        Logs the payload that would be sent and reports a successful result.
        Used when the pipeline is in dry-run mode.
        """
        LOGGER.info(f'DRY RUN: Would request {self.api_url}/requests\n {json.dumps(self.payload, indent=2)}')
        self.reportResult(Result('complete', 'PASS', final=True))

    def terminate(self):
        """
        Cancel the running test request.

        Sends a delete request to Testing Farm API to cancel the test.
        Called asynchronously when the workflow needs to be stopped.

        Returns:
            bool: True if cancellation succeeded, False otherwise.
        """
        if self.request_id is None:
            LOGGER.warning("No request to cancel")
            return True

        try:
            self.delete_request()
            self.reportResult(Result('canceled', None, final=True))
            return True
        except requests.HTTPError as e:
            LOGGER.error(f"Test termination failed: {e}")
            self.reportResult(Result('canceled', 'ERROR', final=True))
            return False

    def displayStatus(self):
        """
        Return markdown-formatted status link for WebUI display.

        Returns:
            str: Markdown link to test run or provisioning page, or empty string.
        """
        if self.weblink is not None:
            return f'[TF testrun]({self.weblink})'
        if self.provision_weblink is not None:
            return f'[TF provisioning]({self.provision_weblink})'
        return ''

    def submit_test(self):
        """
        Submit a test request to Testing Farm API.

        Returns:
            str: Request ID assigned by Testing Farm.

        Raises:
            requests.HTTPError: If the API request fails.
        """
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_token}"
        }

        response = requests.post(
            f"{self.api_url}/requests",
            headers=headers,
            json=self.payload
        )
        response.raise_for_status()

        result = response.json()
        return result['id']

    def get_status(self):
        """
        Retrieve current status of the test request from Testing Farm.

        Returns:
            dict: Status response containing state, results, and metadata.

        Raises:
            requests.HTTPError: If the API request fails.
        """
        headers = {
            "Authorization": f"Bearer {self.api_token}"
        }

        response = requests.get(
            f"{self.api_url}/requests/{self.request_id}",
            headers=headers
        )
        response.raise_for_status()

        return response.json()

    def delete_request(self):
        """
        Send DELETE request to cancel the test on Testing Farm.

        Raises:
            requests.HTTPError: If the cancellation request fails.
        """
        headers = {
            "Authorization": f"Bearer {self.api_token}"
        }

        response = requests.delete(
            f"{self.api_url}/requests/{self.request_id}",
            headers=headers
        )
        response.raise_for_status()

    def collect_artifacts(self, artifacts_url):
        """
        Fetch and add test artifacts from Testing Farm results.

        Parses the artifacts XML/HTML listing and adds log files to the workflow.

        Args:
            artifacts_url (str): URL to the artifacts directory listing.
        """
        try:
            response = requests.get(artifacts_url)
            response.raise_for_status()
        except requests.HTTPError as e:
            LOGGER.error(f"Can\'t collect artifacts: {e}")
            return
        
        xml = response.text

        link_pattern = r'<log href="([^"]+)" name="([^"]+)" ([^<]+)/>'
        matches = re.findall(link_pattern, xml)

        for href, name, _ in matches:
            # Skip parent directory and absolute URLs
            if name in ['log_dir', 'data']:
                continue
            if name.startswith('data/'):
                name = name.split('/', 1)[1]
            self.addLog(name, href)