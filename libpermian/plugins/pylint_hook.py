import astroid
import importlib
from astroid import MANAGER

# This file is meant to be used only and only as a pylint plugin to enable
# imports of libpermian plugins.

def register(linter):
    pass

builder = astroid.builder.AstroidBuilder(MANAGER)

def failed_custom_import(modname):
    if not modname.startswith('libpermian.plugins.'):
        raise astroid.AstroidBuildingError(modname=modname)
    module = importlib.import_module(modname)
    return builder.module_build(module, modname)

MANAGER.register_failed_import_hook(failed_custom_import)
