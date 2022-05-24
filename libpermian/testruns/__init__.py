import logging

from ..exceptions import StateChangeError
from ..workflows.factory import WorkflowFactory
from ..reportsenders.factory import ReportSenderFactory
from ..issueanalyzer.proxy import IssueAnalyzerProxy
from ..caserunconfiguration import CaseRunConfigurationsList
from ..result import Result

LOGGER = logging.getLogger(__name__)

class TestRuns():
    """Collection of case-run-configurations based on the Test Plans, Requirements and Test Cases from tplib provided library.

    This class also handles assignment of the workflows and manages their
    execution.
    """
    def __init__(self, library, event, settings):
        self.library = library
        self.event = event
        self.settings = settings
        self.caseRunConfigurations = []
        self.issueAnalyzerProxy = IssueAnalyzerProxy(self.settings)
        """List of CaseRunConfigurations taking part in this execution"""
        self.populateCaseRunConfigurations(library, event)
        self.assignWorkflows(event, settings)
        self.reportSenders = list(ReportSenderFactory.assign(self))

    def populateCaseRunConfigurations(self, library, event):
        """
        Based on the event and settings takes Test plans from library and
        for each of the Test plans collects list of Test cases and their
        configurations (in the context of the test plan). Based on those
        creates CaseRunConfiguration objects and stores them in
        caseRunConfigurations for later execution.

        If multiple caseRunConfiguration object share same testcase and
        configuration, they are merged into one object keeping records
        of the Test plans the case-run-configurations belong to.
        """
        LOGGER.debug("Getting caseRunConfigurations from event")
        self.caseRunConfigurations = event.generate_caseRunConfigurations(library)
        for caserun in self.caseRunConfigurations:
            caserun.testrun = self
            LOGGER.debug("Will run caseRunConfiguration %s: %s", caserun.id, caserun)

    def assignWorkflows(self, event, settings):
        """
        Aggregate CaseRunConfiguration objects based on their workflows
        and call Workflows factory function which then takes care of creating
        desired Worklflow instances. The Workflow instances are responsible
        for assigning themselves (as they see fit) to the CaseRunConfiguration
        objects. Note that one Workflow can be assigned to multiple
        CaseRunConfiguration objects.

        :raises UnexpectedState: When there's at least one CaseRunConfiguration object without workflow assigned.
        :return: None
        :rtype: None
        """
        WorkflowFactory.assign(self)

    def start(self):
        """
        Run start method on all workflows assigned to the CaseRunConfiguration
        objects.

        Note there may be multiple CaseRunConfiguration objects sharing the
        same Workflow object. In such situation, the start method should be
        called for one Workflow object only once.

        If this start method was already successfully invoked, nothing should
        happen.

        :raises NotReady: When this method is called before workflows are assigned.
        :return: None
        :rtype: None
        """
        for reportSender in self.reportSenders:
            reportSender.start()
        started_workflows = set()
        for caserun in self.caseRunConfigurations:
            if id(caserun.workflow) not in started_workflows:
                caserun.workflow.start()
                started_workflows.add(id(caserun.workflow))

    def wait(self):
        """
        Block execution until all workflows are finished. If this method is
        called after all workflows are finished, nothing should happen and no
        blocking should occur.

        :raises NotReady: When start method was not invoked yet.
        :return: True if all report senders finished without issue
        :rtype: bool
        """
        for caserun in self.caseRunConfigurations:
            caserun.workflow.join()
            if not caserun.result.final:
                # copy is needed here, so that the final result is not stored
                # in the crc before self.update is called.
                self.update(caserun.copy().updateResult(Result('DNF', 'ERROR', True)))
        all_ok = True
        for reportSender in self.reportSenders:
            reportSender.join()
            if reportSender.exception:
                all_ok = False
        return all_ok

    def update(self, crc):
        """
        Register update in crc provided by workflow and if the update is valid,
        provide it to ReportSenders.
        """
        try:
            crcUpdate = self.caseRunConfigurations[crc.id].updateResult(crc.result).readOnlyCopy()
        except StateChangeError as e:
            LOGGER.error('Cannot change state of result: %s', e)
            return
        for reportSender in self.reportSenders:
            reportSender.resultUpdate(crcUpdate)

    # TODO: consider using functools.lru_cache or functools.cached_property
    @property
    def testPlansMapping(self):
        """
        Mapping of testPlans to caseRunConfigurations. The keys are TestPlan
        ids and values are caseRunConfigurations which belong to the TestPlan.
        """
        return self.caseRunConfigurations.by_testplan()

    def __getitem__(self, crcId):
        for crc in self.caseRunConfigurations:
            if crc.id == crcId:
                return crc
        raise KeyError(f'No caseRunConfiguration of id "{crcId}" found.')

    def __iter__(self):
        for crc in self.caseRunConfigurations:
            yield crc.id

    def items(self):
        for crc in self.caseRunConfigurations:
            yield crc.id, crc
