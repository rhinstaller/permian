.. _usage library:


============
Test Library
============
Permian was developed together with tplib, a python library for managing test cases,
test plans, and requirements stored in yaml files. A test library is just git
repository or local directory that contains these yaml files.
Permian only realy cares about test plans and test cases. Requirements are mostly
only for organization of test cases and can be optionaly used during reporting.

If the test library is a git repository a branch is selected based on the event.
In settings there are options branchNameFormat and branchNameStrategy that define
how this is accomplished.

**branchNameStrategy** determines how to approach a situation when the desired branch
of the testplans library repository is not available.

- **exact-match** - This strategy uses the branchNameFormat and doesn't allow fallback
  to any other branch if the desired one is not available and fails.
- **drop-least-significant** - This strategy uses the branchNameFormat and if the
  desired branch is not available tries another branch names continuously dropping
  the least significat part of the version specification until branch of such name
  is found (success) or until there's nothing more to drop (failure).
  Example of branch names attempts is::

    Foo-1.2-3 -> Foo-1.2 -> Foo-1 -> Foo -> (failure)

**branchNameFormat** is Jinja2 template is used for branch name formatting where the
event as well as all event structures are provided as separate variables. For
example:: 

    {{event.product.name.lower()}}-{{event.product.major}}.{{event.product.minor}}.{{event.product.other}}.{{event.product.flag}}

Organization
^^^^^^^^^^^^
There’s no forced filesystem organization structure. Items in library are
destinguished by their filename suffix:

- Test plan ``.plan.yaml``
- Requirement ``.req.yaml``
- Test case ``.tc.yaml``

Recommended filesystem organization::

    ├── component
    │   ├── test_plans
    │   │   ├── some-testplan.plan.yaml
    │   │   └── ...
    │   ├── requirements
    │   │   ├── some-requirement.req.yaml
    │   │   └── ...
    │   └── test_cases
    │       ├── some-testcase.tc.yaml
    │       └── ...
    ├── other-component
    │   └── ...
    ├── reporting_templates
    │   └── ...
    └── pipeline.ini

tplib documentation
^^^^^^^^^^^^^^^^^^^
https://tplib.readthedocs.io
