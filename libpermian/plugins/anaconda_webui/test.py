import unittest
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
        self.workflow.test_workdir = '/test/temp/workdir'
        self.workflow.temp_dir = '/test/temp'
        self.workflow.vm_name = 'test_vm'
        self.workflow.container = ExecutionContainer()

    @patch('subprocess.run')
    def test_start_vm(self, mocked_run):
        self.workflow._start_vm()

        mocked_run.assert_called_with(['virt-install', '--connect', 'qemu:///123.456.789.0', '--noautoconsole',
            '-n', 'test_vm', '--os-variant', 'rhel-unknown', '--location',
            'http://example.com/compose/aarch64/BaseOS/os,kernel=images/pxeboot/vmlinuz,initrd=images/pxeboot/initrd.img',
            '--memory', '4096', '--vcpus', '2', '--disk', 'size=10', '--extra-args',
            'inst.sshd inst.webui inst.webui.remote inst.stage2=http://example.com/compose/aarch64/BaseOS/os'],
            check=True, stderr=-2, stdout=-1)

    @patch('time.sleep')
    @patch('subprocess.run')
    def test_wait_for_ip(self, mocked_run, mocked_sleep):
        mocked_run.return_value.stdout = b' vnet31     aa:bb:cc:dd:ee:ff    ipv4         192.168.122.42/24'

        self.workflow._wait_for_ip()

        self.assertEqual(self.workflow.vm_ip, '192.168.122.42')
        mocked_run.assert_called_with(['virsh', '-q', '--connect', 'qemu:///123.456.789.0', 'domifaddr', 'test_vm'], check=False, stdout=-1)

    @patch('time.sleep')
    @patch('urllib.request.urlopen')
    def test_wait_for_webui(self, mocked_urlopen, mocked_sleep):
        self.workflow.vm_ip = '192.168.122.42'

        self.workflow._wait_for_webui()

        mocked_sleep.assert_called_once_with(10)
        mocked_urlopen.assert_called_with('http://192.168.122.42:8000/webui', context=ANY)

    @patch('subprocess.run')
    def test_execute(self, mocked_run):
        mocked_run.return_value.returncode = 0
        self.workflow.reportResult = MagicMock()
        self.workflow.vm_ip = '192.168.122.42'

        self.workflow.execute()
        
        mocked_run.assert_called_with(['podman', 'run', '--rm', '-it', '-v',
            '/test/temp:/root/workdir:z', '-w', '/root/workdir/workdir',
            'anaconda-webui', 'file', 'Case', '--browser', '192.168.122.42:8000',
            '--machine', '192.168.122.42:11'], stderr=-2, stdout=-1)

        self.workflow.reportResult.assert_called_with(Result('complete', 'PASS', True))
