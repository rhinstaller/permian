import unittest
from unittest.mock import Mock, patch
from libpermian.plugins.beaker_tag import BeakerTagReportSender
from libpermian.settings import Settings
from libpermian.caserunconfiguration import CaseRunConfiguration, CaseRunConfigurationsList
from libpermian.result import Result
from libpermian.issueanalyzer.proxy import IssueAnalyzerProxy
from tplib import library


class DummyTestCase():
    name = 'testing plugin case 2'
    id = name

class DummyCompose():
    id = 'RHEL2-20310314'
    nightly = True

class DummyEvent1():
    compose = DummyCompose()
    type = 'compose'

class DummyEvent2():
    compose = DummyCompose()
    type = 'component'


class TestBeakerTagReportSender(unittest.TestCase):
    def setUp(self):
        #self.reporting = DummyReportingData1()
        self.settings = Settings(cmdline_overrides={'reportSenders': {'dry_run': True}},
                                 environment={},
                                 settings_locations=[])
        self.settings_not_dry = Settings(cmdline_overrides={},
                                         environment={},
                                         settings_locations=[])
        self.library = library.Library('tests/test_library')
        self.crc = CaseRunConfiguration(DummyTestCase(), {}, [self.library.testplans['Beaker tag testplan 1']])
        self.caseRunConfigurations = CaseRunConfigurationsList([self.crc])

    def test_dryrun_minimal(self):
        with self.assertLogs('libpermian.plugins.beaker_tag', level='INFO') as cm:
            self.report_sender = BeakerTagReportSender(self.library.testplans['Beaker tag testplan 2'],
                                                       self.library.testplans['Beaker tag testplan 2'].reporting[0],
                                                       self.caseRunConfigurations,
                                                       DummyEvent1(),
                                                       self.settings,
                                                       IssueAnalyzerProxy(self.settings),
                                                       )
            crcUpdate = self.crc.copy()
            crcUpdate.result = Result(state='complete', result='PASS', final=True)
            self.assertTrue(self.report_sender.resultUpdate(crcUpdate))
        
            self.report_sender.start()
            self.report_sender.join()

        self.assertEqual(cm.output, ['INFO:libpermian.plugins.beaker_tag:Setting tag ACCEPTED to compose RHEL2-20310314'])

    @patch('libpermian.plugins.beaker_tag.xmlrpc_server')
    def test_minimal(self, xmlrpc_server_mock):
        bkr_mock = Mock()
        xmlrpc_server_mock.return_value = bkr_mock

        with self.assertLogs('libpermian.plugins.beaker_tag', level='DEBUG') as cm:
            self.report_sender = BeakerTagReportSender(self.library.testplans['Beaker tag testplan 2'],
                                                       self.library.testplans['Beaker tag testplan 2'].reporting[0],
                                                       self.caseRunConfigurations,
                                                       DummyEvent1(),
                                                       self.settings_not_dry,
                                                       IssueAnalyzerProxy(self.settings_not_dry),
                                                       )
            crcUpdate = self.crc.copy()
            crcUpdate.result = Result(state='complete', result='PASS', final=True)
            self.assertTrue(self.report_sender.resultUpdate(crcUpdate))

            self.report_sender.start()
            self.report_sender.join()

        bkr_mock.distros.tag.assert_called_once_with('RHEL2-20310314', 'ACCEPTED')
        self.assertEqual(cm.output, ['DEBUG:libpermian.plugins.beaker_tag:Successfully set tag ACCEPTED to compose RHEL2-20310314'])

    def test_dryrun_all(self):
        with self.assertLogs('libpermian.plugins.beaker_tag', level='INFO') as cm:
            self.report_sender = BeakerTagReportSender(self.library.testplans['Beaker tag testplan 1'],
                                                       self.library.testplans['Beaker tag testplan 1'].reporting[0],
                                                       self.caseRunConfigurations,
                                                       DummyEvent1(),
                                                       self.settings,
                                                       IssueAnalyzerProxy(self.settings),
                                                       )
            crcUpdate = self.crc.copy()
            crcUpdate.result = Result(state='complete', result='PASS', final=True)
            self.assertTrue(self.report_sender.resultUpdate(crcUpdate))
        
            self.report_sender.start()
            self.report_sender.join()

        self.assertEqual(cm.output, ['INFO:libpermian.plugins.beaker_tag:Setting tag NOT-FAILED-NIGHTLY to compose RHEL2-20310314'])

    def test_dryrun_no_report_1(self):
        with self.assertLogs('libpermian.plugins.beaker_tag', level='DEBUG') as cm:
            self.report_sender = BeakerTagReportSender(self.library.testplans['Beaker tag testplan 1'],
                                                       self.library.testplans['Beaker tag testplan 1'].reporting[0],
                                                       self.caseRunConfigurations,
                                                       DummyEvent1(),
                                                       self.settings,
                                                       IssueAnalyzerProxy(self.settings),
                                                       )
            crcUpdate = self.crc.copy()
            crcUpdate.result = Result(state='complete', result='FAIL', final=True)
            self.assertTrue(self.report_sender.resultUpdate(crcUpdate))
        
            self.report_sender.start()
            self.report_sender.join()

        self.assertEqual(cm.output, ['DEBUG:libpermian.plugins.beaker_tag:Not reporting: condition or report-on-results did not match'])

    def test_dryrun_no_report_2(self):
        with self.assertLogs('libpermian.plugins.beaker_tag', level='DEBUG') as cm:
            self.report_sender = BeakerTagReportSender(self.library.testplans['Beaker tag testplan 1'],
                                                       self.library.testplans['Beaker tag testplan 1'].reporting[0],
                                                       self.caseRunConfigurations,
                                                       DummyEvent2(),
                                                       self.settings,
                                                       IssueAnalyzerProxy(self.settings),
                                                       )
            crcUpdate = self.crc.copy()
            crcUpdate.result = Result(state='complete', result='PASS', final=True)
            self.assertTrue(self.report_sender.resultUpdate(crcUpdate))
        
            self.report_sender.start()
            self.report_sender.join()

        self.assertEqual(cm.output, ['DEBUG:libpermian.plugins.beaker_tag:Not reporting: condition or report-on-results did not match'])
