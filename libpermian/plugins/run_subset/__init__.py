import json
import argparse

from tclib.expressions import eval_bool

from .. import api
from ...cli.factory import CliFactory
from ...events.base import Event
from ...events.factory import EventFactory
from ...caserunconfiguration import CaseRunConfigurationsList
from libpermian.events.structures.base import BaseStructure

def keys_values_sep(pair_sep, keyval_sep):
    def keys_values(data):
        try:
            return dict(
                item.split(keyval_sep, 1)
                for item
                in data.split(pair_sep)
            )
        except ValueError:
            raise argparse.ArgumentTypeError(f"'{data}' is not value key/value[,key/value] argument. Expected format: 'key{keyval_sep}value{pair_sep}key{keyval_sep}svalue' where the 'key{keyval_sep}value' can be specified once or multiple times.")
    return keys_values

@api.events.register('run_subset')
class RunSubsetEvent(Event):
    def __init__(self, settings, type, run_subset, **kwargs):
        super().__init__(settings, type, run_subset=run_subset, **kwargs)
        self.original_event = EventFactory.make(self.settings, self.run_subset.event)

    def format_branch_spec(self, fmt):
        return self.original_event.format_branch_spec(fmt)

    @property
    def additional_testplans_data(self):
        return self.original_event.additional_testplans_data

    @property
    def additional_requrements_data(self):
        return self.original_event.additional_requrements_data

    @property
    def additional_testcases_data(self):
        return self.original_event.additional_testcases_data

    def generate_caseRunConfigurations(self, library):
        crcList = CaseRunConfigurationsList()
        original_crcList = self.original_event.generate_caseRunConfigurations(library)
        for crc in original_crcList:
            if self.run_subset.testplans is not None:
                crc.running_for = {
                    testplan_id: True
                    for testplan_id
                    in crc.running_for
                    if testplan_id in self.run_subset.testplans
                }

            if self.run_subset.testplans_queries is not None:
                # consider only those testplans which comply with at least one
                # of the testplans_queries
                crc.running_for = {
                    testplan_id: True
                    for testplan_id
                    in crc.running_for
                    if any(
                        eval_bool(
                            testplans_query,
                            tp=library.testplans[testplan_id],
                        )
                        for testplans_query
                        in self.run_subset.testplans_queries
                    )
                }

            # ignore the crc if it's not executed for any testplan
            if not crc.running_for:
                continue

            if self.run_subset.testcases is not None:
                if crc.testcase.id not in self.run_subset.testcases:
                    continue

            if self.run_subset.testcases_queries is not None:
                if not any(
                    eval_bool(
                        testcases_query,
                        tc=crc.testcase,
                    )
                    for testcases_query
                    in self.run_subset.testcases_queries
                ):
                    continue

            if self.run_subset.configurations is not None:
                # check if any of provided configuration combination
                # (self.run_subset.configurations) is compatible with
                # crc.configuration (meaning it contains all the required keys
                # with required values => is subset)
                if not any(
                    set(subset_configuration.items()).issubset(set(crc.configuration.items()))
                    for subset_configuration in self.run_subset.configurations
                ):
                    continue

            if self.run_subset.crc_queries is not None:
                if not any(
                    eval_bool(
                        crc_query,
                        crc=crc,
                    )
                    for crc_query
                    in self.run_subset.crc_queries
                ):
                    continue

            # the crc passed all the provided filters, add it to the list
            crcList.append(crc)
        return crcList

    # If attribute/structure is not provided by this event, try getting it from
    # the original event
    # Note this doesn't handle methods provided by the base class, those still
    # have to be handled by overloading.
    def __getattr__(self, attrname):
        try:
            # Try to get structure from this event first. If the structure
            # exists, return it.
            value = super().__getattr__(attrname)
            if value is not None:
                return value
        except AttributeError:
            pass
        # No such structure or attribute is in this event, try to get it from
        # original event.
        return getattr(self.original_event, attrname)

    def __str__(self):
        display_name = self.run_subset.display_name + ' - ' if self.run_subset.display_name else ''
        return f'(subset) {display_name}{self.original_event}'

@api.events.register_structure('run_subset')
class RunSubsetStructure(BaseStructure):
    def __init__(self, settings, event, testplans=None, testplans_queries=None, testcases=None, testcases_queries=None, configurations=None, crc_queries=None, display_name=None):
        super().__init__(settings)
        self.event = event
        self.testplans = testplans
        self.testplans_queries = testplans_queries
        self.testcases = testcases
        self.testcases_queries = testcases_queries
        self.configurations = configurations
        self.crc_queries = crc_queries
        self.display_name = display_name

@api.cli.register_command_parser('run_subset')
def subset_command(base_parser, args):
    base_parser.add_argument(
        '--testplan', action='append',
        help='Execute only selected testplan.',
    )
    base_parser.add_argument(
        '--testplan-query', action='append',
        help='Execute only selected testplans complying to the query.',
    )
    base_parser.add_argument(
        '--testcase', action='append',
        help='Execute only selected testcase.',
    )
    base_parser.add_argument(
        '--testcase-query', action='append',
        help='Execute only selected testcases complying to the query.',
    )
    base_parser.add_argument(
        '--configuration', action='append', type=keys_values_sep(',', ':'),
        help='Execute only configurations containing specific key:value.',
    )
    base_parser.add_argument(
        '--crc-query', action='append',
        help='Execute only selected caseRunConfigurations complying to the query. The caseRunConfiguration is exposed as `crc` variable.',
    )
    base_parser.add_argument(
        '--display-name',
        help='Optional display name that will be added to the string representing the Event',
    )
    base_parser.add_argument(
        'command',
        choices=CliFactory.known_commands((None, 'pipeline', 'run_subset'))
    )
    options, _ = base_parser.parse_known_args(args)
    options, event_json = CliFactory.parse(options.command, args, base_parser)
    original_event = json.loads(event_json)
    event = {
        'type': 'run_subset',
        'run_subset': {
            'event': original_event,
            'testplans': options.testplan,
            'testplans_queries': options.testplan_query,
            'testcases': options.testcase,
            'testcases_queries': options.testcase_query,
            'configurations': options.configuration,
            'crc_queries': options.crc_query,
            'display_name': options.display_name,
        },
    }
    return options, json.dumps(event)
