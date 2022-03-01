from libpermian.plugins import api
from libpermian.events.base import Event
from libpermian.events.structures.builtin import BaseStructure


@api.events.register('everything')
class EverythingEvent(Event):
    def __init__(self, settings, type, everything_testplan, **kwargs):
        super().__init__(settings, type, everything_testplan=everything_testplan, **kwargs)

    def __str__(self):
        return 'EverythingEvent'

    @property
    def additional_testplans_data(self):
        """ Returns artifical testplan that is verified by all testcases """
        tp_data = {'name': 'Everything',
                   'point_person': self.everything_testplan.point_person,
                   'artifact_type': 'everything',
                   'verified_by': {'test_cases': {'query': 'true'}},
                   'configurations': self.everything_testplan.configurations,
                   'reporting': self.everything_testplan.reporting,
                  }

        return [tp_data]

    def filter_testPlans(self, library):
        """ Always returns Everything testplan """
        return [library.testplans['Everything']]

@api.events.register_structure('everything_testplan')
class EverythingTestPlanStructure(BaseStructure):
    def __init__(self, settings, configurations, point_person, reporting=None):
        self.configurations = configurations
        self.point_person = point_person
        self.reporting = reporting if reporting is not None else [{'type': 'xunit'}]
