import unittest
import tempfile
import os

from . import CaseRunConfiguration, CaseRunConfigurationsList, merge_testcase_configurations
from ..result import Result
from ..exceptions import LocalLogExistsError, RemoteLogError


class DummyTestCase():
    def __init__(self, name):
        self.name = name
        self.execution = unittest.mock.MagicMock()
        self.execution.type = 'test'
        self.id = name

class DummyTestPlan():
    def __init__(self, name):
        self.name = name
        self.id = name

class TestCaseRunConfigurationLogs(unittest.TestCase):
    def setUp(self):
        self.logsdir = tempfile.TemporaryDirectory(prefix="testlogs_")
        testrun = unittest.mock.MagicMock()
        testrun.settings.get.return_value = self.logsdir.name
        plan = DummyTestPlan('A')
        self.crc = CaseRunConfiguration(DummyTestCase('testcase1'), {}, [plan])
        self.crc.testrun = testrun
        self.assertEqual(os.listdir(self.logsdir.name), [])

    def tearDown(self):
        self.logsdir.cleanup()

    def testAddLog(self):
        self.assertEqual(self.crc.logs, {})
        self.crc.addLog('foo', 'bar')
        self.assertEqual(self.crc.logs, {'foo':'bar'})
        # try to change already added log
        with self.assertRaises(LocalLogExistsError) as cm:
            self.crc.addLog('foo', 'baz')
        exception = cm.exception
        self.assertEqual(exception.crcid, self.crc.id)
        self.assertEqual(exception.name, 'foo')
        self.assertEqual(exception.old_path, 'bar')
        self.assertEqual(exception.new_path, 'baz')
        self.assertEqual(self.crc.logs, {'foo':'bar'})
        # add another log
        self.crc.addLog('another', 'something')
        self.assertEqual(self.crc.logs, {'foo':'bar', 'another':'something'})
        # add remote log
        self.crc.addLog('url', 'http://example.com/')
        self.assertEqual(
            self.crc.logs,
            {'foo':'bar', 'another':'something', 'url':'http://example.com/'}
        )
        self.assertEqual(os.listdir(self.logsdir.name), [])

    def testOpenLogfileLocal(self):
        message = 'Hello!'
        with self.crc.openLogfile('foo', 'w') as logfile:
            logfile.write(message)
        # Check there's directory for the logs belonging to the crc
        self.assertEqual(
            os.listdir(self.logsdir.name),
            [self.crc.id]
        )
        # Check the logs directory belonging to the crc contains the log
        self.assertEqual(
            os.listdir(os.path.join(self.logsdir.name, self.crc.id)),
            ["foo"]
        )
        with self.crc.openLogfile('foo') as logfile:
            self.assertEqual(logfile.read(), message)
        with open(os.path.join(self.logsdir.name, self.crc.id, 'foo')) as direct_logfile:
            self.assertEqual(direct_logfile.read(), message)

    def testOpenLogfileLocalWithFilename(self):
        message = 'Hello!'
        filename = 'foo.bar.txt'
        with self.crc.openLogfile('foo', 'w', filename=filename) as logfile:
            logfile.write(message)
        # Check there's directory for the logs belonging to the crc
        self.assertEqual(
            os.listdir(self.logsdir.name),
            [self.crc.id]
        )
        # Check the logs directory belonging to the crc contains the log
        self.assertEqual(
            os.listdir(os.path.join(self.logsdir.name, self.crc.id)),
            [filename]
        )
        with self.crc.openLogfile('foo', filename=filename) as logfile:
            self.assertEqual(logfile.read(), message)
        with open(os.path.join(self.logsdir.name, self.crc.id, filename)) as direct_logfile:
            self.assertEqual(direct_logfile.read(), message)

    def testOpenLogfileLocalAdded(self):
        message = 'Hello!'
        with tempfile.NamedTemporaryFile('w+') as direct_logfile:
            direct_logfile.write(message)
            direct_logfile.flush()
            self.crc.addLog('local', direct_logfile.name)
            with self.crc.openLogfile('local') as logfile:
                self.assertEqual(logfile.read(), message)
            self.assertEqual(os.listdir(self.logsdir.name), [])

    def testOpenLogfileRemote(self):
        url = 'http://example.com/'
        self.crc.addLog('url_log', url)
        with self.assertRaises(RemoteLogError) as cm:
            self.crc.openLogfile('url_log')
        exception = cm.exception
        self.assertEqual(exception.crcid, self.crc.id)
        self.assertEqual(exception.name, 'url_log')
        self.assertEqual(exception.log_path, url)

class TestCaseRunConfigurationsList(unittest.TestCase):
    def setUp(self):
        planA = DummyTestPlan('A')
        planB = DummyTestPlan('B')

        self.crc11 = CaseRunConfiguration(DummyTestCase('testcase1'), {'conf': 1, 'a': 0}, [planA])
        self.crc11.result = Result('running', 'PASS', False)

        self.crc12 = CaseRunConfiguration(DummyTestCase('testcase1'), {'conf': 2, 'a': 0}, [planA, planB])
        self.crc12.result = Result('complete', 'FAIL', False)

        self.crc21 = CaseRunConfiguration(DummyTestCase('testcase2'), {'conf': 1, 'a': 1}, [planB])
        self.crc21.result = Result('DNF', None, False)

        self.crc23 = CaseRunConfiguration(DummyTestCase('testcase2'), {'conf': 3, 'a': 1}, [planB])
        self.crc23.result = Result('DNF', 'ERROR', False)

        self.crcList = CaseRunConfigurationsList([
            self.crc11, self.crc12,
            self.crc21, self.crc23,
        ])

    def test_append(self):
        caserun_configurations = CaseRunConfigurationsList()
        caserun_configurations.append(1)
        self.assertListEqual(caserun_configurations, [1])
        caserun_configurations.append(1)
        self.assertListEqual(caserun_configurations, [2])
        caserun_configurations.append(3)
        self.assertListEqual(caserun_configurations, [2, 3])

    def test_by_testcase(self):
        self.assertEqual(
            self.crcList.by_testcase(),
            {
                'testcase1' : CaseRunConfigurationsList([self.crc11, self.crc12]),
                'testcase2' : CaseRunConfigurationsList([self.crc21, self.crc23]),
            },
        )

    def test_by_workflowType(self):
        self.assertEqual(
            self.crcList.by_workflowType(),
            {
                'test' : self.crcList,
            },
        )

    def test_by_configuration(self):
        self.assertEqual(
            self.crcList.by_configuration('conf'),
            {
                (1,) : CaseRunConfigurationsList([self.crc11, self.crc21]),
                (2,) : CaseRunConfigurationsList([self.crc12]),
                (3,) : CaseRunConfigurationsList([self.crc23]),
            },
        )
        self.assertEqual(
            self.crcList.by_configuration('a'),
            {
                (0,) : CaseRunConfigurationsList([self.crc11, self.crc12]),
                (1,) : CaseRunConfigurationsList([self.crc21, self.crc23]),
            },
        )
        self.assertEqual(
            self.crcList.by_configuration('conf', 'a'),
            {
                (1,0) : CaseRunConfigurationsList([self.crc11]),
                (2,0) : CaseRunConfigurationsList([self.crc12]),
                (1,1) : CaseRunConfigurationsList([self.crc21]),
                (3,1) : CaseRunConfigurationsList([self.crc23]),
            },
        )

    def test_by_testplan(self):
        self.assertEqual(
            self.crcList.by_testplan(),
            {
                'A' : CaseRunConfigurationsList([self.crc11, self.crc12]),
                'B' : CaseRunConfigurationsList([self.crc12, self.crc21, self.crc23]),
            },
        )

    def test_combined(self):
        self.assertEqual(
            {
                testplan : crcList.by_testcase()
                for testplan, crcList
                in self.crcList.by_testplan().items()
            },
            {
                'A' : {
                    'testcase1' : CaseRunConfigurationsList([self.crc11, self.crc12]),
                },
                'B' : {
                    'testcase1' : CaseRunConfigurationsList([self.crc12]),
                    'testcase2' : CaseRunConfigurationsList([self.crc21, self.crc23]),
                },
            },
        )

    def test_result(self):
        self.assertEqual(self.crcList.status, 'running')
        self.assertEqual(
            {
                testcase: crcList.result
                for testcase, crcList
                in self.crcList.by_testcase().items()
            },
            {
                'testcase1' : 'FAIL',
                'testcase2' : 'ERROR',
            }
        )

    def test_status(self):
        self.assertEqual(self.crcList.result, 'ERROR')
        self.assertEqual(
            {
                testcase: crcList.status
                for testcase, crcList
                in self.crcList.by_testcase().items()
            },
            {
                'testcase1' : 'running',
                'testcase2' : 'DNF',
            }
        )

    def test_hasDirtyResult(self):
        for crc in self.crcList:
            self.assertTrue(self.crcList.hasDirtyResult)
            crc.result.dirty = False
        self.assertFalse(self.crcList.hasDirtyResult)

    def test_allResultsFinal(self):
        for crc in self.crcList:
            self.assertFalse(self.crcList.allResultsFinal)
            crc.result.final = True
        self.assertTrue(self.crcList.allResultsFinal)

    def test_ids(self):
        self.assertEqual(
            self.crcList.ids,
            [
                'a0a2e5ffb7b6b59a151fa60678401b3d9472e0ae',
                '09fb918ce6c546f144fd1fee520bc21f92c9a40f',
                '544d65aafd33895bc707a774ac99f49582e3e3d3',
                'a438f41d447d2c887cba21d0b2f2b704ec89c89a'
            ]
        )
        self.assertEqual(
            {
                testcase: crcList.ids
                for testcase, crcList
                in self.crcList.by_testcase().items()
            },
            {
                'testcase1' : [
                    'a0a2e5ffb7b6b59a151fa60678401b3d9472e0ae',
                    '09fb918ce6c546f144fd1fee520bc21f92c9a40f'
                ],
                'testcase2' : [
                    '544d65aafd33895bc707a774ac99f49582e3e3d3',
                    'a438f41d447d2c887cba21d0b2f2b704ec89c89a'
                ],
            }
        )

    def test_withDirtyResult(self):
        self.assertEqual(
            self.crcList.withDirtyResult,
            self.crcList,
        )
        self.crc12.result.dirty = False
        self.assertEqual(
            self.crcList.withDirtyResult,
            CaseRunConfigurationsList([
                self.crc11,
                self.crc21, self.crc23,
            ]),
        )
        self.crc21.result.dirty = False
        self.assertEqual(
            self.crcList.withDirtyResult,
            CaseRunConfigurationsList([
                self.crc11,
                self.crc23,
            ]),
        )

class TestMerge_testcase_configurations(unittest.TestCase):
    def setUp(self):
        self.caseRunConfigurations = [CaseRunConfiguration(DummyTestCase('testcase1'), {'conf': 1}, []),
                                      CaseRunConfiguration(DummyTestCase('testcase1'), {'conf': 2}, []),
                                      CaseRunConfiguration(DummyTestCase('testcase2'), {'conf': 3}, []),
                                      CaseRunConfiguration(DummyTestCase('testcase2'), {'conf': 4}, [])]

    def test_common_result(self):
        self.caseRunConfigurations[0].result = Result('running', 'PASS', False)
        self.caseRunConfigurations[1].result = Result('complete', 'FAIL', False)
        testcases = merge_testcase_configurations(self.caseRunConfigurations)

        self.assertEqual(testcases['testcase1']['result'].state, 'running')
        self.assertEqual(testcases['testcase1']['result'].result, 'FAIL')
        self.assertEqual(testcases['testcase2']['result'].state, 'not started')
        self.assertEqual(testcases['testcase2']['result'].result, None)
        #print()

    def test_common_workflow(self):
        testcases = merge_testcase_configurations(self.caseRunConfigurations)
        self.assertEqual(testcases['testcase1']['workflow'], 'test')

    def test_configurations(self):
        testcases = merge_testcase_configurations(self.caseRunConfigurations)
        self.assertEqual(len(testcases['testcase1']['caseRunConfigurations']), 2)
        self.assertEqual(testcases['testcase1']['caseRunConfigurations'][0].configuration['conf'], 1)
        self.assertEqual(testcases['testcase1']['caseRunConfigurations'][1].configuration['conf'], 2)
        self.assertEqual(len(testcases['testcase2']['caseRunConfigurations']), 2)
        self.assertEqual(testcases['testcase2']['caseRunConfigurations'][0].configuration['conf'], 3)
        self.assertEqual(testcases['testcase2']['caseRunConfigurations'][1].configuration['conf'], 4)
