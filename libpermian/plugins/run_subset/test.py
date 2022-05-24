import json
import unittest
from unittest.mock import patch, create_autospec, MagicMock

from tplib.library import Library

from libpermian.caserunconfiguration import CaseRunConfigurationsList
from libpermian.cli.factory import CliFactory
from libpermian.events.factory import EventFactory
from libpermian.settings import Settings

class TestEventOptions(unittest.TestCase):
    def test_no_args(self):
        _, event_spec = CliFactory.parse('run_subset', ['demo'])
        self.assertEqual(
            event_spec,
            json.dumps({
                'type' : 'run_subset',
                'run_subset' : {
                    'event': {'type': 'demo'},
                    'testplans': None,
                    'testplans_queries': None,
                    'testcases': None,
                    'testcases_queries': None,
                    'configurations': None,
                    'crc_queries': None,
                    'display_name': None,
                }
            })
        )

    def test_all_args(self):
        _, event_spec = CliFactory.parse(
            'run_subset',
            [
                '--testplan', 'somePlan',
                '--testplan-query', 'somePlanQuery',
                '--testcase', 'someTestCase',
                '--testcase-query', 'someTestCaseQuery',
                '--configuration', 'some:configuration',
                '--crc-query', 'someCrcQuery',
                'demo',
            ]
        )
        self.assertEqual(
            event_spec,
            json.dumps({
                'type' : 'run_subset',
                'run_subset' : {
                    'event': {'type': 'demo'},
                    'testplans': ['somePlan'],
                    'testplans_queries': ['somePlanQuery'],
                    'testcases': ['someTestCase'],
                    'testcases_queries': ['someTestCaseQuery'],
                    'configurations': [{'some':'configuration'}],
                    'crc_queries': ['someCrcQuery'],
                    'display_name': None,
                }
            })
        )

    def test_all_args_multiple(self):
        _, event_spec = CliFactory.parse(
            'run_subset',
            [
                '--testplan', 'somePlan',
                '--testplan', 'anotherPlan',
                '--testplan-query', 'somePlanQuery',
                '--testplan-query', 'anotherPlanQuery',
                '--testcase', 'someTestCase',
                '--testcase', 'anotherTestCase',
                '--testcase-query', 'someTestCaseQuery',
                '--testcase-query', 'anotherTestCaseQuery',
                '--configuration', 'some:configuration',
                '--configuration', 'another:configuration',
                '--crc-query', 'someCrcQuery',
                '--crc-query', 'anotherCrcQuery',
                'demo',
            ]
        )
        self.assertEqual(
            event_spec,
            json.dumps({
                'type' : 'run_subset',
                'run_subset' : {
                    'event': {'type': 'demo'},
                    'testplans': ['somePlan', 'anotherPlan'],
                    'testplans_queries': ['somePlanQuery', 'anotherPlanQuery'],
                    'testcases': ['someTestCase', 'anotherTestCase'],
                    'testcases_queries': [
                        'someTestCaseQuery',
                        'anotherTestCaseQuery'
                    ],
                    'configurations': [
                        {'some': 'configuration'},
                        {'another': 'configuration'}
                    ],
                    'crc_queries': ['someCrcQuery', 'anotherCrcQuery'],
                    'display_name': None,
                }
            })
        )

    def test_configurations(self):
        _, event_spec = CliFactory.parse(
            'run_subset',
            [
                '--configuration', 'single:configuration',
                '--configuration', 'one:1,two:2,three:3',
                'demo',
            ]
        )
        self.assertEqual(
            event_spec,
            json.dumps({
                'type' : 'run_subset',
                'run_subset' : {
                    'event': {'type': 'demo'},
                    'testplans': None,
                    'testplans_queries': None,
                    'testcases': None,
                    'testcases_queries': None,
                    'configurations': [
                        {'single': 'configuration'},
                        {
                            'one': '1',
                            'two': '2',
                            'three': '3',
                        }
                    ],
                    'crc_queries': None,
                    'display_name': None,
                }
            })
        )

class TestSubsets(unittest.TestCase):
    def setUp(self):
        self.settings = Settings(
            cmdline_overrides={},
            environment={},
            settings_locations=[],
        )
        self.library = Library('./tests/test_library/')
        self.original_event = EventFactory.make(
            self.settings,
            CliFactory.parse('demo', [])[1]
        )
        self.original_crcList = self.original_event.generate_caseRunConfigurations(self.library)
        # Make sure the original plan contains expected reference data
        self.assertCountEqual(
            self.original_crcList.by_testplan().keys(),
            [
                'demonstration plan 1',
                'demonstration plan 2',
                'demonstration plan 3'
            ]
        )
        self.original_by_arch = self.original_crcList.by_key(
            lambda crc: crc.configuration.get('architecture')
        )
        self.original_by_archvar = self.original_crcList.by_key(
            lambda crc: (
                crc.configuration.get('architecture'),
                crc.configuration.get('variant')
            )
        )


    def test_unchanged(self):
        
        event = EventFactory.make(
            self.settings,
            CliFactory.parse('run_subset', ['demo'])[1]
        )
        self.assertEqual(
            event.generate_caseRunConfigurations(self.library),
            self.original_crcList,
        )

    def test_testplans(self):
        tp1 = 'demonstration plan 2'
        tp2 = 'demonstration plan 3'
        args = [
            '--testplan', tp1,
            '--testplan', tp2,
            'demo'
        ]
        event = EventFactory.make(
            self.settings,
            CliFactory.parse('run_subset', args)[1]
        )
        crcList = event.generate_caseRunConfigurations(self.library)
        # check there are only crcIds from selected plans
        # use sets as one crc can me in multiple testplans
        self.assertCountEqual(
            set(crcList.ids),
            {
                crc.id
                for crc
                in self.original_crcList.by_testplan()[tp1] +
                self.original_crcList.by_testplan()[tp2]
            }
        )
        # check the crcIds are executed only for those plans
        self.assertCountEqual(
            crcList.by_testplan().keys(),
            [tp1, tp2]
        )

    def test_testcases(self):
        tc1 = 'BLS / grubby / remove entry'
        tc2 = 'NVDIMM / automated kickstart installation with NVDIMM'
        args = [
            '--testcase', tc1,
            '--testcase', tc2,
            'demo'
        ]
        event = EventFactory.make(
            self.settings,
            CliFactory.parse('run_subset', args)[1]
        )
        crcList = event.generate_caseRunConfigurations(self.library)
        self.assertCountEqual(
            crcList.by_testcase(),
            [tc1, tc2]
        )

    def test_testcases_testplans(self):
        tp1 = 'demonstration plan 2'
        tp2 = 'demonstration plan 3'
        other_tp = 'demonstration plan 1'
        tc1 = 'BLS / grubby / remove entry' # present in tp1 and other_tp
        tc2 = 'grub2 / bootonce' # present only in tp1
        tc3 = 'NVDIMM / automated kickstart installation with NVDIMM' # present int tp1 and tp2
        other_tc = 'partitioning / ext4 / root' # present in other_tp
        args = [
            '--testplan', tp1,
            '--testplan', tp2,
            '--testcase', tc1,
            '--testcase', tc2,
            '--testcase', tc3,
            '--testcase', other_tc,
            'demo'
        ]
        event = EventFactory.make(
            self.settings,
            CliFactory.parse('run_subset', args)[1]
        )
        crcList = event.generate_caseRunConfigurations(self.library)
        self.assertCountEqual(
            crcList.by_testcase(),
            [tc1, tc2, tc3]
        )
        # check only tp1 and tp2 are considered and not other_tp
        self.assertCountEqual(
            crcList.by_testplan(),
            [tp1, tp2]
        )

    def test_testplans_query(self):
        tp1 = 'demonstration plan 1'
        args = [
            '--testplan-query', f'tp.name == "{tp1}"',
            'demo'
        ]
        event = EventFactory.make(
            self.settings,
            CliFactory.parse('run_subset', args)[1]
        )
        crcList = event.generate_caseRunConfigurations(self.library)
        # check there are only crcIds from selected plans
        # use sets as one crc can me in multiple testplans
        self.assertCountEqual(
            set(crcList.ids),
            {
                crc.id
                for crc
                in self.original_crcList.by_testplan()[tp1]
            }
        )
        # Check the testcases are executed only for tp1
        self.assertCountEqual(
            crcList.by_testplan(),
            [tp1]
        )

    def test_testcases_query(self):
        tc1 = 'grub2 / bootonce' # present only in tp1
        args = [
            '--testcase-query', f'tc.name == "{tc1}"',
            'demo'
        ]
        event = EventFactory.make(
            self.settings,
            CliFactory.parse('run_subset', args)[1]
        )
        crcList = event.generate_caseRunConfigurations(self.library)
        # Check only tc1 is preset
        self.assertCountEqual(
            crcList.by_testcase().keys(),
            [tc1],
        )
        # Check all configurations of tc1 are present
        self.assertCountEqual(
            crcList.by_testcase()[tc1],
            self.original_crcList.by_testcase()[tc1],
        )

    def test_configuration(self):
        args = [
            '--configuration', 'architecture:x86_64',
            'demo'
        ]
        event = EventFactory.make(
            self.settings,
            CliFactory.parse('run_subset', args)[1]
        )
        crcList = event.generate_caseRunConfigurations(self.library)
        self.assertCountEqual(
            crcList,
            self.original_by_arch['x86_64'],
        )

    def test_configuration_combination(self):
        args = [
            '--configuration', 'architecture:x86_64,variant:BaseOS',
            'demo'
        ]
        event = EventFactory.make(
            self.settings,
            CliFactory.parse('run_subset', args)[1]
        )
        crcList = event.generate_caseRunConfigurations(self.library)
        self.assertCountEqual(
            crcList,
            self.original_by_archvar['x86_64', 'BaseOS'],
        )

    def test_configurations(self):
        args = [
            '--configuration', 'architecture:x86_64',
            '--configuration', 'architecture:s390x',
            'demo'
        ]
        event = EventFactory.make(
            self.settings,
            CliFactory.parse('run_subset', args)[1]
        )
        crcList = event.generate_caseRunConfigurations(self.library)
        self.assertCountEqual(
            crcList,
            self.original_by_arch['x86_64'] +
            self.original_by_arch['s390x']
        )

    def test_configurations_combinations(self):
        args = [
            '--configuration', 'architecture:x86_64,variant:BaseOS',
            '--configuration', 'architecture:s390x,variant:AppStream',
            'demo'
        ]
        event = EventFactory.make(
            self.settings,
            CliFactory.parse('run_subset', args)[1]
        )
        crcList = event.generate_caseRunConfigurations(self.library)
        self.assertCountEqual(
            crcList,
            self.original_by_archvar['x86_64', 'BaseOS'] +
            self.original_by_archvar['s390x', 'AppStream']
        )

    def test_crc_query(self):
        args = [
            '--crc-query', 'crc.configuration.get("architecture") == "x86_64"',
            'demo'
        ]
        event = EventFactory.make(
            self.settings,
            CliFactory.parse('run_subset', args)[1]
        )
        crcList = event.generate_caseRunConfigurations(self.library)
        self.assertCountEqual(
            crcList,
            self.original_by_arch['x86_64']
        )

    def test_crc_queries(self):
        args = [
            '--crc-query', 'crc.configuration.get("architecture") == "x86_64"',
            '--crc-query', 'crc.configuration.get("architecture") == "s390x"',
            'demo'
        ]
        event = EventFactory.make(
            self.settings,
            CliFactory.parse('run_subset', args)[1]
        )
        crcList = event.generate_caseRunConfigurations(self.library)
        self.assertCountEqual(
            crcList,
            self.original_by_arch['x86_64'] +
            self.original_by_arch['s390x']
        )
