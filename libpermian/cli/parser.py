import re
import argparse

def base_argparser():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--override', '-o',
        action=OverrideCallback,
        type=Override,
        help='Override settings option. It has to be provided in format: section.option=value',
    )
    parser.add_argument(
        '--settings', '-s',
        action='append',
        default=[],
        help='',
    )
    parser.add_argument(
        '--generate-event',
        action='store_true',
        help="Don't run the pipeline but generate event specification string for the event used.",
    )
    parser.add_argument(
        '--check-testruns',
        action='store_true',
        help="Don't run the pipeline but check if there's anything to be executed for provided event (with provided settings). The return code is zero if there's anything to be executed.",
    )
    parser.add_argument(
        '--debug-log',
        type=argparse.FileType('w'),
        help="Name of file where debug logs should be stored.",
    )
    verbosity = parser.add_mutually_exclusive_group()
    verbosity.add_argument(
        '--debug', '-d',
        action='store_true',
        help='',
    )
    verbosity.add_argument(
        '--quiet', '-q',
        action='store_true',
        help='',
    )
    return parser

class Override():
    """
    Parse override option provided in form section.option=value where the
    leftmost dot is considered and the leftmost equal sign (after the first
    dot) is considered.
    """
    expr = re.compile(r'^(?P<section>[^.]+)\.(?P<option>[^=]+)=(?P<value>.*)$')
    def __init__(self, value):
        mo = self.expr.match(value)
        if mo is None:
            raise argparse.ArgumentTypeError('Value of incorrect format was provided: "%s", expected value in format: "section.option=value"' % value)
        self.section = mo.group('section')
        self.option = mo.group('option')
        self.value = mo.group('value')

class OverrideCallback(argparse.Action):
    """
    Merge Overrides into one dict structure. If section or option doesn't exist
    create them. The last value of the same section.option wins.
    """
    def __init__(self, option_strings, dest, nargs=None, const=None, default=None, type=None, choices=None, required=False, help=None, metavar=None):
        if default is None:
            default = {}
        super().__init__(option_strings, dest, nargs, const, default, type, choices, required, help, metavar)
    
    def __call__(self, parser, namespace, values, option_string):
        dest = getattr(namespace, self.dest)
        if values.section not in dest:
            dest[values.section] = {}
        dest[values.section][values.option] = values.value

class ToPayload(argparse.Action):
    """ 
    Collects arguments into payload dict with dest as the key
    """
    def __init__(self, option_strings, dest, **kwargs):
        self.payload_dest = dest
        super().__init__(option_strings, "payload", **kwargs)

    def __call__(self, parser, namespace, values, option_string):
        if namespace.payload is None:
            namespace.payload = {}
        namespace.payload[self.payload_dest] = values

class AppendToPayload(argparse.Action):
    """
    Collects arguments into payload dict with dest as the key appending the
    value the same way as 'append' action would do.
    """
    def __init__(self, option_strings, dest, **kwargs):
        self.payload_dest = dest
        super().__init__(option_strings, "payload", **kwargs)

    def __call__(self, parser, namespace, values, option_string):
        if namespace.payload is None:
            namespace.payload = {}
        if self.payload_dest not in namespace.payload:
            namespace.payload[self.payload_dest] = []
        namespace.payload[self.payload_dest].append(values)

def bool_argument(value):
    """
    Custom argparse type that translates human readable booleans into True or False
    """
    positive = ['yes', 'true', '1']
    negative = ['no', 'false', '0']
    if value.lower() in positive:
        return True
    if value.lower() in negative:
        return False
    raise argparse.ArgumentTypeError("'%s' is not a valid boolean - must be one of '%s'." % (value, ','.join(positive + negative)))
