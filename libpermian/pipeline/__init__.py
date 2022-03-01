import copy
import os
import threading
import logging
from tclib.library import Library

from ..settings import Settings
from ..events.factory import EventFactory
from ..testruns import TestRuns
from ..webui import WebUI
from .. import hooks
from . import library_repo

LOGGER = logging.getLogger(__name__)

def run_pipeline(event, settings_paths, overrides, env=None):
    """
    Start the pipeline with provided pipeline parameters.

    For more information see Pipeline constructor and run methods.

    :param event: JSON encoded event definition
    :type event: str
    :param settings_paths: Paths to settings files independent on the event (main pipeline settings)
    :type settings_paths: list
    :param overrides: Direct overrides of settings values, for more details see libpermian.settings.Settings
    :type overrides: dict
    :param env: Alternative environemnt variables to be used instead of os.environ
    :type env: dict, optional
    """
    pipeline = Pipeline(event, settings_paths, overrides, env)
    pipeline.run()
    return pipeline.return_code

class Pipeline():
    """
    Create pipeline object providing all essential information required for the
    pipeline execution. When ready, the pipeline can be executed only once and
    if other execution is needed, one should create a new pipeline object. Note
    that plugins still can "leave mess" after previous execution and pipeline
    cannot guarantee this not happening, so it's much safer to create only one
    pipeline object and exit the process after the pipeline finishes.

    :param event: JSON encoded event definition
    :type event: str
    :param settings_paths: Paths to settings files independent on the event (main pipeline settings)
    :type settings_paths: list
    :param overrides: Direct overrides of settings values, for more details see libpermian.settings.Settings
    :type overrides: dict
    :param env: Alternative environemnt variables to be used instead of os.environ
    :type env: dict, optional
    """
    def __init__(self, event, settings_paths, overrides, env=None):
        if env is None:
            env = copy.copy(os.environ)
        self.settings = Settings(overrides, env, settings_paths)
        self.event = EventFactory.make(self.settings, event)
        self.library = None
        self.testRuns = None
        self.executed = False
        self.webUI = None
        self.return_code = 0

    def _checkThreads(self):
        """
        Make sure that the pipeline is run from the main thread and there are
        no other threads, in other words, make sure we're alone and the waiting
        for threads at the end of pipeline will work.
        """
        if threading.current_thread() != threading.main_thread():
            raise Exception('The pipeline has to be executed from the main thread')
        if [threading.current_thread()] != threading.enumerate():
            raise Exception('There are other threads active')
        
    def run(self):
        """
        This is the main pipeline method which handles all the orchestration
        and when ended all the pipeline related activities (except daemon
        threads) are be finished.
        """
        LOGGER.debug('Starting pipeline')
        self._checkThreads()
        if self.executed:
            raise Exception('The pipeline can be executed only once')
        self.executed = True
        LOGGER.debug('Starting WebUI')
        self._startWebUI()
        LOGGER.debug('WebUI started')
        self._cloneLibrary()
        LOGGER.debug('Making test runs')
        self._makeTestRuns()
        LOGGER.debug('Preparing reporting')
        self._prepareReporting()
        LOGGER.debug('Preparing workflows')
        self._prepareWorkflows()
        LOGGER.debug('Running workflows')
        self._runWorkflows()
        LOGGER.debug('Waiting for workflows to finish')
        self._set_return_code(self._waitForWorkflows(), 1)
        LOGGER.debug('Waiting for other threads to finish')
        self._waitForThreads()
        LOGGER.debug('Running pipeline_ended handlers')
        hooks.builtin.pipeline_ended(self)
        LOGGER.debug('Waiting for other (post) threads to finish')
        self._waitForThreads() # wait for any possible threads started by the final hook

    def _set_return_code(self, succeeded, rc):
        if not succeeded:
            self.return_code |= rc

    def _startWebUI(self):
        """
        Start WebUI daemon thread and start providing the pipeline status over
        HTTP.
        """
        self.webUI = WebUI(self)
        self.webUI.start()
        self.webUI.waitUntilStarted()

    def _cloneLibrary(self, target_directory=None):
        """
        Clone repository containing testplans, requirements and testcases and
        store them in :py:attr:`library` attribute using
        :py:class:`tclib.Library`.
        """
        try:
            # first try direct specification of path to library
            target_directory = self.settings.get('library', 'directPath')
        except KeyError:
            target_directory = library_repo.clone(target_directory, self.event, self.settings)
        self.settings.load_from_library(target_directory)
        self.library = Library(target_directory,
                               additional_testplans=self.event.additional_testplans_data,
                               additional_requirements=self.event.additional_requrements_data,
                               additional_testcases=self.event.additional_testcases_data)

    def _makeTestRuns(self):
        """
        Create TestRuns instance preparing prescriptions for execution and
        reporting.
        """
        self.testRuns = TestRuns(self.library, self.event, self.settings)

    def _prepareReporting(self):
        """
        Create ResultRouter instance and have all the ResultSender instances
        ready for the workflows to send results.
        """
        pass

    def _prepareWorkflows(self):
        """
        Create all workflow instances for the TestRuns instance.
        """
        pass

    def _runWorkflows(self):
        """
        Start the wokflows associated to the TestRuns.

        Note: This method calls hook which signals the pipeline has started the
        execution.
        """
        self.testRuns.start()

    def _waitForWorkflows(self):
        """
        Wait until all the workflows associated to the TestRuns have ended.

        Note: This method calls hook which signals the pipeline has finished the
        execution.
        """
        return self.testRuns.wait()

    def _waitForThreads(self):
        current_thread = threading.current_thread()
        for thread in threading.enumerate():
            if thread == current_thread:
                continue
            if thread.daemon:
                continue
            thread.join()
