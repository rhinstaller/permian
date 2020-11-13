import unittest
from tclib import library
from libpipeline.settings import Settings
from libpipeline.reportsenders.factory import ReportSenderFactory
from libpipeline.testruns import TestRuns
from libpipeline.events.base import Event


class TestDefaultReportSenders(unittest.TestCase):
    def test_default(self):
        lib = library.Library('tests/test_library')
        settings = Settings(cmdline_overrides={'reportSenders': {'additional_reporting': 'library://additional_rep.yaml'}, 'testingPlugin': {'reportSenderDirectory': '.'}}, environment={}, settings_locations=[])
        event = Event('test', other={'tests': ['test1', 'test2']})
        testruns = TestRuns(lib, event, settings)

        expected = [('testplan 1', 'test', {'template': 'email template\n'}),
                    ('testplan 1', 'test', {'test': 'from-defaults'}),
                    ('testplan 2', 'undefined', {'template': 'email template\n'}),
                    ('testplan 2', 'test', {'test': 'from-defaults'})]

        self.assertCountEqual(expected, [ (rs.testplan.name, rs.reporting.type, rs.reporting.data) for rs in testruns.reportSenders ])