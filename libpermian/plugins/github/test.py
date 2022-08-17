import unittest
from unittest.mock import patch
from tplib import library
from libpermian.settings import Settings
from libpermian.events.base import Event
from libpermian.result import Result
from libpermian.caserunconfiguration import CaseRunConfiguration, CaseRunConfigurationsList
from libpermian.issueanalyzer.proxy import IssueAnalyzerProxy
from libpermian.plugins.github import GitHubPullRequestReportSender


class ResultMock200():
    status_code = 200
    text = 'error'

    @classmethod
    def json(cls):
        return {'head': {'sha': 'abc123'}}


class ResultMock201():
    status_code = 201
    text = 'error'

    @classmethod
    def json(cls):
        return {'id': '47261'}


class CustomReportingData():
    type = 'github-pr'
    submit_issues = None
    data = {'pr-check-name': 'Special check',
            'pr-check-summary': 'Summary',
            'output-text': '{{ crcs.result }}'}

    @classmethod
    def __iter__(cls):
        return {'data': cls.data}.__iter__()


class DummyTestCase():
    name = 'Dummy test case'
    id = name
    _data = {}
    _name = 'Dummy test case'


def update_result(report_sender, crc, result):
    crcUpdate = crc.copy()
    crcUpdate.result = result
    report_sender.resultUpdate(crcUpdate)


class TestGitHubPullRequestReportSender(unittest.TestCase):
    def setUp(self):
        self.reporting = CustomReportingData()
        self.settings = Settings(cmdline_overrides={'github': {'pull-request': '42',
                                                               'repository': 'user/test',
                                                               'token': '1234'}},
                                 environment={},
                                 settings_locations=[])
        self.library = library.Library('tests/test_library')
        self.crc = CaseRunConfiguration(DummyTestCase(), {'test': '1'}, [self.library.testplans['GitHub testplan 1']])
        self.caseRunConfigurations = CaseRunConfigurationsList([self.crc])

    @patch('requests.get')
    @patch('requests.post')
    @patch('requests.patch')
    def test_reporting_default(self, requests_patch, requests_post, requests_get):
        requests_get.return_value = ResultMock200()
        requests_patch.return_value = ResultMock200()
        requests_post.return_value = ResultMock201()

        testplan = self.library.testplans['GitHub testplan 1']
        report_sender = GitHubPullRequestReportSender(testplan,
            testplan.reporting[0], self.caseRunConfigurations,
            Event, self.settings,
            IssueAnalyzerProxy(self.settings)
        )
        update_result(report_sender, self.crc, Result(state='not started', result=None, final=False))
        report_sender.start()
        update_result(report_sender, self.crc, Result(state='running', result=None, final=False))
        update_result(report_sender, self.crc, Result(state='complete', result='PASS', final=True))
        report_sender.join()

        requests_get.assert_called_with('https://api.github.com/repos/user/test/pulls/42',
            headers={'Accept': 'application/vnd.github.v3+json', 'Authorization': 'token 1234'})

        requests_post.assert_called_with('https://api.github.com/repos/user/test/check-runs',
            data='{"name": "GitHub testplan 1", "status": "queued", "output": {"title": "GitHub testplan 1", "summary": "Testplan for testing github-pr report sender", "text": "| Test case | Configuration | Status | Result |\\n| --------- | ------------- | ------ | ------ |\\n| Dummy test case |test: 1, | not started | None |"}, "head_sha": "abc123"}',
            headers={'Accept': 'application/vnd.github.v3+json', 'Authorization': 'token 1234'})
        
        requests_patch.assert_called_with('https://api.github.com/repos/user/test/check-runs/47261',
            data='{"name": "GitHub testplan 1", "status": "completed", "output": {"title": "GitHub testplan 1", "summary": "Testplan for testing github-pr report sender", "text": "| Test case | Configuration | Status | Result |\\n| --------- | ------------- | ------ | ------ |\\n| Dummy test case |test: 1, | complete | PASS |"}, "conclusion": "success"}',
            headers={'Accept': 'application/vnd.github.v3+json', 'Authorization': 'token 1234'})

    @patch('requests.get')
    @patch('requests.post')
    @patch('requests.patch')
    def test_reporting_custom(self, requests_patch, requests_post, requests_get):
        requests_get.return_value = ResultMock200()
        requests_patch.return_value = ResultMock200()
        requests_post.return_value = ResultMock201()

        testplan = self.library.testplans['GitHub testplan 1']
        report_sender = GitHubPullRequestReportSender(testplan,
            self.reporting, self.caseRunConfigurations,
            Event, self.settings,
            IssueAnalyzerProxy(self.settings)
        )
        update_result(report_sender, self.crc, Result(state='not started', result=None, final=False))
        report_sender.start()
        update_result(report_sender, self.crc, Result(state='running', result=None, final=False))
        update_result(report_sender, self.crc, Result(state='complete', result='PASS', final=True))
        report_sender.join()

        requests_get.assert_called_with('https://api.github.com/repos/user/test/pulls/42',
            headers={'Accept': 'application/vnd.github.v3+json', 'Authorization': 'token 1234'})

        requests_post.assert_called_with('https://api.github.com/repos/user/test/check-runs',
            data='{"name": "Special check", "status": "queued", "output": {"title": "Special check", "summary": "Summary", "text": "None"}, "head_sha": "abc123"}',
            headers={'Accept': 'application/vnd.github.v3+json', 'Authorization': 'token 1234'})
        
        requests_patch.assert_called_with('https://api.github.com/repos/user/test/check-runs/47261',
            data='{"name": "Special check", "status": "completed", "output": {"title": "Special check", "summary": "Summary", "text": "PASS"}, "conclusion": "success"}',
            headers={'Accept': 'application/vnd.github.v3+json', 'Authorization': 'token 1234'})
