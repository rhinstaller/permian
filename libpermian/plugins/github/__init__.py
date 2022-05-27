import requests
import jinja2
import logging
import json
from libpermian.plugins import api
from libpermian.reportsenders.base import BaseReportSender


LOGGER = logging.getLogger(__name__)


class GitHubReportingException(Exception):
    def __init__(self, status_code, text):
        super().__init__(f'Error {status_code}, {text}')


@api.reportsenders.register('github-pr')
class GitHubPullRequestReportSender(BaseReportSender):
    """ GitHub pull request reportSender

    Reports result of a testplan as a check into a defined pull request.
    Optional reporting data (jinja2 templates):
    - pr-check-name: Name of the check in GitHub PR, testplan name by default
    - pr-check-summary: Summary of the check, testplan description by default
    - output-text: Text displayed in the check (supports Markdown), table with CRCs information by default
    All settings are required see settings.ini for details
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        github_token = self.settings.get('github', 'token')
        self.pr_id = self.settings.get('github', 'pull-request')
        self.repository = self.settings.get('github', 'repository')
        self.api_url = 'https://api.github.com'
        
        self.headers = {'Accept': 'application/vnd.github.v3+json', \
                        'Authorization': f'token {github_token}'}

        # This reporting can be used without any additional data provided
        reporting_data = self.reporting.data if self.reporting.data else dict()

        jinja_env = jinja2.Environment(loader=jinja2.BaseLoader)

        # Get check name and summary
        check_name_template = jinja_env.from_string(reporting_data.get('pr-check-name', '{{ tp.name }}'))
        self.check_name = check_name_template.render(tp=self.testplan, reportsender=self)

        check_summary_template = jinja_env.from_string(reporting_data.get('pr-check-summary', '{{ tp.description }}'))
        self.check_summary = check_summary_template.render(tp=self.testplan, reportsender=self)

        # Get check output text
        if 'output-text' in reporting_data:
            self.template = jinja_env.from_string(reporting_data.get('output-text'))
        else:
            jinja_pkg_env = jinja2.Environment(loader=jinja2.PackageLoader('libpermian.plugins.github', 'templates'))
            self.template = jinja_pkg_env.get_template('output_text.j2')

    def make_payload(self, status="in_progress", conclusion=None, head_sha=None):
        """ Makes json payload for GH check-runs API, https://docs.github.com/en/rest/checks/runs

        :param status: One of (queued, in_progress, completed), defaults to "in_progress"
        :type status: str, optional
        :param conclusion: One of (action_required, cancelled, failure, neutral, success, skipped, stale, timed_out),
            conclusion is not send if not defined, defaults to None
        :type conclusion: str, optional
        :param head_sha: SHA of a commit, head_sha is not send if not defined, defaults to None
        :type head_sha: str, optional
        :return: payload in json
        :rtype: str
        """
        output_text = self.template.render(crcs=self.caseRunConfigurations,
                                           tp=self.testplan,
                                           reportsender=self)

        payload = {"name": self.check_name,
                   "status": status,
                   "output": {"title": self.check_name,
                              "summary": self.check_summary,
                              "text": output_text
                             }
                  }

        if conclusion:
            payload['conclusion'] = conclusion
        if head_sha:
            payload['head_sha'] = head_sha

        return json.dumps(payload)

    def setUp(self):
        """ Creates new GitHub check-run and saves its ID """
        if self.dry_run:
            return

        # Get head SHA from pull request
        pr_response = requests.get(
            f'{self.api_url}/repos/{self.repository}/pulls/{self.pr_id}',
            headers=self.headers)

        if pr_response.status_code != 200:
            raise GitHubReportingException(pr_response.status_code, pr_response.text)

        head_sha = pr_response.json()['head']['sha']

        # Create new check run
        cr_response = requests.post(
            f'{self.api_url}/repos/{self.repository}/check-runs',
            data=self.make_payload('queued', head_sha=head_sha),
            headers=self.headers)

        if cr_response.status_code != 201:
            raise GitHubReportingException(cr_response.status_code, cr_response.text)

        self.check_run_id = cr_response.json()['id']

    def send_update(self, payload):
        """ Sends update to GitHub check-run

        :param payload: json payload https://docs.github.com/en/rest/checks/runs#update-a-check-run
        :type payload: str
        """
        if self.dry_run:
            LOGGER.info(f'Dry run reporting: {payload}')
            return

        cru_response = requests.patch(
            f'{self.api_url}/repos/{self.repository}/check-runs/{self.check_run_id}',
            data=payload,
            headers=self.headers)

        if cru_response.status_code != 200:
            raise GitHubReportingException(cru_response.status_code, cru_response.text)

    def processPartialResult(self, crc):
        pass

    def processFinalResult(self, crc):
        self.send_update(self.make_payload())

    def processTestRunStarted(self):
        self.send_update(self.make_payload())

    def processTestRunFinished(self):
        """ Converts the testplan result to conclusion and sends last check-run update """
        # Get conclusion
        mapping = {None: 'action_required',
                   'PASS': 'success',
                   'FAIL': 'failure',
                   'ERROR': 'failure'}

        if self.caseRunConfigurations.status == 'canceled':
            conclusion = 'cancelled'
        else:
            conclusion =  mapping[self.resultOf(self.caseRunConfigurations)]

        self.send_update(self.make_payload('completed', conclusion))

    def processCaseRunFinished(self, testCaseID):
        pass
