import unittest
from unittest.mock import patch, MagicMock, call
from . import env_plugins_override, disabled, load
from importlib import import_module
import importlib

mocked_os_environ = {'SOMETHING_ELSE': 'foo',
                     'PIPELINEPLUGINS_DISABLE': 'plugin1,plugin2,plugin3',
                     'PIPELINEPLUGINS_ENABLE': 'plugin4'}

mock = MagicMock()

TEST_PLUGINS_PATH = {'tests/plugins'}
plugins_dir = list(TEST_PLUGINS_PATH)[0]

class TestPluginsOverride(unittest.TestCase):
    @patch('os.environ', new=mocked_os_environ)
    def test_env_plugins_override(self):
        disabled, enabled, _ = env_plugins_override()
        self.assertEqual(disabled, {'plugin1', 'plugin2', 'plugin3'})
        self.assertEqual(enabled, {'plugin4'})

    @patch('libpermian.plugins.PLUGINS_PATH', new=TEST_PLUGINS_PATH)
    def test_plugins_disabled_flag(self):
        self.assertFalse(disabled(plugins_dir, 'test1_enabled'))
        self.assertTrue(disabled(plugins_dir, 'test2_disabled'))

    @patch('libpermian.plugins.DISABLED_PLUGINS', new={'test1_enabled'})
    @patch('libpermian.plugins.ENABLED_PLUGINS', new={'test2_disabled'})
    @patch('libpermian.plugins.PLUGINS_PATH', new=TEST_PLUGINS_PATH)
    def test_plugins_disabled_override(self):
        self.assertTrue(disabled(plugins_dir, 'test1_enabled'))
        self.assertFalse(disabled(plugins_dir, 'test2_disabled'))

class TestPluginsLoad(unittest.TestCase):
    @patch('importlib.import_module', new=mock)
    @patch('libpermian.plugins.PLUGINS_PATH', new=TEST_PLUGINS_PATH)
    def test_plugins_load(self):
        self.assertEqual([], mock.call_args_list)
        load()
        self.assertTrue(call('libpermian.plugins.test1_enabled') in mock.call_args_list)
        self.assertFalse(call('libpipleine.plugins.test2_disabled') in mock.call_args_list)

 