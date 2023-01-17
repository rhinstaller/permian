"""
cli package handles execution of the pipeline from commandline. This package
focuses on parsing of cmdline arguments and executing the pipeline with
desired parameters.

It's possible to extend the CLI in plugins by introducing new commands.
The commands have associated parser function which provides parsed options
and event which the pipeline should react on. For more information see
CliFactory class.
"""

import sys
import os
import pty
import logging

from .. import plugins
from ..pipeline import run_pipeline, get_caserunconfigurations
from .factory import CliFactory
from . import builtin

def main(*raw_args):
    """
    Main pipeline function which should be called when the pipeline is executed
    from CLI. The command name is detected based on the first argument (name of
    the file from which the pipeline is executed) and corresponding command
    parser is used for event generation and option parsing.

    Custom CLI arguments can be optionally provided as \*args. If those are not
    provided sys.argv content is used as CLI arguments.
    """
    if not os.isatty(0):
        # Set pseudo-terminal as fd 0 (stdin), this breaks input into pipeline but
        # workarounds issues when running subprocess that requires interactive console
        _, pty_slave = pty.openpty()
        os.dup2(pty_slave, 0)

    plugins.load()
    if not raw_args:
        raw_args = sys.argv
    command_name, *args = raw_args
    filename = os.path.basename(command_name)
    options, event_spec = CliFactory.parse(filename, args)
    # TODO: Move logging_level to settings where --debug|--quiet would set override
    logging_level = logging.INFO
    if options.debug:
        logging_level = logging.DEBUG
    if options.quiet:
        logging_level = logging.WARN
    # set up handlers
    stderr_handler = logging.StreamHandler()
    stderr_handler.setLevel(logging_level)
    handlers=[stderr_handler]
    if options.debug_log:
        debug_log_handler = logging.StreamHandler(options.debug_log)
        debug_log_handler.setLevel(logging.DEBUG)
        handlers.append(debug_log_handler)
    # configure logging using the handlers
    logging.basicConfig(
        level=logging.ERROR, # Set everything (non-pipeline) to error
        format="%(levelname)s:%(name)s(%(threadName)s):%(message)s",
        handlers=handlers,
    )
    logging.getLogger('libpermian').setLevel(logging.DEBUG)
    logger = logging.getLogger(__name__)
    # the whole logging setup stuff should be probably moved elsewhere
    if options.generate_event:
        print(event_spec)
        sys.exit(0)
    if options.check_testruns:
        crcList = get_caserunconfigurations(event_spec, options.settings, options.override)
        logger.info("Would execute %d case run configurations", len(crcList))
        logger.debug(
            "Case Run configurations that would be executed:\n %s",
            "\n ".join([repr(crc) for crc in crcList]),
        )
        logger.info("Would execute %d test cases", len(crcList.by_testcase()))
        logger.debug(
            "Test cases that would be executed: \n %s",
            "\n ".join(crcList.by_testcase().keys()),
        )
        logger.info("Would execute %d test plans", len(crcList.by_testplan()))
        logger.debug(
            "Test plans that would be executed: \n %s",
            "\n ".join(crcList.by_testplan().keys()),
        )
        sys.exit(0 if crcList else 1)
    result = run_pipeline(event_spec, options.settings, options.override)
    sys.exit(result)
