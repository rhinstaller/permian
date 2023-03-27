import unittest
from unittest.mock import patch, MagicMock, ANY
from libpermian.plugins.anaconda_webui import Hypervisor

class TestHypervisorLocal(unittest.TestCase):
    def setUp(self):
        self.hv = Hypervisor('localhost')

    @patch('time.sleep')
    @patch('subprocess.run')
    def test_wait_for_ip(self, mocked_run, mocked_sleep):
        mocked_run.return_value.stdout = b' vnet31     aa:bb:cc:dd:ee:ff    ipv4         192.168.122.42/24'
        self.assertEqual('192.168.122.42', self.hv.wait_for_ip('test_vm'))
        mocked_run.assert_called_with(['virsh', '-q', '--connect', 'qemu:///system', 'domifaddr', 'test_vm'], check=False, stdout=-1)

    @patch('subprocess.run')
    def test_stop_vm(self, mocked_run):
        self.hv.stop_vm('test_vm')
        mocked_run.assert_called_with(['virsh', '-q', '--connect', 'qemu:///system', 'destroy', 'test_vm'], check=False, stdout=-1)

    @patch('subprocess.run')
    def test_remove_vm(self, mocked_run):
        self.hv.remove_vm('test_vm')
        mocked_run.assert_called_with(['virsh', '-q', '--connect', 'qemu:///system', 'undefine', 'test_vm', '--remove-all-storage'], check=True, stdout=-1)

    @patch('subprocess.run')
    def test_configure_prerouting(self, mocked_run):
        self.assertEqual(['1234', '5678'], self.hv.configure_prerouting('192.168.122.42', ['1234', '5678']))
        mocked_run.assert_not_called()
        self.assertDictEqual({}, self.hv.configured_preroutings)

    @patch('subprocess.run')
    def test_clean_prerouting(self, mocked_run):
        self.hv.clean_prerouting()
        mocked_run.assert_not_called()


class TestHypervisorRemote(unittest.TestCase):
    def setUp(self):
        self.hv = Hypervisor('example.com')

    @patch('time.sleep')
    @patch('subprocess.run')
    def test_wait_for_ip(self, mocked_run, mocked_sleep):
        mocked_run.return_value.stdout = b' vnet31     aa:bb:cc:dd:ee:ff    ipv4         192.168.122.42/24'
        self.assertEqual('192.168.122.42', self.hv.wait_for_ip('test_vm'))
        mocked_run.assert_called_with(['virsh', '-q', '--connect', 'qemu+ssh://root@example.com/system', 'domifaddr', 'test_vm'], check=False, stdout=-1)

    @patch('subprocess.run')
    def test_stop_vm(self, mocked_run):
        self.hv.stop_vm('test_vm')
        mocked_run.assert_called_with(['virsh', '-q', '--connect', 'qemu+ssh://root@example.com/system', 'destroy', 'test_vm'], check=False, stdout=-1)

    @patch('subprocess.run')
    def test_remove_vm(self, mocked_run):
        self.hv.remove_vm('test_vm')
        mocked_run.assert_called_with(['virsh', '-q', '--connect', 'qemu+ssh://root@example.com/system', 'undefine', 'test_vm', '--remove-all-storage'], check=True, stdout=-1)

    @patch('subprocess.run')
    def test_get_available_port(self, mocked_run):
        mocked_run.return_value.stdout = b'''-P PREROUTING ACCEPT
-A PREROUTING -p tcp -m tcp --dport 42001 j DNAT --to 192.168.122.42:1234
-A PREROUTING -p tcp -m tcp --dport 42002 j DNAT --to 192.168.122.42:5678
'''
        self.assertEqual('42003', self.hv._get_available_port())

    def test_configure_prerouting(self):
        self.hv._aquire_config_lock = MagicMock()
        self.hv._aquire_config_lock.return_value = 1
        self.hv._get_available_port = MagicMock()
        self.hv._add_prerouting = MagicMock()
        self.hv._get_available_port.side_effect = ['42001', '42002']
        self.hv._release_config_lock = MagicMock()

        self.assertEqual(['42001', '42002'], self.hv.configure_prerouting('192.168.122.42', ['1234','5678']))
        self.assertDictEqual({'1234': ('192.168.122.42', '42001'), '5678': ('192.168.122.42', '42002')}, self.hv.configured_preroutings)
        self.hv._aquire_config_lock.assert_called_once()
        self.hv._add_prerouting.assert_called_with('192.168.122.42', '5678', '42002')
        self.assertEqual(2, self.hv._get_available_port.call_count)
        self.hv._release_config_lock.assert_called_once()

    @patch('subprocess.run')
    def test_clean_prerouting(self, mocked_run):
        self.hv.configured_preroutings = {'1234': ('192.168.122.42', '42001'), '5678': ('192.168.122.42', '42002')}
        self.hv.clean_prerouting()
        
        self.assertEqual(4, mocked_run.call_count)
        self.assertDictEqual({}, self.hv.configured_preroutings)
