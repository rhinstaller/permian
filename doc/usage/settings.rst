.. _usage settings:


=================
Pipeline settings
=================

The pipeline settings may be defined in following places (sorted in priority order):

- cmdline override
- environment variable
- ini files in tplib library
- ini files in provided locations
- default ini files of plugins
- default ini file of pipeline

----------------------
Command-line overrides
----------------------

Any setting can be overridden with command-line argument ``--override`` or ``-o`` in the format ``section.option=value``, eg.::

    -o "library.directPath=/home/user/test_library"

---------------------
Environment variables
---------------------

Settings can also be set as environment variables named ``PIPELINE_section_option``, eg.::

    PIPELINE_library_directPath=/home/user/test_library

--------------
Settings files
--------------

Settings ini files can be located in several places. During runtime these ini files are combined and
duplicate entries override each other based on the priority list above.

- Pipeline default settings ``libpermian/default.ini``
- Plugin default settings ``$plugin_directory/settings.ini``
- Settings file provided with cmdline option ``--settings`` or ``-s``
- tplib Library, any ``.ini`` file in the path
