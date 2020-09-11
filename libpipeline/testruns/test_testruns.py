import unittest
from . import CaseRunConfigurationsList
from ..events.base import Event
from ..settings import Settings
from tclib import library
from . import TestRuns

from libpipeline.workflows.factory import WorkflowFactory
from libpipeline.workflows.isolated import IsolatedWorkflow, GroupedWorkflow
from libpipeline.workflows.builtin import UnknownWorkflow, ManualWorkflow


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
    def factory(cls, caseRunConfigurations):
        cls(caseRunConfigurations)


class TestWorkflowGrouped(GroupedWorkflow):
    def execute(self):
        pass

    def groupTerminate(self):
        return False

    def groupDisplayStatus(self):
        return 'Test'

    @classmethod
    def factory(cls, caseRunConfigurations):
        # Split caseruns into groups by architecture
        groups_by_config = dict()
        for caserun in caseRunConfigurations:
            try:
                groups_by_config[caserun.configuration['arch']].append(caserun)
            except KeyError:
                groups_by_config[caserun.configuration['arch']] = [caserun]

        for caseruns in groups_by_config.values():
            cls(caseruns)


def testruns_init():
        lib = library.Library('tests/test_library')
        settings = Settings(cmdline_overrides={'library': {'defaultCaseConfigMergeMethod': 'extension'}}, environment={}, settings_locations=[])
        event = Event('test', {}, ['test_workflows'])
        return TestRuns(lib, event, settings)


class TestCaseRunConfigurationsList(unittest.TestCase):
    def test_caserun_configurations_list(self):
        caserun_configurations = CaseRunConfigurationsList()
        caserun_configurations.append(1)
        self.assertListEqual(caserun_configurations, [1])
        caserun_configurations.append(1)
        self.assertListEqual(caserun_configurations, [2])
        caserun_configurations.append(3)
        self.assertListEqual(caserun_configurations, [2, 3])


class TestAssignWorkflows1(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.old_workflow_classes = WorkflowFactory.workflow_classes.copy()
        WorkflowFactory.register('test_isolated')(TestWorkflowIsolated)
        WorkflowFactory.register('test_grouped')(TestWorkflowGroupedAll)
        cls.testruns = testruns_init()

    @classmethod
    def tearDownClass(cls):
        WorkflowFactory.workflow_classes = cls.old_workflow_classes

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
        cls.old_workflow_classes = WorkflowFactory.workflow_classes.copy()
        WorkflowFactory.register('test_grouped')(TestWorkflowGrouped)
        cls.testruns = testruns_init()

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