import unittest
from tplib import library
from libpermian.settings import Settings
from libpermian.events.base import Event
from libpermian.workflows.factory import WorkflowFactory
from libpermian.workflows.isolated import IsolatedWorkflow, GroupedWorkflow
from libpermian.workflows.builtin import UnknownWorkflow, ManualWorkflow
from libpermian.testruns import TestRuns
from libpermian.result import Result


class TestWorkflowIsolated(IsolatedWorkflow):
    def execute(self):
        pass

    def terminate(self):
        return False

    def displayStatus(self):
        return 'Test'


class TestWorkflowGroupedAll(GroupedWorkflow):
    def execute(self):
        pass

    def groupTerminate(self):
        return False

    def groupDisplayStatus(self):
        return 'Test'

    @classmethod
    def factory(cls, testRuns, crcIds):
        cls(testRuns, crcIds)


class TestWorkflowGrouped(GroupedWorkflow):
    def execute(self):
        pass

    def groupTerminate(self):
        return False

    def groupDisplayStatus(self):
        return 'Test'

    @classmethod
    def factory(cls, testRuns, crcList):
        # Split caseruns into groups by architecture
        for crcList in crcList.by_configuration('arch').values():
            cls(testRuns, crcList)


def testruns_init():
        lib = library.Library('tests/test_library')
        settings = Settings(cmdline_overrides={'library': {'defaultCaseConfigMergeMethod': 'extension'}}, environment={}, settings_locations=[])
        event = Event(settings, 'test', other={'tests': ['test_workflows']})
        return TestRuns(lib, event, settings)


class TestAssignWorkflows1(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        WorkflowFactory.clear_workflow_classes()
        WorkflowFactory.register('test_isolated')(TestWorkflowIsolated)
        WorkflowFactory.register('test_grouped')(TestWorkflowGroupedAll)
        cls.testruns = testruns_init()

    @classmethod
    def tearDownClass(cls):
        WorkflowFactory.restore_workflow_classes()

    def test_isolated(self):
        for caserun in self.testruns.caseRunConfigurations:
            if caserun.testcase.name == 'test_isolated 1':
                workflow1 = caserun.workflow
            if caserun.testcase.name == 'test_isolated 2':
                workflow2 = caserun.workflow

        self.assertIsInstance(workflow1, TestWorkflowIsolated)
        self.assertIsInstance(workflow2, TestWorkflowIsolated)
        self.assertNotEqual(workflow1, workflow2)

    def test_grouped_all(self):
        for caserun in self.testruns.caseRunConfigurations:
            if caserun.testcase.name == 'test_grouped 1':
                workflow1 = caserun.workflow
            if caserun.testcase.name == 'test_grouped 2':
                workflow2 = caserun.workflow
            if caserun.testcase.name == 'test_grouped 3':
                workflow3 = caserun.workflow

        self.assertIsInstance(workflow1, TestWorkflowGroupedAll)
        self.assertIsInstance(workflow2, TestWorkflowGroupedAll)
        self.assertIsInstance(workflow3, TestWorkflowGroupedAll)
        self.assertEqual(workflow1, workflow2)
        self.assertEqual(workflow2, workflow3)

    def test_manual(self):
        for caserun in self.testruns.caseRunConfigurations:
            if caserun.testcase.name == 'testcase 1':
                workflow = caserun.workflow

        self.assertIsInstance(workflow, ManualWorkflow)

    def test_unknown(self):
        for caserun in self.testruns.caseRunConfigurations:
            if caserun.testcase.name == 'testcase 2':
                workflow = caserun.workflow

        self.assertIsInstance(workflow, UnknownWorkflow)


class TestAssignWorkflows2(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        WorkflowFactory.clear_workflow_classes()
        WorkflowFactory.register('test_grouped')(TestWorkflowGrouped)
        cls.testruns = testruns_init()

    @classmethod
    def tearDownClass(cls):
        WorkflowFactory.restore_workflow_classes()

    def test_grouped_by_config(self):
        for caserun in self.testruns.caseRunConfigurations:
            if caserun.testcase.name == 'test_grouped 1':
                workflow1 = caserun.workflow
            if caserun.testcase.name == 'test_grouped 2':
                workflow2 = caserun.workflow
            if caserun.testcase.name == 'test_grouped 3':
                workflow3 = caserun.workflow

        self.assertIsInstance(workflow1, TestWorkflowGrouped)
        self.assertIsInstance(workflow2, TestWorkflowGrouped)
        self.assertIsInstance(workflow3, TestWorkflowGrouped)
        self.assertEqual(workflow1, workflow2)
        self.assertNotEqual(workflow2, workflow3)
