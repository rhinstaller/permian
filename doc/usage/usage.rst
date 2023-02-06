.. _usage basic:

===========
Basic usage
===========

Dependencies
------------

- tplib https://github.com/rhinstaller/tplib/
- python3
  (python3-flask, python3-requests, python3-libxml2, python3-yaml, python3-magic,
  python3-pylint, python3-bugzilla, python3-productmd, python3-sphinx)
- git
- beaker-client
- diffutils

For up to date dependecies check ``Dockerfile``

Running Permian
----------------

The base commands for running Permian are ``pipeline`` and ``run_event``, other
commands are provided by plugins. The command name is detected based on the first
argument (name of the file from which the pipeline is executed) and corresponding
command parser is used for event generation and option parsing. Examples::

    ./pipeline run_event --settings pipeline.ini "event specification"
    ./run_event --settings pipeline.ini "event specification"

Plugins
^^^^^^^

Pipeline plugins are python packages that extend the functionality of the Permian
pipeline. Plugins can be located outside of the libpermian directory.

Some plugins may be disabled by default (empty ``DISABLED`` file in the plugin's directory).
Disabled plugins can be enabled with environment variable ``PIPELINEPLUGINS_ENABLE``, and plugins
enabled by default can be disabled with variable ``PIPELINEPLUGINS_DISABLE``. Plugin names
are separated with comma. ::

    PIPELINEPLUGINS_ENABLE=test PIPELINEPLUGINS_DISABLE=beaker,beaker_tag ./pipeline ...

**Additional plugins**

Permian can load aditional plugins from locations defined in environment variable
``PIPELINEPLUGINS_PATH``, paths are separated by colon::

    PIPELINEPLUGINS_PATH=../my_plugins/plugins/:/home/user/secret_plugins/ ./pipeline ...

If you are running pipeline in container, you have to specify paths inside the cotainer
and they have to be accessible there. Default ``./in_container`` script doesn't help with this.

Running only subsets of tests
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Just use run_subset command and specify desired limiting factors before the
original command (see ``./run_subset --help``). The resulting command line will look like::

    ./run_subset --configuration architecture:s390x -s pipeline.ini compose ...

To run a subset of tests verifying a specific requirement and filtering the list of test cases::

    ./run_subset --testcase-query '"installer" in tc.tags and "disabled" not in tc.tags and tc.priority < 9 and tc.execution.type != "manual" and "RHEL-8 Installation: Driverdisk" in tc.verifiesRequirement|map(attribute="name")' -s pipeline.ini compose ...

Dry run
^^^^^^^
Partial dry run, execute tests, but don't report the results::

    -o reportSenders.dry_run=True

Full dry run, don't execute tests and don't report results::

    -o workflows.dry_run=True -o reportSenders.dry_run=True


Local test library
^^^^^^^^^^^^^^^^^^
Running pipeline on local testplans library (e.g. on not committed or not merged changes)::

    -o library.directPath=./path/to/library

If you are running pipeline in container the library must be a subdirectory of the
permian (cwd) directory so that it is reachable inside the container.

Events
------
Events are describing the cause (or impulse) for the pipeline to start and
based on the event all the actions taken by the pipeline are taken.

One of the main functions of the events is to provide name of branch which
contains testplans that should be executed for such event instance.

Events may also require or provide additional information related to the event
instance where such information can be taken from external sources and is stored
in event structures.

Event structures
^^^^^^^^^^^^^^^^
Event structures store and provide additional data on the subject of the testing.
Additional data could be for example detecting product (and its version) for a
Koji build or information about packages that are product of the build. Another
example would be additional information about compose such as label or compose type.

Some structures can be converted to others. For example koji_build can be
converted to compose, if development compose for that build exists.

There is also event structure ``other`` that can store anything. But it is intended
mostly for testing porpuses.

Example of event::

    {
        'type': 'koji.build.tag',
        'koji_build': {
            'nvr': 'python-2.7.5-90.el7',
            'new_tag': 'gate',
            'build_id': 123456
        },
        'other' : {
            'items': ['a', 'b', 'c'],
            'where': 'underground'
        }
    }

Same event used with ``run_event`` command::

    ./pipeline run_event '{"type": "koji.build.tag", "koji_build": {"nvr": "python-2.7.5-90.el7", "new_tag": "gate", "build_id": 123456}, "other": {"items": ["a", "b", "c"], "where": "underground"}}'

Some plugins with events also define special commands that make it easier to use the events.
Same event but without the ``other`` event structure::

    ./koji_build_tag 'python-2.7.5-90.el7' 'gate' --build-id 123456

More information on events can be found in the :ref:`development section<dev events>`.

Running in container
--------------------

Permian comes with Dockerfile and scripts that make it easy to run it in container.
The container image is based on CentOS Stream 8 and contains all required dependencies.
Some plugins may require it, for example because of dependencies not available on
newer systems, others may need special settings or may not be compatible with running
inside of this container at all. So be carful and always test your setup in dry-run mode first.

- To build the container image with tag 'permian' run::

    ./build_container

- To execute any command in this container run::

    ./in_container your_cmmand

Limitations of in_container script / podman approach
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Simple concurrent execution of in_container script leads to IO errors and permission denials

As the ``in_container`` script executes podman container with current directory mounted to the
container, execution of multiple container instances with the same directory mounted multiple
times results in IO errors.

Concurrent execution of permian with the same work directory may lead to overwriting results
data (xunit files, logs, webui dump, ...). This can be avoided by using different work
directory for separate executions. It's advised to create a new directory for each permian
run to have separated result sets.

Accessing WebUI
---------------

Dynamic port
^^^^^^^^^^^^

When the pipeline starts running a message about WebUI URL availability should show up::

    INFO:libpipeline.webui.callbacks(Thread-2):WebUI started at: http://10.0.2.100:63323/

When running the pipeline in container the IP address is unfortunately not reachable,
but the port should be exposed, so you should be able to see the WebUI by visiting
following URL http://localhost:63323/ (where the port corresponds with the one in the message)

Static port
^^^^^^^^^^^


A static WebUI port can be set using ``PIPELINE_WebUI_listen_port`` environment variable.
You can have it exported either in your .bashrc file or in your shell session of when
running the pipeline like::

    PIPELINE_WebUI_listen_port=9999 ./in_container ./pipeline ...

When the pipeline is started via the in_container script, the static port can be defined
only by the environment variable because the port is published by podman and it has to be
known before the pipeline is started. If the port would be set using -o command line
argument (or in pipeline settings file), the in_container script would not be aware of
this and would publish different port effectively making the WebUI unreachable.

Updates, cleaning, changes
--------------------------

As both permian and tclib are still developed, it may be good to monitor their development
and it's definitely good to keep them updated when running the pipeline locally.

Updating permian
^^^^^^^^^^^^^^^^

To keep the permian code updated, just update the cloned permian git repository by using
regular git commands (pull, fetch, reset ...) and re-build the container image,
if you are using it.

Updating tplib and other bits
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

If you are using the container image, tplib is inside and simple re-build will update it.
Otherwise same as permian, just update the cloned tplib git repository.

Note that tplib, ksbuild and other libraries don't change so often and they mostly just
add support for new data or fix some corner case scenario issues, this update may be
needed only once things start behaving unexpectedly.

Cleaning mess permian made
^^^^^^^^^^^^^^^^^^^^^^^^^^
(traceback dumps, WebUI dumped files, logs, xunit files)

When you run permian locally (even in the container using in_container script) no matter
if it was executed regular way or in dry_run mode, the pipeline will produce a lot of
files in the working (permian) directory. To get rid of those files, simply run
following command::

    make clean

Trying own changes of permian
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

When running the in_container script, the pipeline code that's actually executed is
taken from the working directory, so you may just modify the code (or checkout to
other branch) the way you want and then test your changes by just running the pipeline
as documented above.
