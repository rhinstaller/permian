import unittest
from unittest.mock import patch, call
from tplib import library
from libpermian.settings import Settings
from libpermian.events.base import Event
from libpermian.result import Result
from libpermian.caserunconfiguration import CaseRunConfiguration, CaseRunConfigurationsList
from libpermian.issueanalyzer.proxy import IssueAnalyzerProxy
from libpermian.plugins.stdout import stdoutReportSender


class CustomReportingData():
    type = 'stdout'
    submit_issues = False
    data = {}

    @classmethod
    def __iter__(cls):
        return {'data': cls.data}.__iter__()

class DummyWorkflow():
    def groupDisplayStatus(self, crcid):
        return 'testing'

class DummyTestCase():
    name = 'Dummy test case'
    id = name
    _data = {}
    _name = 'Dummy test case'
    #workflow = DummyWorkflow()


def update_result(report_sender, crc, result):
    crcUpdate = crc.copy()
    crcUpdate.result = result
    report_sender.resultUpdate(crcUpdate)


class TestStdoutReportSender(unittest.TestCase):
    def setUp(self):
        self.reporting = CustomReportingData()
        self.settings = Settings(cmdline_overrides={'stdout': {'throttleInterval': '0'}},
                                 environment={},
                                 settings_locations=[])
        self.library = library.Library('tests/test_library')
        self.crc = CaseRunConfiguration(DummyTestCase(), {'test': '1'}, [self.library.testplans['testplan 1']])
        self.crc.workflow = DummyWorkflow()
        self.caseRunConfigurations = CaseRunConfigurationsList([self.crc])


    @patch('libpermian.plugins.stdout.LOGGER')
    def test_reporting_custom(self, logging_mock):
        testplan = self.library.testplans['testplan 1']
        report_sender = stdoutReportSender(testplan,
            self.reporting, self.caseRunConfigurations,
            Event, self.settings,
            IssueAnalyzerProxy(self.settings)
        )
        update_result(report_sender, self.crc, Result(state='not started', result=None, final=False))
        report_sender.start()
        update_result(report_sender, self.crc, Result(state='running', result=None, final=False))
        update_result(report_sender, self.crc, Result(state='complete', result='PASS', final=True))
        report_sender.join()

        not_started = call('''
+------------------------------------------------------------------------------+
| testplan 1                                                                   |
+==============================================================================+
| Dummy test case                                                              |
+----------------------------+-------------------+-----------------------------|
| 1                          | None              | not started                 |
+----------------------------+-------------------+-----------------------------+
| testing                                                                      |
+==============================================================================+''')
        running = call('''
+------------------------------------------------------------------------------+
| testplan 1                                                                   |
+==============================================================================+
| Dummy test case                                                              |
+----------------------------+-------------------+-----------------------------|
| 1                          | None              | running                     |
+----------------------------+-------------------+-----------------------------+
| testing                                                                      |
+==============================================================================+''')
        complete = call('''
+------------------------------------------------------------------------------+
| testplan 1                                                                   |
+==============================================================================+
| Dummy test case                                                              |
+----------------------------+-------------------+-----------------------------|
| 1                          | PASS              | complete                    |
+----------------------------+-------------------+-----------------------------+
| testing                                                                      |
+==============================================================================+''')

        logging_mock.info.assert_has_calls([not_started, running, complete])

