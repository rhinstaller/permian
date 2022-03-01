import unittest

from libpermian.events.factory import EventFactory
from libpermian.settings import Settings


class TestEverythingEvent(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.settings = Settings(
            cmdline_overrides={},
            environment={},
            settings_locations=[],
        )

    def test_additional_testplan(self):
        event_string = '''
        {"type": "everything",
         "everything_testplan" : {
           "configurations": [{"architecture": "x86_64", "variant": "BaseOS"}],
           "point_person": "tester@example.com"
         }
        }'''

        event = EventFactory.make(self.settings, event_string)
        self.assertEquals(event.additional_testplans_data,
                          [{'name': 'Everything',
                              'point_person': 'tester@example.com',
                              'artifact_type': 'everything',
                              'verified_by': {'test_cases': {'query': 'true'}},
                              'configurations': [{"architecture": "x86_64", "variant": "BaseOS"}],
                              'reporting': [{'type': 'xunit'}],
                          }])

    def test_additional_testplan_reporting(self):
        event_string = '''
        {"type": "everything",
         "everything_testplan" : {
           "configurations": [{"architecture": "x86_64", "variant": "BaseOS"}],
           "point_person": "tester@example.com",
           "reporting": [{"type": "test", "data": {"filename": "reporting.txt"}}]
         }
        }'''
        event = EventFactory.make(self.settings, event_string)
        self.assertEquals(event.additional_testplans_data,
                          [{'name': 'Everything',
                            'point_person': 'tester@example.com',
                            'artifact_type': 'everything',
                            'verified_by': {'test_cases': {'query': 'true'}},
                            'configurations': [{"architecture": "x86_64", "variant": "BaseOS"}],
                            'reporting': [{"type": "test", "data": {"filename": "reporting.txt"}}],
                          }])
