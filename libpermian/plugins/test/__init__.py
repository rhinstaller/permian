import logging
import json
import re
from os import path
from time import sleep
from .. import api
from ...workflows.isolated import IsolatedWorkflow
from ...result import Result, STATES, RESULTS, UNSET
from ...events.base import Event 
from ...reportsenders.base import BaseReportSender
from ...issueanalyzer.base import BaseAnalyzer, BaseIssue
from ...issueanalyzer.issueset import IssueSet
from libpermian.events.structures.base import BaseStructure


LOGGER = logging.getLogger(__name__)


def decode_hex(string):
    """
    Decode hexdump string

    *string* must be an ASCII string describing binary data as
    hexadecimal bytes, ie. each line must have this form:

          BYTE [BYTE]..

    where each BYTE is a two-digit hexadecimal number.  Lines
    are joined before decoding.

    For example:

        >>> decode_hex('aa bb\ncc')
        b'\xaa\xbb\xcc'

    describes binary blob containing  three bytes: AA, BB and CC.
    """
    hexstr = ''
    for line in string.split('\n'):
        hexstr += ''.join(line.split())
    return bytes.fromhex(hexstr)


@api.cli.register_command_parser('test')
def test_command(base_parser, args):
    parser = base_parser
    parser.add_argument('--tp', action='append', required=True,
                        help='Name of testplan to execute - can be used multiple times')
    options = parser.parse_args(args)
    return options, json.dumps({'type': 'test', 'test': {'testplans': options.tp}})


@api.events.register_structure('test')
class TestStructure(BaseStructure):
    def __init__(self, settings, testplans):
        super().__init__(settings)
        self.testplans = testplans

@api.events.register('test')
class TestEvent(Event):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.selected_testplans = self.test.testplans


@api.workflows.register("test")
class TestWorkflow(IsolatedWorkflow):
    def __init__(self, testRuns, crcList):
        super().__init__(testRuns, crcList)
        self.status_step_counter = 0
        self.terminated = False

    def formatLogMessage(self, message):
        return self.logFormat.format(
            message=message,
            asctime=self.status_step_counter,
        )

    def execute(self):
        last_state = None
        # initial delay - to ensure specific order of results in reporting
        sleep(self.crc.configuration.get('initial_delay', 0) + (self.crc.configuration.get('test', 0) * 0.01))

        for num, step in enumerate(self.crc.testcase.execution.automation_data, start=1):
            self.log(f'Running step no {num}: {step}')
            if self.terminated: break
            self.status_step_counter = num
            state = step.get('state', last_state)
            result = step.get('result', None)
            final = step.get('final', False)

            if self.terminated: break
            if 'log' in step:
                for logname, message in step['log'].items():
                    self.log(f"Writing message to log: {logname}")
                    self.log(message, logname)

            if self.terminated: break
            if 'log_content' in step:
                for logname, content in step['log_content'].items():
                    self.log(f"Writing message to log: {logname}")
                    with self.crc.openLogfile(logname, 'w', True) as fo:
                        fo.write(content)

            if self.terminated: break
            if 'log_data' in step:
                name = step['log_data']['name']
                data = decode_hex(step['log_data']['data_hex'])
                filename = step['log_data'].get('filename')
                self.log(f"Writing data to log: {len(data)} bytes, name={name} filename={filename}")
                self.logData(data, name, filename=filename)

            if self.terminated: break
            if 'log_file' in step:
                for logname, log_path in step['log_file'].items():
                    self.log(f"Adding log {logname} pointing to: {log_path}")
                    self.addLog(logname, log_path)

            if self.terminated: break
            if 'sleep' in step:
                self.log(f"Sleeping: {step['sleep']}")
                sleep(step['sleep'])

            if self.terminated: break
            if {'state', 'result', 'final'}.intersection(step.keys()):
                self.log(f"Reporting Result({state}, {result}, {final})")
                self.reportResult(Result(state, result, final))
                last_state = state

    def terminate(self):
        self.terminated = True
        return True

    def displayStatus(self):
        return 'Processing step: ' + str(self.status_step_counter)


@api.reportsenders.register('test')
class TestReportSender(BaseReportSender):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.processing_log_filename = path.join(self.settings.get('testingPlugin', 'reportSenderDirectory'),
                                                 self.reporting.data.get('filename', re.sub(r'[^\w\d-]', '_', self.testplan.name)))
        if self.group is not None:
            self.processing_log_filename += f'-{self.group!r}'
        self.processing_log_file = None
        self.throttled_reporting = 0

    def setUp(self):
        self.processing_log_file = open(self.processing_log_filename, 'w')

    def tearDown(self):
        self.processing_log_file.close()

    def processPartialResult(self, crc):
        self.processing_log_file.write('reporter %s - result partial %s-%s - %s, %s, %s\n' % (self.reporting.data.get('reporter', 0),
            crc.testcase.name,
            crc.configuration.get('test', 0),
            crc.result.state, crc.result.result, crc.result.final))

    def processFinalResult(self, crc):
        self.processing_log_file.write('reporter %s - result final %s-%s - %s, %s->%s(%r), %s\n' % (self.reporting.data.get('reporter', 0),
            crc.testcase.name,
            crc.configuration.get('test', 0),
            crc.result.state, crc.result.result,
            self.resultOf([crc]), self.issuesFor([crc]),
            crc.result.final))

    def processTestRunStarted(self):
        self.processing_log_file.write('reporter %s - testrun "%s" started\n' % (self.reporting.data.get('reporter', 0),
            self.testplan.name))

    def processTestRunFinished(self):
        self.processing_log_file.write('reporter %s - testrun "%s" finished\n' % (self.reporting.data.get('reporter', 0),
            self.testplan.name))

    def processCaseRunFinished(self, testCaseID):
        self.processing_log_file.write('reporter %s - finished testcase "%s" in "%s"\n' % (self.reporting.data.get('reporter', 0),
            testCaseID, self.testplan.name))

    def flush(self):
        self.throttled_reporting += 1
        for crc in self.unprocessed_crcs:
            self.processing_log_file.write('reporter %s - throttled reporting %i crc %s-%s - %s, %s, %s\n' % (self.reporting.data.get('reporter', 0),
                self.throttled_reporting,
                crc.testcase.name,
                crc.configuration.get('test', 0),
                crc.result.state, crc.result.result, crc.result.final))
        return True

class TestIssue(BaseIssue):
    def __init__(self, settings, uri, report_url, resolved=None):
        super().__init__(settings)
        self.test_uri = uri or None
        self.test_report_url = report_url or None
        self.test_resolved = resolved in ("1", "t", "True", "true")

    def make(self):
        return f'new({self.uri or self.report_url})'

    def update(self):
        pass

    def _lookup(self):
        return self.test_uri

    @property
    def resolved(self):
        return self.test_resolved

    @property
    def report_url(self):
        return self.test_report_url

@api.issueanalyzer.register
class TestIssueAnalyzer(BaseAnalyzer):
    @staticmethod
    def analyze(analyzerProxy, caseRunConfiguration):
        for logname, logfile in caseRunConfiguration.logs.items():
            if not logname.startswith('testissue_'):
                continue
            with open(logfile) as logfile_fo:
                yield TestIssue(analyzerProxy.settings, *(x.rstrip('\n') for x in logfile_fo.readlines()))
