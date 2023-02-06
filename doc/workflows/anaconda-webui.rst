Anaconda WebUI Testing Workflow
===============================

Workflow for running Anaconda WebUI integration tests.

Requirements
------------

- Testing framework, taken from anaconda, cockpit, cockpit-project/bots git repositories. Configured in settings.
- Test scripts, taken from anaconda or other git repository. Configured in settings.
- QEMU Virtualization hypervisor/s. Configured in settings.
- Event structure InstallationSourceStructure, this is what is going to be tested.
  It can be obtained by conversion from compose structure or supplied directly::
  
    {
        "base_repo_id": "BaseOS",
        "repos": {
            "BaseOS": {
                "x86_64": {
                    "os": "http://example.com/compose/x86_64/BaseOS/os",
                    "kernel": "images/pxeboot/vmlinuz",
                    "initrd": "images/pxeboot/initrd.img"
                }
            }
        }
    }


Settings
--------

Examples can be found in `default settings file <https://github.com/rhinstaller/permian/blob/devel/libpermian/plugins/anaconda_webui/settings.ini>`_.

AnacondaWebUI
^^^^^^^^^^^^^
- **anaconda_repo** - URL to Anaconda git repository or path to local directory (use file://)
- **cockpit_repo** - URL to Cockpit git repository, if anaconda_repo is local directory and
  ``anaconda/ui/webui/test/common`` exists, this repo won't be used.
- **cockpit_branch** - Cockpit git branch
- **bots_repo** - URL to Cockpit Bots git repository, if anaconda_repo is local directory and
  ``anaconda/ui/webui/bots`` exists, this repo won't be used.
- **bots_branch** - Cockpit Bots git branch
- **hypervisor_vm_limit** - How many VMs can this workflow use at once
- **use_container** - Run npm command and the test itself inside podman container.
- **port_ssh** - SSH port used for connection to the VM where Anaconda is running.
- **port_webui** - Port used for connection to the Anaconda WebUI
- **webui_location** - Part of URL where WebUI should be accessible.
- **webui_startup_timeout** - Timeout in minutes for Anaconda WebUI to start after the VM gets IP
- **webui_ssl_verify** - Verify SSL certificate used by Anaconda WebUI
- **debug** - If true VMs is not removed at the end of the test

VMHypervisors
^^^^^^^^^^^^^
Hypervisor hostnames or IPs, one for each supported architecture.
Use `qemu:///system` for local hypervisor.

AnacondaWebUIRepos
^^^^^^^^^^^^^^^^^^
Dictionary of git repositories with additional test scripts.

AnacondaWebUIkernelCmdline
^^^^^^^^^^^^^^^^^^^^^^^^^^
Additional arguments for kernel cmdline, one for each supported architecture and
one added to all architectures.

Usage
-----

Testcase
^^^^^^^^
Execution type of this workflow is ``anaconda-webui``. Required automation_data
are:

- **script_file** - path to the test script, by default the base for this path
  is anaconda git repository
- **test_case** - python class in the script file (test script file can contain 
  multiple test cases)

Optional automation_data:

- **test_repo** - Name of repository where the test script is located. Repositories
  are defined in AnacondaWebUIRepos settings section. Sets the base path for script_file.
- **additional_repos** - List of additional repos for installation (``inst.addrepo``), eg. ``['AppStream', 'CRB']``.
  These need to be supplied by InstallationSource event structure.
- **kernel_cmdline** - Parameters to be added to kernel cmdline.
- **webui_startup_timeout** - Override how long to wait for WebUI to start (in minutes).

Example of minimal execution section for running test from anaconda repo::

    execution:
        type: anaconda-webui
        automation_data:
            script_file: ./ui/webui/test/integration/default.py
            test_case: DefaultInstallation

Example of execution section with all options set::

    execution:
        type: anaconda-webui
        automation_data:
            script_file: ./check-navigation.py
            test_case: TestNavigation
            test_repo: my-special-tests
            additional_repos: ['AppStream', 'CRB']
            kernel_cmdline: 'nosmt'
            webui_startup_timeout: 15

Hypervisor
^^^^^^^^^^
The workflow is using virtual machines, so it needs access to a system with libvirtd running.
Currently only local hypervisor is supported.

Test scripts
^^^^^^^^^^^^
Anaconda WebUI integration tests are python scripts that use cockpit's test framework
and wrapper methods that make it easy to interact with the Web UI and run commands
on the machine during installation and after reboot.

More information can be found in `Anaconda documentation <https://anaconda-installer.readthedocs.io/en/latest/testing.html#anaconda-web-ui-tests>`_.

Execution
---------

Run tests from Anaconda repostiory
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

1. Follow the guide on page :ref:`Quick start<Quick start>` and get Permian
   running without an container.

2. Clone Anaconda repository, we are going to use the testplan library from it::

    git clone -–depth 1 https://github.com/rhinstaller/anaconda.git

3. Get URL for the compose or unpacked boot iso that you want to test. For now you can use
   https://fedorapeople.org/groups/anaconda/webui_permian_tests/sources/periodic/x86_64/,
   currently it is updated manually and should work with tests in the Anaconda master branch.

4. To run the 'WebUI Integration daily preview' test plan use github.scheduled.preview event,
   the default Permian settings should work, the only other thing that needs to be specified
   is InstallationSource event structure.::
   
    PYTHONPATH=./tplib ./pipeline run_event \
      -o "library.directPath=../anaconda/ui/webui/test/integration/" \
      '{"type": "github.scheduled.preview",
        "InstallationSource": {
          "base_repo_id": "bootiso",
          "repos": {
            "bootiso": {
              "x86_64": {
                "os": "https://fedorapeople.org/groups/anaconda/webui_permian_tests/sources/periodic/x86_64/",
                "kernel": "images/pxeboot/vmlinuz",
                "initrd": "images/pxeboot/initrd.img"
              }
            }
          }
        }
       }' < /dev/null

  .. note::
    The `< /dev/null` at the end is there because of `issue 65 <https://github.com/rhinstaller/permian/issues/65>`_.
