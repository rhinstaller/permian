import unittest
import subprocess
from unittest.mock import patch, MagicMock, ANY
from libpermian.plugins.anaconda_webui import Hypervisor


class TestHypervisorLocal(unittest.TestCase):
    @patch('subprocess.run')
    def setUp(self, mocked_run):
        self.hv = Hypervisor('localhost')
        mocked_run.assert_not_called()

    @patch('time.sleep')
    @patch('subprocess.run')
    def test_wait_for_ip(self, mocked_run, mocked_sleep):
        mocked_run.return_value.stdout = b' vnet31     aa:bb:cc:dd:ee:ff    ipv4         192.168.122.42/24'
        self.assertEqual('192.168.122.42', self.hv.wait_for_ip('test_vm'))
        mocked_run.assert_called_with(['virsh', '-q', '--connect', 'qemu:///system', 'domifaddr', 'test_vm'], check=False, stdout=subprocess.PIPE)

    @patch('subprocess.run')
    def test_stop_vm(self, mocked_run):
        self.hv.stop_vm('test_vm')
        mocked_run.assert_called_with(['virsh', '-q', '--connect', 'qemu:///system', 'destroy', 'test_vm'], check=False, stdout=subprocess.PIPE)

    @patch('subprocess.run')
    def test_remove_vm(self, mocked_run):
        self.hv.remove_vm('test_vm')
        mocked_run.assert_called_with(['virsh', '-q', '--connect', 'qemu:///system', 'undefine', 'test_vm', '--remove-all-storage'], check=True, stdout=subprocess.PIPE)

    @patch('subprocess.run')
    def test_configure_forwarding(self, mocked_run):
        self.assertEqual(['1234', '5678'], self.hv.configure_forwarding('192.168.122.42', ['1234', '5678']))
        mocked_run.assert_not_called()


class TestHypervisorRemote(unittest.TestCase):
    @patch('libpermian.plugins.anaconda_webui.Hypervisor._open_connection')
    @patch('subprocess.run')
    @patch('tempfile.TemporaryDirectory')
    def setUp(self, mocked_tempdir, mocked_run, mocked_open_connection):
        mocked_tempdir.return_value.name = '/tmp/permian_sshctl.1234'
        self.hv = Hypervisor('example.com')
        mocked_open_connection.assert_called_once()

    @patch('time.sleep')
    @patch('subprocess.run')
    def test_wait_for_ip(self, mocked_run, mocked_sleep):
        mocked_run.return_value.stdout = b' vnet31     aa:bb:cc:dd:ee:ff    ipv4         192.168.122.42/24'
        self.assertEqual('192.168.122.42', self.hv.wait_for_ip('test_vm'))
        mocked_run.assert_called_with(['virsh', '-q', '--connect', 'qemu+ssh://example.com/system', 'domifaddr', 'test_vm'], check=False, stdout=subprocess.PIPE)

    @patch('subprocess.run')
    def test_stop_vm(self, mocked_run):
        self.hv.stop_vm('test_vm')
        mocked_run.assert_called_with(['virsh', '-q', '--connect', 'qemu+ssh://example.com/system', 'destroy', 'test_vm'], check=False, stdout=subprocess.PIPE)

    @patch('subprocess.run')
    def test_remove_vm(self, mocked_run):
        self.hv.remove_vm('test_vm')
        mocked_run.assert_called_with(['virsh', '-q', '--connect', 'qemu+ssh://example.com/system', 'undefine', 'test_vm', '--remove-all-storage'], check=True, stdout=subprocess.PIPE)

    @patch('subprocess.run')
    @patch('random.randint')
    def test_forward_port(self, mocked_randint, mocked_run):
        mocked_randint.return_value = 123456
        self.assertEqual(123456, self.hv._forward_port('192.168.122.42', '1234'))
        mocked_run.assert_called_with([
            'ssh', '-S', '/tmp/permian_sshctl.1234/example.com',
            '-O', 'forward', '-L', f'*:123456:192.168.122.42:1234', 'example.com'
            ], 
            check=True
        )

    def test_configure_forwarding(self):
        self.hv._forward_port = MagicMock()
        self.hv._forward_port.side_effect = ['42001', '42002']

        self.assertEqual(['42001', '42002'], self.hv.configure_forwarding('192.168.122.42', ['1234','5678']))
        self.hv._forward_port.assert_called_with('192.168.122.42', '5678')

    @patch('os.path.exists')
    @patch('subprocess.run')
    def test_close_connection(self, mocked_run, mocked_exists):
        mocked_exists.return_value = False
        self.hv._close_connection()
        mocked_run.assert_not_called()

        mocked_exists.return_value = True
        self.hv._close_connection()
        mocked_run.assert_called_with(['ssh', '-S', '/tmp/permian_sshctl.1234/example.com', '-O', 'exit', 'example.com'], check=True)
