import logging
import jinja2
from time import time

from libpermian.plugins import api
from libpermian.reportsenders.base import BaseReportSender

LOGGER = logging.getLogger(__name__)

@api.reportsenders.register('stdout')
class stdoutReportSender(BaseReportSender):
    """ Report sender that shows the current state of crcs in the info log / stdout """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.interval_timer = 0
        self.throttleInterval = int(self.settings.get('stdout', 'throttleInterval'))

        def setlen(input, length):
            string = str(input)[:length]
            addnum = length - len(string)
            return string + ' ' * addnum

        jinja_pkg_env = jinja2.Environment(loader=jinja2.PackageLoader('libpermian.plugins.stdout', 'templates'))
        jinja_pkg_env.filters['setlen'] = setlen
        self.template = jinja_pkg_env.get_template('table80.j2')

    def show_report(self):
        if self.interval_timer > time():
            return
        self.interval_timer = int(time()) + self.throttleInterval

        report_table = self.template.render(crcs=self.caseRunConfigurations,
                                            tp=self.testplan)
        LOGGER.info(f'\n{report_table}')

    def processPartialResult(self, crc):
        self.show_report()

    def processFinalResult(self, crc):
        self.show_report()

    def processTestRunStarted(self):
        self.show_report()

    def processTestRunFinished(self):
        self.show_report()

    def processCaseRunFinished(self, testCaseID):
        self.show_report()

    def flush(self):
        self.show_report()
        return True