import logging
from functools import lru_cache
from hashlib import sha1
import os
import shutil
import re

from ..result import Result
from ..exceptions import UnexpectedState, StateChangeError, ReadOnlyChangeError, UnknownTestConfigurationMergeMethod, LocalLogExistsError, RemoteLogError
from ..result import Result, UNSET, STATES, RESULTS

URL_RE = re.compile("[^/]+://")
LOGGER = logging.getLogger(__name__)

class CaseRunConfiguration():
    """Representation of case-run-configuration containing logic for state and
    result management as well as information about workflow responsible for
    handling of the case-run-configuration.

    :param testcase: Test case for which the case-run is executed.
    :type testcase: tplib.structures.testcase.TestCase
    :param configuration: Configuration for which the case-run is executed.
    :type configuration: dict
    :param testplans: List of testplan ids for which the case-run-configuration executed.
    :type testplans: list
    """
    def __init__(self, testcase, configuration, testplans):
        self.testrun = None
        self.testcase = testcase
        """TestCase handled by this run"""
        self.configuration = configuration
        """Configuration of the TestCase"""
        self.running_for = { testplan.id : True for testplan in testplans }
        """Mapping of plans for which this configuration shoud be executed"""
        self.workflow = None
        """Workflow instance handling execution of this configuration"""
        self.result = Result('not started')
        """TODO"""
        self.readOnly = False
        """If set to true, the object is meant to be used as read-only copy and some methods which have side effects are forbidden and raise exception."""
        self.logs = dict()
        """Paths or URLs to logs associated to the caseRunConfiguration with specific names"""

    @property
    @lru_cache(maxsize=None)
    def id(self):
        """ Return string ID made from hash """
        return sha1(f'{self.testcase.id}:{sorted(self.configuration.items())}'.encode()).hexdigest()

    def copy(self):
        caserun = CaseRunConfiguration(self.testcase, self.configuration, [])
        caserun.testrun = self.testrun
        caserun.running_for = self.running_for
        caserun.workflow = self.workflow
        caserun.result = self.result.copy()
        # logs are on purpose shared
        caserun.logs = self.logs
        return caserun

    def readOnlyCopy(self):
        """
        Provide read-only copy of this instance. This is meant to be used when
        one copy is provided to multiple destinations and the destinations
        should not have ability to change state of the shared instance.
        """
        caserun = CaseRunConfiguration(self.testcase, self.configuration, [])
        caserun.testrun = self.testrun
        caserun.running_for = self.running_for
        caserun.workflow = self.workflow
        caserun.result = self.result.copy()
        # logs are on purpose shared
        caserun.logs = self.logs
        caserun.readOnly = True
        return caserun

    def cancel(self, reason):
        """
        Attempt to cancel this case-run-configuration for all testplans.

        :param reason: Description why the cancel should happen.
        :type reason: str
        :return: True if the workflow cancel was succesfull
        :rtype: bool
        """
        # TODO: record reason
        if self.result.final:
            return False
        self.running_for =  { plan:False for plan in self.running_for }
        crc_copy = self.copy()
        if self.workflow.groupTerminate([self.id]):
            crc_copy.updateResult(Result('canceled', None, True))
            canceled = True
        else:
            crc_copy.updateResult(Result('canceled', 'ERROR'))
            canceled = False
        self.testrun.update(crc_copy)
        return canceled

    def updateResult(self, result):
        """
        Update state of this case-run-configuration optionally setting result
        as well. This method is also used to mark the state as final effectively
        preventing any further change.

        :param state: Desired state to be set
        :type state: str
        :param result: Desired result to be set. If result is not set, the result is not changed. defaults to UNSET
        :type result: str, optional
        :param final: Mark the state as final preventing any future changes.
        :type final: bool
        :raises ValueError: When unknown state or result is provided.
        :return: Copy of given result with this caseRunConfiguration added
        :rtype: libpermian.result.Result
        """
        # At this moment, no locking is required as there should not be
        # multiple threads running the updateResult on the same
        # caseRunConfiguration instance as the only threads that should invoke
        # updateResult are workflows (it should not happen that multiple
        # workflow instances would be working on the same caseRunConfiguration)
        # and main thread setting DNF, ERROR result if the responsible workflow
        # thread is ended.
        # It's still worth noting, that this method may be cause of possible
        # race-condition issues in the future.
        LOGGER.debug('Attempting to change result of "%s" from %s to %s', self.id, self.result, result)
        if self.readOnly:
            raise ReadOnlyChangeError(f'Cannot change state of read-only result: {self}')
        try:
            self.result.update(result)
        except StateChangeError as e:
            LOGGER.error('Cannot change state of result: %s', e)
        return self

    def withResult(self, result):
        crcCopy = self.copy()
        crcCopy.result = result
        return crcCopy

    def assignWorkflow(self, workflow):
        """
        If workflow is already assigned and different workflow is about
        to assigned, raise traceback.

        While locked(state):
        If the state None, assign workflow and change state to queued.

        :param workflow: Mark this workflow as the one handling this case-run-configuration.
        :type workflow: tplib.Workflow
        :raises ValueError: When a different workflow instance is assigned.
        :return: None
        :rtype: None
        """

    def addLog(self, name, logfile, copy_file=False):
        """ Associates a file with this crc.
        
        If copy_file is True, the file is also copied to local logs dir.
        """
        if copy_file:
            with open(logfile, 'rb') as src_fo:
                dest_fo = self.openLogfile(name, 'wb', autoadd=True)
                shutil.copyfileobj(src_fo, dest_fo)
            dest_fo.close()
            return

        if name in self.logs and self.logs[name] != logfile:
            raise LocalLogExistsError(self.id, name, self.logs[name], logfile)
        self.logs[name] = logfile

    def openLogfile(self, name, mode="r", autoadd=False, filename=None):
        """
        Create (if doesn't exist) and open a logfile of given name related to
        the crcId. If autoadd is true, add the computed log path (from workflows
        settings and optional filename argument) to the related crcId.

        Raise RemoteLogError if the crc already has remote log assigned.
        """
        try:
            log_path = self.logs[name]
        except KeyError:
            log_path = os.path.join(
                self.testrun.settings.get('workflows', 'local_logs_dir'),
                self.id,
                filename or name
            )
        if log_path.startswith('file://'):
            log_path = log_path[7:] # trim the file://
        elif URL_RE.match(log_path):
            raise RemoteLogError(self.id, name, log_path)
        # make sure the target directory exists before opening the logfile
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        log_fo = open(log_path, mode)
        if autoadd:
            self.addLog(name, log_path)
        return log_fo

    def __iadd__(self, other):
        """
        Custom implementation of += operator.

        If the same CaseRunConfiguration is provided, update the information
        of Test Plans in this instance taking the Test Plans from the other
        instance.

        :raises NotImplemented: When object of incompatible type is given
        :raises ValueError: When not matching CaseRunConfiguration is given
        :return: self
        :rtype: CaseRunConfiguration
        """
        if not isinstance(other, CaseRunConfiguration):
            raise NotImplementedError()
        if self != other:
            raise ValueError("Cannot merge different CaseRunConfigurations")
        if self.readOnly:
            raise ReadOnlyChangeError(f'Cannot change state of read-only result: {self}')
        self.running_for.update(other.running_for)
        return self

    def __eq__(self, other):
        """
        Custom implementation of == operator.

        Compare with other CaseRunConfiguration and if they are of the same
        testcase and configuration return True.

        If the type of other is different fallback to other python methods
        allowing for other to still consider itself being the same thing.

        :raises NotImplemented:
        :return: True if the other CaseRunConfiguration is for the same testcase and has the same configuration, False otherwise.
        :rtype: bool
        """
        if not isinstance(other, CaseRunConfiguration):
            raise NotImplementedError()
        return (self.testcase, self.configuration) == (other.testcase, other.configuration)

    def __hash__(self):
        """ Returns hash of the CaseRunConfiguration made from testcase and configuration """
        return hash((self.testcase, tuple(sorted(self.configuration.items()))))

    def __repr__(self):
        return f"<CaseRunConfiguration({self.testcase.name}:{self.configuration})>"

class CaseRunConfigurationsList(list):
    """ Special list object with modified behaviour of append method for use with CaseRunConfigurations """
    def append(self, other_caserun):
        # If CaseRunConfiguration already created add current testplan to its running_for
        if other_caserun in self:
            self[self.index(other_caserun)] += other_caserun
        else:
            super().append(other_caserun)

    def copy(self):
        """
        Provide new CaseRunConfigurationsList containing copies of
        CaseRunConfigurations from this list.
        """
        return CaseRunConfigurationsList([crc.copy() for crc in self])

    def by_key(self, key_func):
        """
        Group caseRunConfigurations based on result of key_func.

        :param key_func:
        :type key_func: callable
        :return:
        :rtype dict:
        """
        result = {}
        for crc in self:
            key = key_func(crc)
            try:
                result[key].append(crc)
            except KeyError:
                result[key] = CaseRunConfigurationsList([crc])
        return result

    def by_testcase(self):
        return self.by_key(lambda crc: crc.testcase.id)

    def by_workflowType(self):
        return self.by_key(lambda crc: crc.testcase.execution.type)

    def by_configuration(self, *keys):
        return self.by_key(
            lambda crc: tuple([crc.configuration.get(key) for key in keys])
        )

    def by_testplan(self):
        result = {}
        for crc in self:
            for testplan in crc.running_for:
                try:
                    result[testplan].append(crc)
                except KeyError:
                    result[testplan] = CaseRunConfigurationsList([crc])
        return result

    @property
    def status(self):
        """Return lowest state present in the caseRunConfigurations"""
        states = { state:i for i, state in enumerate(STATES) }
        return list(STATES)[min([states[crc.result.state] for crc in self])]

    @property
    def result(self):
        """Return highest result present in the caseRunConfigurations"""
        results = { result:i for i, result in enumerate(RESULTS) }
        return list(RESULTS)[max([results[crc.result.result] for crc in self])]

    @property
    def hasDirtyResult(self):
        return any([crc.result.dirty for crc in self])

    @property
    def allResultsFinal(self):
        return all([crc.result.final for crc in self])

    @property
    def ids(self):
        return [crc.id for crc in self]

    @property
    def withDirtyResult(self):
        try:
            return self.by_key(lambda crc: crc.result.dirty)[True]
        except KeyError:
            return CaseRunConfigurationsList([])

    def __getitem__(self, index):
        if isinstance(index, int):
            return super().__getitem__(index)
        crcId = index
        for crc in self:
            if crc.id == crcId:
                return crc
        raise KeyError(f'No caseRunConfiguration of id "{crcId}" found.')


class ConfigurationDictHybrid(dict):
    """ Configuration dict that tries to combine configurations while respecting limitations """
    def merge(self, other):
        """ Merges self and other dict by preserving key-values from other dict and adding unique keys from self """
        config = other.copy()
        for missing_key in self.keys() - other.keys():
            config[missing_key] = self[missing_key]
        return config

    def compatible_with(self, other):
        """ Checks if this configuration dict can be merged with other dict using the Hybrid method:
        all keys that are in both dicts must have the same value
        """
        for key, value in self.items():
            if key in other and value != other[key]:
                return False
        return True

class ConfigurationDictStrict(dict):
    """ Configuration dict that 'merges' only exactly the same configurations """
    def merge(self, other):
        """ Just returns other dict as it has to be the same in order to be 'merged' """
        return other

    def compatible_with(self, other):
        """ Checks if this configuration dict can be merged with other dict using the Strict method:
        must be the same
        """
        return self == other

class ConfigurationsList(list):
    def __init__(self, clist, merge_method):
        """ List of configurations used for testplan that then extends and/or limits testcase configurations during merge

        :param clist: (Testplan) Configurations
        :type clist: list of dicts, None
        :param merge_method: name of merge method - determines the type of configurations
        :type merge_method: string
        """
        # Handle None configurations list
        if clist is None:
            clist = []
        # Conver configurations to particular ConfigurationDict based on merge_method
        if merge_method == 'intersection':
            clist = [ ConfigurationDictStrict(item) for item in clist ]
        elif merge_method == 'extension':
            clist = [ ConfigurationDictHybrid(item) for item in clist ]
        else:
            raise UnknownTestConfigurationMergeMethod(merge_method)
        super().__init__(clist)

    def merge(self, other):
        """ Merges self configurations and other configurations
        If self configurations is empty, the other configurations are returned
        If other configurations is empty, empty dict is added

        :param testcase: Testcase
        :type testcase: tplib.TestCase
        :param testplan: Testplan
        :type testplan: tplib.TestPlan
        :return: Configurations
        :rtype: list of dicts
        """
        configs = []
        # Handle no other configurations
        if other == None:
            other = [{}]
        # Handle no self configurations
        if self == []:
            return other
        # Perform merge
        for self_config in self:
            for other_config in other:
                if self_config.compatible_with(other_config):
                    configs.append(self_config.merge(other_config))

        return configs

def merge_testcase_configurations(caseRunConfigurations):
    """ Converts list of CaseRunConfiguration objects into a dict with testcase name as key
    and adds common result and workflow

    :param caseRunConfigurations: List of CaseRunConfiguration objects
    :type caseRunConfigurations: list
    :raises RuntimeError: When workflow is not common for all configurations of a testcase
    :return: {'testcase_name': {caseRunConfigurations: list, result: Result, workflow: str}, ...}
    :rtype: dict
    """
    testcases = {}
    for caserun in caseRunConfigurations:
        if caserun.testcase.name not in testcases:
            testcases[caserun.testcase.name] = {'caseRunConfigurations': [], 'result': None, 'workflow': None}
        testcase = testcases[caserun.testcase.name]

        # add caserun
        testcase['caseRunConfigurations'].append(caserun)
            
        # set workflow
        if testcase['workflow'] is not None and testcase['workflow'] != caserun.testcase.execution.type:
            raise RuntimeError('CaseRunConfigurations for one tescase have different workflows')
        testcase['workflow'] = caserun.testcase.execution.type
            
        if testcase['result'] is None:
            testcase['result'] = caserun.result.copy()
            continue

        if list(STATES).index(testcase['result'].state) > list(STATES).index(caserun.result.state):
            testcase['result'].state = caserun.result.state
        if list(RESULTS).index(testcase['result'].result) < list(RESULTS).index(caserun.result.result):
            testcase['result'].result = caserun.result.result

    return testcases
