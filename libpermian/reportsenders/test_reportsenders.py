import unittest
from tplib import library
from libpermian.settings import Settings
from libpermian.reportsenders.factory import ReportSenderFactory
from libpermian.testruns import TestRuns
from libpermian.events.base import Event


class TestDefaultReportSenders(unittest.TestCase):
    def test_default(self):
        lib = library.Library('tests/test_library')
        settings = Settings(cmdline_overrides={'reportSenders': {'additional_reporting': 'library://additional_rep.yaml'}, 'testingPlugin': {'reportSenderDirectory': '.'}}, environment={}, settings_locations=[])
        event = Event(settings, 'test', other={'tests': ['test1', 'test2']})
        testruns = TestRuns(lib, event, settings)

        expected = [('testplan 1', 'test', {'template': 'email template\n'}),
                    ('testplan 1', 'test', {'test': 'from-defaults'}),
                    ('testplan 2', 'undefined', {'template': 'email template\n'}),
                    ('testplan 2', 'test', {'test': 'from-defaults'})]

        self.assertCountEqual(expected, [ (rs.testplan.name, rs.reporting.type, rs.reporting.data) for rs in testruns.reportSenders ])
