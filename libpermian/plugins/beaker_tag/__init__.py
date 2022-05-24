from tplib.expressions import eval_bool
from libpermian.reportsenders.base import BaseReportSender
from libpermian.plugins import api
from libpermian.plugins.beaker import xmlrpc_server
import xmlrpc.client
import subprocess
import logging
import jinja2


LOGGER = logging.getLogger(__name__)


@api.reportsenders.register('beaker-tag')
class BeakerTagReportSender(BaseReportSender):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ror = self.reporting.data.get('report-on-results', ['PASS'])

    def processPartialResult(self, crc):
        pass

    def processFinalResult(self, crc):
        pass

    def processTestRunStarted(self):
        pass

    def processTestRunFinished(self):
        env = jinja2.Environment(loader=jinja2.BaseLoader)
        tag_name = env.from_string(self.reporting.data.get('tag-name')).render(event=self.event, reporting=self)
        condition = 'True' if self.reporting.condition is None else self.reporting.condition

        if eval_bool(condition, event=self.event, reporting=self) and self.caseRunConfigurations.result in self.ror:
            self.set_tag(self.event.compose.id, tag_name)
        else:
            LOGGER.debug('Not reporting: condition or report-on-results did not match')

    def processCaseRunFinished(self, testCaseID):
        pass

    def set_tag(self, compose, tag):
        if not self.dry_run:
            try:
                beaker_xmlrpc = xmlrpc_server(self.settings)
                beaker_xmlrpc.distros.tag(compose, tag)
            except xmlrpc.client.Fault as e:
                LOGGER.error('Failed to set tag %s, due to: %s', tag, e)
                raise
            LOGGER.debug(f'Successfully set tag {tag} to compose {compose}')
        else:
            LOGGER.info(f'Setting tag {tag} to compose {compose}')
