import unittest
from libpermian.settings import Settings
from libpermian.workflows.factory import WorkflowFactory
from libpermian.workflows.grouped import GroupedWorkflow
from libpermian.workflows.isolated import IsolatedWorkflow
from libpermian.workflows.builtin import UnknownWorkflow
from libpermian.result import Result
from libpermian.caserunconfiguration import CaseRunConfiguration, CaseRunConfigurationsList

class DummyTestCase():
    name = 'test'
    id = name

class TestWorkflow(IsolatedWorkflow):
    def execute(self):
        pass

    def terminate(self):
        return False

    def displayStatus(self):
        return 'Test'

class TestWorkflowFactory(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        WorkflowFactory.clear_workflow_classes()
        WorkflowFactory.register('test')(TestWorkflow)

    @classmethod
    def tearDownClass(cls):
        WorkflowFactory.restore_workflow_classes()

    def test_registered(self):
        self.assertIs(TestWorkflow, WorkflowFactory.workflow_classes['test'])

    @unittest.mock.patch('libpermian.testruns.TestRuns', autospec=True)
    def test_unknown(self, MockTestRuns):
        caseRunConfiguration = CaseRunConfiguration(DummyTestCase(), {}, [])
        testRuns = MockTestRuns(None, None, None)
        testRuns.caseRunConfigurations = CaseRunConfigurationsList(
            [caseRunConfiguration]
        )
        testRuns.__getitem__ = lambda instance, key: caseRunConfiguration if key == caseRunConfiguration.id else None
        testRuns.event = None
        testRuns.settings = Settings({}, {}, [])
        WorkflowFactory._assignWorkflows('unknown', testRuns, testRuns.caseRunConfigurations)
        self.assertIsInstance(caseRunConfiguration.workflow, UnknownWorkflow)

class SilentlyFailingWorkflow(GroupedWorkflow):
    silent_exceptions = (NotImplementedError,)
    def __init__(self, testRuns, crcList):
        super().__init__(testRuns, crcList)
        self.mocked_log = ''
    def setup(self):
        raise NotImplementedError('This is currently not supported')
    def groupLog(self, text, **kwargs):
        self.mocked_log += text
    def execute(self):
        pass
    def factory(self):
        pass
    def groupDisplayStatus(self):
        pass
    def groupTerminate(self):
        pass

class BrokenWorkflow(SilentlyFailingWorkflow):
    def setup(self):
        pass
    def execute(self):
        raise ZeroDivisionError('I\'m broken')

class TestWorkflowExceptions(unittest.TestCase):
    @unittest.mock.patch('libpermian.testruns.TestRuns', autospec=True)
    def setUp(self, MockTestRuns):
        self.crc = CaseRunConfiguration(DummyTestCase(), {}, [])
        self.mock_testrun = MockTestRuns(None, None, None)
        self.mock_testrun.caseRunConfigurations = CaseRunConfigurationsList([self.crc])
        self.mock_testrun.event = None
        self.mock_testrun.settings = Settings({}, {}, [])

    def test_silent_exception(self):
        workflow = SilentlyFailingWorkflow(self.mock_testrun, [self.crc])
        workflow.run()
        self.assertRegex(workflow.mocked_log, 'Workflow raised silent exception: This is currently not supported.')
        self.assertEqual(workflow.crcList[0].result, Result('DNF', 'ERROR', True))

    def test_exception(self):
        workflow = BrokenWorkflow(self.mock_testrun, [self.crc])
        with self.assertRaises(ZeroDivisionError):
            workflow.run()
        self.assertEqual(workflow.crcList[0].result, Result('DNF', 'ERROR', True))
