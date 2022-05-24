"""
TODO: Add information about possibilities to extend the pipeline. It should be categorized so that one can focus only on the area they want to extend.

The categories should go to individual api subpackages.
In each category, provide description about which tplib data is handled by the extension (in case of Workflow, ReportSender)

Workflows:

Provisioners:

ReportSenders:

ResultsProcessors:

Input events (triggers):
Note: Mention it's good to add CLI actions associated with the event (creating the event)

CommandLine:

Web UI:

Hooks:

"""

# expose all subpackages directly in api
from . import (
    cli,
    events,
    hooks,
    issueanalyzer,
    reportsenders,
    webui,
    workflows,
)

# TODO: Move to subpackage
def register_provisioner(name, provisioner_class=None):
    """
    Redirects to TODO

    Provisioners provide access to external resources such as systems, services
    or files stored on remote servers.
    """


# TODO: Move to subpackage
def register_resultsProcessor(name, resultsProcessor_class=None):
    """
    Redirects to TODO

    ResultsProcessors perform transformation of results possibly adding
    additional information based on external sources such as bugzilla or change
    state of the results.
    """
