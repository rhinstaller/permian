import unittest
import subprocess
from unittest.mock import patch, MagicMock, ANY

from libpermian.events.base import Event
from libpermian.settings import Settings
from libpermian.testruns import TestRuns
from libpermian.plugins.anaconda_webui import AnacondaWebUIWorkflow, ExecutionContainer
from libpermian.caserunconfiguration import CaseRunConfiguration
from libpermian.result import Result


class DummyTestPlan():
    id = 'dummy_testplan'


def get_DummyTestCase():
    instance = MagicMock()
    instance.name = 'Dummy test case'
    instance.id = instance.name
    instance.execution.automation_data = {'script_file': 'file', 'test_case': 'Case'}
    return instance

class TestAnacondaWebUIWorkflow(unittest.TestCase):
    @patch('subprocess.check_output')
    @patch('subprocess.check_call')
    def setUp(self, mocked_check_call, mocked_check_output):
        settings = Settings({
            'AnacondaWebUI': {
                    'webui_location' : '/webui',
                    'port_ssh': '11',
                    'port_webui': '8000',
                    'use_container': 'true',
                },
            'VMHypervisors': {
                'aarch64': 'qemu:///123.456.789.0',
                }
            }, {}, [])

        event = Event(settings, 'test', InstallationSource={"base_repo_id": "BaseOS",
            "repos": {"BaseOS": {"x86_64": {"os": "http://example.com/compose/x86_64/BaseOS/os",
                                     "kernel": "images/pxeboot/vmlinuz",
                                     "initrd": "images/pxeboot/initrd.img"},
                      "aarch64": {"os": "http://example.com/compose/aarch64/BaseOS/os",
                                      "kernel": "images/pxeboot/vmlinuz",
                                      "initrd": "images/pxeboot/initrd.img"}},
            "AppStream": {"x86_64": {"os": "http://example.com/compose/x86_64/AppStream/os"},
                          "aarch64": {"os": "http://example.com/compose/aarch64/AppStream/os"}}},
        })

        testRuns = TestRuns(MagicMock(), event, settings)
        crc = CaseRunConfiguration(get_DummyTestCase(),
                                   {'branch': 'test_branch', 'architecture': 'aarch64'},
                                   [DummyTestPlan()])

        self.workflow = AnacondaWebUIWorkflow(testRuns, [crc], None, None)
        self.workflow.log = MagicMock()
        self.workflow.groupLog = MagicMock()
        self.workflow.addLog = MagicMock()
        self.workflow.test_workdir = '/test/temp/workdir'
        self.workflow.temp_dir = '/test/temp'
        self.workflow.vm_name = 'test_vm'
        self.workflow.webui_dir = '/test/temp/workdir/webui'
        self.workflow.container = ExecutionContainer(subprocess.DEVNULL)

    @patch('libpermian.caserunconfiguration.CaseRunConfiguration.openLogfile')
    @patch('subprocess.Popen')
    def test_start_vm(self, mocked_popen, mocked_openLogfile):
        self.workflow.crc.openLogfile.return_value = MagicMock()
        self.workflow._start_vm()

        self.workflow.crc.openLogfile.assert_called_with('virt-install', 'wb', True)
        mocked_popen.assert_called_with(['virt-install', '--connect', 'qemu+ssh://root@qemu:///123.456.789.0/system', '--autoconsole', 'text',
            '-n', 'test_vm', '--os-variant', 'rhel-unknown', '--location',
            'http://example.com/compose/aarch64/BaseOS/os,kernel=images/pxeboot/vmlinuz,initrd=images/pxeboot/initrd.img',
            '--memory', '4096', '--vcpus', '2', '--disk', 'size=10', '--serial', 'pty', '--extra-args',
            'inst.sshd inst.webui inst.webui.remote inst.graphical console=ttyS0 inst.stage2=http://example.com/compose/aarch64/BaseOS/os inst.geoloc=0'],
            stderr=-2, stdout=self.workflow.crc.openLogfile.return_value)

    @patch('time.sleep')
    @patch('urllib.request.urlopen')
    def test_wait_for_webui(self, mocked_urlopen, mocked_sleep):
        self.workflow.test_system_ip = '192.168.122.42'

        self.workflow._wait_for_webui()

        mocked_sleep.assert_called_once_with(10)
        mocked_urlopen.assert_called_with('http://192.168.122.42:8000/webui', context=ANY)

    @patch('libpermian.caserunconfiguration.CaseRunConfiguration.openLogfile')
    @patch('os.listdir')
    @patch('time.sleep')
    @patch('subprocess.Popen')
    def test_execute(self, mocked_run, mocked_sleep, list_dir, mocked_openLogfile):
        mocked_run.return_value.returncode = 0
        list_dir.return_value = []
        self.workflow.reportResult = MagicMock()
        self.workflow.test_system_ip = '192.168.122.42'

        self.workflow.execute()
        
        mocked_run.assert_called_with(['podman', 'run', '--rm', '-it', '-v',
            '/test/temp:/root/workdir:z', '-w', '/root/workdir/workdir',
            '-e', 'WEBUI_TEST_DIR=/root/workdir/workdir/webui/test',
            'anaconda-webui', 'file', 'Case', '--browser', '192.168.122.42:8000',
            '--machine', '192.168.122.42:11'], stderr=-2, stdout=ANY)

        self.workflow.reportResult.assert_called_with(Result('complete', 'PASS', True))
