"""
Events are describing the cause (or impulse) for the pipeline to start and
based on the event all the actions taken by the pipeline are taken. Some would
use instead of 'event' term 'trigger' but we're trying to avoid such term as it
can be used as both verb (to trigger the pipeline) and subjet (the trigger
started the pipeline).

One of the main functions of the events is to provide name of branch which
contains testplans that should be executed for such event instance.

Events may also provide additional information related to the event instance
where such information are taken from external sources. Example of such
functionality could be for example detecting product (and its version) for a
Koji build that's to be processed by the pipeline or information about packages
that are product of the build. Another example would be additional information
about compose such as label or compose type. These additional information may or
may not be used by the event itself when deciding the name of the testplans
branch.

The event that comes to the pipeline is json encoded mapping (dict) with 1
mandatory item "type" and optionally additional items which provide additional
information about the nature of the event or are used as overrides.
Resulting in json like::

  {
    'type' : 'explosion',
    'other' : {
      'items' : ['a', 'b', 'c'],
      'where' : 'underground'
    }
  }

In this case, the EventFactory looks for a class associated to the 'explosion'
event type and crates its object passing the type as first argument and all
other items as kwargs based on which corresponding event structures are created
(described below).

To define Event responsible for handling 'explosion' event type which
additionally provides information about exploded items following code would be
used::

  @libpermian.events.factory.register('explosion')
  class ExplosionEvent(libpermian.events.base.Event):
      pass

In case of providing the example explosion event to the pipeline as the impulse
for pipeline execution, the Pipeline would do something similar::

  from libpermian.events.factory import EventFactory

  branch_format = '{where}' # taken from settings
  event_string = '''{
    "type" : "explosion",
    "other" : {
      "items" : ["a", "b", "c"]
    }
  }'''
  event = EventFactory.make(settings, event_string)
  branch = event.format_branch_spec(branch_format)
  # pipeline would clone the git repository fetching the branch and proceed with next steps (passing the event along with tplib.Library and settings for the execution)

The event can also hold additional structures (like "other" shown above) which
are python objects created based on the content of the item which would be::

  {
    'items' : ['a', 'b', 'c'],
    'where' : 'underground'
  }

in case of::

  {
    'type' : 'explosion',
    'other' : {
      'items' : ['a', 'b', 'c'],
      'where' : 'underground'
    }
  }

The "other" structure can be accessed like regular object attribute using dot
operator like: ``event.other``. The structure is created by :py:method:`EventStructuresFactory.make` method which finds class associated to the name ("other")
and passes the content of the dict as kwargs to the event structure class
constructor.

The event structure classes are ordinary python classes and the only special
interfaces are ``__init__`` (where the event specification string structure
fields are defined by the arguments including mandatory fields by mandatory
arguments) and special to_* methods and from_* classmethods.

The to_* methods provide conversion mechanism (which is not provided by python
compared to e.g. C++) from one structure type to another. For example,
koji_build event structure could provide to_compose method which would return
new python object associated to "compose" event structure type based on the
koji_build structure effectively providing information which compose is related
to the koji build.

The from_* class methods provides conversion mechanism the other way allowing
to construct the desired structure based on some other already existing
structure. It has to be class method as there's the instance of the desired
type doesn't exist yet.

Both to_* and from_* can return NotImplemented instead of new object signalling
that for some reason, they cannot provide instance of the desired type for
whatever reason and other conversion methods are attempted (trying to create
the instance from different structure).

In case when the ``event.some_structure`` needs the conversion and no to_* or
from_* method provides instance None value is provided so that expressions like
``event.some_structure.value`` can be used in jinja expressions without raising
exception when some_structure is not available.
"""
from . import builtin # register builtin events
