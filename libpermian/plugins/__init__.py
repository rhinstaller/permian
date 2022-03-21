"""
Plugins package handles organization and management (loading) of plugins.

Pipeline plugins are python packages that are placed outside of libpermian and
symlinked in the directory of this package.

Plugins should add their functionality only via functions defined in
libpermian.plugins.api
"""

import os
import importlib
import sys


def env_plugins_override():
    """ Get enabled and disabled plugin names and paths to additional plugins from env variables

    :return: DISABLED_PLUGINS, ENABLED_PLUGINS, EXTRA_PLUGINS_PATHS
    :rtype: tuple
    """
    disable = os.environ.get('PIPELINEPLUGINS_DISABLE', '')
    disable = set(disable.split(',')) if disable != '' else set()
    enable = os.environ.get('PIPELINEPLUGINS_ENABLE', '')
    enable = set(enable.split(',')) if enable != '' else set()
    paths = os.environ.get('PIPELINEPLUGINS_PATH', '')
    paths = list(paths.split(':')) if paths != '' else list()

    if disable.intersection(enable):
        raise RuntimeError('Plugin cannot be enabled and disabled at the same time, check env.')

    return disable, enable, paths


PLUGINS_PATH = [os.path.dirname(os.path.abspath(__file__))]
DISABLED_PLUGINS, ENABLED_PLUGINS, EXTRA_PLUGINS_PATHS = env_plugins_override()
PLUGINS_PATH += EXTRA_PLUGINS_PATHS
PLUGINS_MODULE_NAME='libpermian.plugins'


def is_plugin_name(module_name):
    """ Checks whether module name looks like pipeline plugin """
    name_parts = module_name.split('.')

    if name_parts[:2] != PLUGINS_MODULE_NAME.split('.'):
        return False
    if len(name_parts) != len(PLUGINS_MODULE_NAME.split('.'))+1:
        return False
    if name_parts[2].startswith('__'):
        return False
    return True


def is_plugin_dir(dir):
    """ Checks whether directory path could be a valid plugin """
    # Plugin must be a directory
    if not os.path.isdir(dir):
        return False
    # Plugin must not start with "__", filters out __pycache__
    if os.path.basename(dir).startswith('__'):
        return False
    # Plugin must contain __init__.py
    if not os.path.exists(os.path.join(dir, '__init__.py')):
        return False
    return True


def loaded_plugin_modules():
    """ List loaded python modules that look like pipeline plugins """
    for module_name, module in sys.modules.items():
        if is_plugin_name(module_name) and '__path__' in dir(module):
            yield module


def disabled(plugins_dir, plugin_name):
    """ Checks if plugin is disabled """
    if  os.path.exists(os.path.join(plugins_dir, plugin_name, 'DISABLED')) and plugin_name not in ENABLED_PLUGINS:
        return True
    if plugin_name in DISABLED_PLUGINS:
        return True
    return False

class PluginsMetaPathFinder(importlib.machinery.PathFinder):
    @classmethod
    def find_spec(self, fullname, path=None, target=None):
        if not is_plugin_name(fullname):
            return None
        _, _, plugin_name = fullname.split('.')
        for plugins_dir in PLUGINS_PATH:
            module_path = os.path.join(plugins_dir, plugin_name)
            if not is_plugin_dir(module_path):
                continue
            if disabled(plugins_dir, plugin_name):
                continue
            spec = importlib.util.spec_from_file_location(fullname, os.path.join(module_path, '__init__.py'))
            return spec
        return None

sys.meta_path.append(PluginsMetaPathFinder)


def load():
    """Import all plugin packages."""
    for plugins_dir in PLUGINS_PATH:
        for plugin_name in sorted(os.listdir(plugins_dir)):
            # TODO: Add logger to log what plugins are (not) loaded and why
            if not is_plugin_dir(os.path.join(plugins_dir, plugin_name)):
                continue
            if disabled(plugins_dir, plugin_name): # Plugin must be enabled
                continue
            importlib.import_module('.'.join(['libpermian', 'plugins', plugin_name]))


def plugin_settings():
    """ Get paths for plugin settings files """
    for module in loaded_plugin_modules():
        plugin_settings_path = os.path.join(module.__path__[0], 'settings.ini')
        if os.path.exists(plugin_settings_path):
            yield plugin_settings_path
