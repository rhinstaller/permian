import unittest
from libpermian.events.factory import EventFactory
from libpermian.events.base import Event
from libpermian.events.builtin import UnknownEvent

class TestEvent(Event):
    pass

class Test2Event(Event):
    pass

class Test2FooEvent(Event):
    pass

class TestEventFactory(unittest.TestCase):
    OLD_EVENT_TYPES = []

    @classmethod
    def setUpClass(cls):
        cls.OLD_EVENT_TYPES = EventFactory.EVENT_TYPES.copy()
        EventFactory.register('test')(TestEvent)

    @classmethod
    def tearDownClass(cls):
        EventFactory.EVENT_TYPES = cls.OLD_EVENT_TYPES

    def setUp(self):
        event_string = '''{"type" : "test",
                           "other" : {"value" : "42"}}'''
        self.event = EventFactory.make(None, event_string)

    def test_registered(self):
        self.assertIs(TestEvent, EventFactory.EVENT_TYPES['test'])

    def test_structure(self):
        self.assertEqual(self.event.other['value'], "42")

    def test_format_branch_spec(self):
        branch = self.event.format_branch_spec('Answer is {{event.other["value"]}}')
        self.assertEqual(branch, 'Answer is 42')

class TestEventFactoryTypes(unittest.TestCase):
    OLD_EVENT_TYPES = []

    @classmethod
    def setUpClass(cls):
        cls.OLD_EVENT_TYPES = EventFactory.EVENT_TYPES.copy()
        EventFactory.register('test')(TestEvent)
        EventFactory.register('test2')(Test2Event)
        EventFactory.register('test2.foo')(Test2FooEvent)

    @classmethod
    def tearDownClass(cls):
        EventFactory.EVENT_TYPES = cls.OLD_EVENT_TYPES

    def test_correct_event(self):
        event = EventFactory.make(None, '{"type": "test"}')
        event2 = EventFactory.make(None, '{"type": "test2"}')
        event2foo = EventFactory.make(None, '{"type": "test2.foo"}')
        self.assertIsInstance(event, TestEvent)
        self.assertIsInstance(event2, Test2Event)
        self.assertIsInstance(event2foo, Test2FooEvent)

    def test_more_specific_event(self):
        event = EventFactory.make(None, '{"type": "test2.foo.bar"}')
        self.assertIsInstance(event, Test2FooEvent)

    def test_more_specific_event_fallback(self):
        event = EventFactory.make(None, '{"type": "test.bar"}')
        event2 = EventFactory.make(None, '{"type": "test2.bar"}')
        self.assertIsInstance(event, TestEvent)
        self.assertIsInstance(event2, Test2Event)

    def test_unknown_event(self):
        event = EventFactory.make(None, '{"type": "foo"}')
        self.assertIsInstance(event, UnknownEvent)
