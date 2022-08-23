from collections import OrderedDict

from ..exceptions import StateChangeError

UNSET = object()

STATES = OrderedDict((
    ('not started' , "Status of item for which no activity has started yet."),
    ('queued', "The execution haven't started yet, but execution is in queue."),
    ('started', "The execution has started and is performing setup activities."),
    ('running', "The execution has started and is running the test now."),
    ('cleaning', "The test has ended and cleanup activities are being done now."),
    ('canceled', "The execution was terminated prematurely."),
    ('complete', "The execution ended and should provide valid data."),
    ('DNF', "The execution was not able complete."),
))

RESULTS = OrderedDict((
    (None, 'No valid result is available.'),
    ('PASS', 'The test has passed.'),
    ('FAIL', 'The test has failed.'),
    ('ERROR', 'There was an error during the execution.'),
))

class Result():
    def __init__(self, state=None, result=None, final=False, dirty=True, **kwargs):
        if state not in STATES:
            raise ValueError('Unknown state: "%s"' % state)
        if result not in RESULTS:
            raise ValueError('Unknown result: "%s"' % result)
        self.state = state
        self.result = result
        self.final = final
        self.extra_fields = kwargs
        self.dirty = dirty

    def update(self, result):
        if self.final:
            raise StateChangeError('Cannot update status of already ended instance.')
        self.final = result.final
        if list(STATES).index(result.state) < list(STATES).index(self.state):
            raise StateChangeError(f'Cannot change state from "{self.state}" to "{result.state}".')
        self.state = result.state
        if list(RESULTS).index(result.result) > list(RESULTS).index(self.result):
            self.result = result.result
        self.extra_fields.update(result.extra_fields)
        self.dirty = True

    def copy(self):
        return Result(
            self.state, self.result, self.final, self.dirty, **self.extra_fields
        )

    def __eq__(self, other):
        if not isinstance(other, Result):
            raise NotImplementedError()
        return (
            self.state == other.state and
            self.result == other.result and
            self.final == other.final
        )

    def __repr__(self):
        return f'<Result({self.state}, {self.result}, {self.final}>'
