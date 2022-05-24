import unittest
import time
import json
import urllib.request
import requests
import tempfile
from flask import Blueprint
from tplib import library
from .server import WebUI
from ..events.base import Event
from ..settings import Settings
from ..testruns import TestRuns
from ..result import Result
from ..reportsenders.factory import ReportSenderFactory
from ..workflows.factory import WorkflowFactory


test_blueprint = Blueprint('test', __name__)
WebUI.registerBlueprint(test_blueprint)

@test_blueprint.route('/unittest')
def page_unittest():
    return 'Ha!'


class TestWebUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.settings = Settings(cmdline_overrides={}, environment={}, settings_locations=[])

    def test_webui(self):
        self.webUI = WebUI(self)
        self.webUI.start()
        self.webUI.waitUntilStarted()
        
        with urllib.request.urlopen(self.webUI.baseurl + 'unittest') as response:
            self.assertEqual('Ha!', response.read().decode("utf-8"))


class TestWebUIData(unittest.TestCase):
    @classmethod
    def setUp(self):
        self.logsdir = tempfile.TemporaryDirectory(prefix="testlogs_")
        ReportSenderFactory.clear_reportSender_classes()
        WorkflowFactory.clear_workflow_classes()
        self.library = library.Library('tests/test_library')
        self.settings = Settings(cmdline_overrides={'library': {'defaultCaseConfigMergeMethod': 'extension'}, 'workflows': {'logsdir':self.logsdir.name}}, environment={}, settings_locations=[])
        self.event = Event(self.settings, 'test', other={'tests': ['test1']})
        self.testRuns = TestRuns(self.library, self.event, self.settings)
        self.webUI = WebUI(self)
        self.webUI.start()
        self.webUI.waitUntilStarted()

    @classmethod
    def tearDown(self):
        ReportSenderFactory.restore_reportSender_classes()
        WorkflowFactory.restore_workflow_classes()
        self.logsdir.cleanup()

    def test_webui_data(self):
        with urllib.request.urlopen(self.webUI.baseurl + 'pipeline_data') as response:
            pipeline_data = json.loads(response.read())

        pipeline_data[0]['state'] = 'started'
        self.testRuns.caseRunConfigurations[0].result.update(Result('started'))

        with urllib.request.urlopen(self.webUI.baseurl + 'pipeline_data') as response:
            self.assertEqual(pipeline_data, json.loads(response.read()))

    def test_webui_logs(self):
        message = 'Hello from webUI test!'
        external_url = 'http://some.server.example.com/foo/bar'
        crc = self.testRuns.caseRunConfigurations[0]
        with urllib.request.urlopen(self.webUI.baseurl + 'pipeline_data') as response:
            expected_pipeline_data = json.loads(response.read())
        self.assertEqual(expected_pipeline_data[0]['logs'], [])
        expected_pipeline_data[0]['logs'] = ['external', 'hello']
        crc.addLog('external', external_url)
        with crc.openLogfile('hello', 'w', autoadd=True) as logfile:
            logfile.write(message)
        with urllib.request.urlopen(self.webUI.baseurl + 'pipeline_data') as response:
            pipeline_data = json.loads(response.read())
        self.assertEqual(pipeline_data, expected_pipeline_data)
        # use requests to detect redirects as it's much easier than urllib.request. TODO: change all urllib.request to requests
        response = requests.get(f'{self.webUI.baseurl}logs/{crc.id}/external', allow_redirects=False)
        self.assertEqual(response.next.url, external_url)
        with urllib.request.urlopen(f'{self.webUI.baseurl}logs/{crc.id}/hello') as response:
            self.assertEqual(response.read().decode(), message)

class TestWebUIDebug(unittest.TestCase):
    def test_webui_debug(self):
            self.skipTest('Enable only for debugging')
            self.library = library.Library('tests/test_library')
            self.settings = Settings(cmdline_overrides={'library': {'defaultCaseConfigMergeMethod': 'extension'}, 'testingPlugin': {'reportSenderDirectory': "./"}}, environment={}, settings_locations=[])
            self.event = Event(self.settings, 'test', other={'tests': ['test1']})
            self.testRuns = TestRuns(self.library, self.event, self.settings)
            self.webUI = WebUI(self)
            self.webUI.start()
            self.webUI.waitUntilStarted()
            time.sleep(30)
