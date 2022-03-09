import abc
import threading
import os
import datetime

from ..exception_dump import dump_exception
from ..result import Result

class GroupedWorkflow(threading.Thread, metaclass=abc.ABCMeta):
    """
    Abstract class for all workflows. Use this class as parent for you
    workflow if you want to handle multiple caseRunConfigurations by one
    workflow instance. If you're not seeking this functionality, look for
    IsolatedWorkflow class.

    Workflow instances should not be directly created, use the factory method
    which should handle creation of the workflow instances.
    """
    silent_exceptions = tuple()

    @classmethod
    @abc.abstractmethod
    def factory(cls, testRuns, crcList):
        """
        Make instances of this workflow for given caseRunConfigurations and
        assign them accordingly.

        Note: Once same instance may be assigned to multiple items of
        caseRunConfigurations. The way how the instances are assigned to
        individual caseRunConfiguration objects is up to the workflow.

        :param crcIds: List of CaseRunConfiguration which belong to this workflow.
        :type crcIds: list
        :return: None
        :rtype: None
        """

    def __init__(self, testRuns, crcList):
        self.testRuns = testRuns
        self.event = testRuns.event
        self.settings = testRuns.settings
        self.dryRun = self.settings.getboolean('workflows', 'dry_run')
        self.logFormat = self.settings.get('workflows', 'log_format')
        self.logTimestampFormat = self.settings.get('workflows', 'log_timestamp_format')
        self.exceptions = []
        for crc in crcList:
            crc.workflow = self
        self.crcList = crcList.copy()
        super().__init__()

    def run(self):
        """
        This is the main body of the workflow execution. This method calls
        setup, execute (or dry_execute) and teardown methods in sequence.

        This method is not meant to be called directly as it's started in
        separate thread once the workflow.start method is invoked. For more
        information see Threading.Thread.start.

        :return: None
        :rtype: None
        """
        try:
            self.setup()
            self.execute() if not self.dryRun else self.dry_execute()
        except self.silent_exceptions as e:
            self.groupLog(f'Workflow raised silent exception: {e}')
            self.groupReportResult(self.crcList, Result('DNF', 'ERROR', True))
        except Exception as e:
            self.exceptions.append(dump_exception(e, self))
            self.groupReportResult(self.crcList, Result('DNF', 'ERROR', True))
            # reraise the exception so that it's exposed for unit tests
            raise
        finally:
            try:
                self.teardown()
            except Exception as e:
                self.exceptions.append(dump_exception(e, self))
                # reraise the exception so that it's exposed for unit tests
                raise

    def setup(self):
        """
        Steps performed before actual execution started.

        :return: None
        :rtype: None
        """
        # do some preparation and logging

    @abc.abstractmethod
    def execute(self):
        """
        Steps performed during the execution of the workflow. Here's the place
        where the core code of the workflow should be happening.

        This method should NEVER EVER perform any computation intensive tasks
        as it's executed in python thread. If needed, use separate processes
        using subprocess, multiprocessing modules or fork function.

        :return: None
        :rtype: None
        """

    def dry_execute(self):
        """
        This method is invoked instead of the execute when the
        caseRunConfiguration should be executed in dry_run mode.
        """

    def teardown(self):
        """
        Steps performed after the execution ended.

        :return: None
        :rtype: None
        """
        # do some afteractions and logging

    @abc.abstractmethod
    def groupTerminate(self, crcIds):
        """
        Terminate execution of specific crcIds handled by the
        workflow.

        :param crcIds: Configurations to be terminated
        :type crcIds: list
        :return: TODO
        :rtype: TODO
        """

    def groupReportResult(self, crcList, result):
        """
        Provide partial or final result for the crcId. For more
        information see TODO:Result.

        :param crcIds: TODO
        :type crcIds: list
        :param result: TODO
        :type result: TODO
        :return: None
        :rtype: None
        """
        self.groupLog(f'Changing state to: "{result.state}" with result: "{result.result}"', crcList=crcList)
        for crc in crcList:
            crc.updateResult(result)
            self.testRuns.update(crc)

    @abc.abstractmethod
    def groupDisplayStatus(self, crcId):
        """
        Provides more comprehensive (and possibly graphically formatted) status
        of the workflow for the end user. This is meant as channel where more
        advanced information such as hyperlink to external system with some
        brief description of current workflow state is provided.

        Note: Output of this method should never be parsed.

        :param crcIds:
        :type crcIds:
        :return: Markdown formatted text provided for human processing
        :rtype: str
        """

    def groupAddLog(self, name, log_path, crcList=None):
        """
        Add arbitrary log_path to a log under specific name related to provided
        crcIds. If crcIds is not provided, all crcIds related to the workflow
        are used.

        The log_path can either be path to local file (relative or absolute)
        or URL.

        This method just registers the log_path but doesn't create files.
        """
        if crcList is None:
            crcList = self.crcList
        for crc in crcList:
            crc.addLog(name, log_path)

    def formatLogMessage(self, message):
        return self.logFormat.format(
            message=message,
            asctime=datetime.datetime.utcnow().strftime(self.logTimestampFormat)
        )

    def groupLog(self, message, name="workflow", crcList=None):
        """
        Add a message to a logfile with provided name related to provided
        crcIds. If the provided crcIds don't have such log yet, it's
        automatically created and assigned.

        When trying to log message to a log which is not a local file,
        exception RemoteLogError is raised.
        """
        message = self.formatLogMessage(message)
        if crcList is None:
            crcList = self.crcList
        for crc in crcList:
            with crc.openLogfile(name, 'a', True, filename=f"{name}.txt") as fo:
                fo.write(message)
                fo.write("\n")
