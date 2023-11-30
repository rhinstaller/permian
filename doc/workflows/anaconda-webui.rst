Anaconda WebUI Testing Workflow
===============================

Workflow for running Anaconda WebUI integration tests. Examples on how to easily
use this workflow to run WebUI tests are at the end of this document.

Requirements
------------

Managed by workflow
^^^^^^^^^^^^^^^^^^^

- Testing framework, taken from anaconda, cockpit, cockpit-project/bots git repositories.
  The location and exact version to be used is configured in settings of the workflow.
- Test scripts, taken from anaconda or other git repository. Other test repositories are
  configured in settings and information where each test script is located is in tplib
  test cases.

Managed by user
^^^^^^^^^^^^^^^
- QEMU Virtualization hypervisor/s. Either local or remove hypervisor with ssh access
  can be used.
- Event structure InstallationSourceStructure or bootIso, this is what is going to be tested.
  Both can be obtained by conversion from compose structure or supplied directly::
  
    "InstallationSource": {
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

  or::

    "bootIso": {
        "x86_64": "/path/to/boot.iso"
    }


Settings
--------

Examples can be found in `default settings file <https://github.com/rhinstaller/permian/blob/devel/libpermian/plugins/anaconda_webui/settings.ini>`_.

AnacondaWebUI
^^^^^^^^^^^^^
- **webui_repo** - URL to anaconda-webui git repository or path to local directory (use file://)
- **cockpit_repo** - URL to Cockpit git repository, if webui_repo is local directory and
  ``./test/common`` exists, this repo won't be used.
- **cockpit_branch** - Cockpit git branch
- **bots_repo** - URL to Cockpit Bots git repository, if webui_repo is local directory and
  ``./bots`` exists, this repo won't be used.
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
Use `localhost` or `user@hostname`.

AnacondaWebUIRepos
^^^^^^^^^^^^^^^^^^
Dictionary of git repositories with additional test scripts.

AnacondaWebUIkernelCmdline
^^^^^^^^^^^^^^^^^^^^^^^^^^
Additional arguments for kernel cmdline, one for each supported architecture and
one added to all architectures.

Usage
-----

Test case
^^^^^^^^^
Execution type of this workflow is ``anaconda-webui``. Required automation_data
are:

- **script_file** - path to the test script, by default the base for this path
  is anaconda git repository
- **test_case** - python class and method in the script file (test script file
  can contain multiple test cases)

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
            script_file: ./test/check-progress
            test_case: TestInstallationProgress.testBasic

Example of execution section with all options set::

    execution:
        type: anaconda-webui
        automation_data:
            script_file: ./check-navigation.py
            test_case: TestNavigation.testInstall
            test_repo: my-special-tests
            additional_repos: ['AppStream', 'CRB']
            kernel_cmdline: 'nosmt'
            webui_startup_timeout: 15

..  _hypervisor:

Hypervisor
^^^^^^^^^^
The workflow is using virtual machines, so it needs access to a system with libvirtd running.
That can be eighter localhost or remote system accessible via ssh. To prepare the system to
be used by this workflow: 

1. Install `libvirt` and `qemu-kvm` packges
2. Start `libvirtd` service.
3. Make sure the system can be accessed by permian without password (set authorized_keys for selected user).
4. If the user is not root, add it to the group `libvirt`.


Test scripts
^^^^^^^^^^^^
Anaconda WebUI integration tests are python scripts that use cockpit's test framework
and wrapper methods that make it easy to interact with the Web UI and run commands
on the machine during installation and after reboot.

More information can be found in `Anaconda documentation <https://anaconda-installer.readthedocs.io/en/latest/testing.html#anaconda-web-ui-tests>`_.

Execution
---------

Run a test case from local anaconda repo
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

We have special command that make this the easiest way to run WebUI test.

1. Follow the guide on page :ref:`Quick start<Quick start>` and get Permian
   running without an container.
2. By default your system will be used as :ref:`hypervisor`,
   so make sure libvirtd is running and you are in the libvirt group.
3. Clone anaconda repository next to Permian repo (the exact location is not
   important but following commands use this path)::

    git clone https://github.com/rhinstaller/anaconda.git

4. (optional) create new test case and test script file in the anaconda repository
   we just cloned.

   1. Create new file `anaconda-webui/test/test_cases/my_new_test.tc.yaml` with
      following content::

        name: My new test
        description: Short description of the test case
        author: your e-mail here
        tags:
          - anaconda
        priority: 1
        execution:
          type: anaconda-webui
          automation_data:
            script_file: ./test/my_new_test.py
            test_case: MyNewTest.testMethod
        instructions:
          steps:
            - step: Describe your test steps here

   2. Create your test script in `anaconda-webui/test/my_new_test.py`

5. Run the new test case::

    PYTHONPATH=../tplib ./pipeline run_awebui_tc ../anaconda-webui 'My new test'

  .. note::
    This command makes sure your local anaconda-webui repository is used as the source of the
    test script. Usually Permian clones its own copy of the anaconda-webui repository.

Run test plan from Anaconda-webui repo
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

1. Follow the guide on page :ref:`Quick start<Quick start>` and get Permian
   running without an container.
2. By default your system will be used as :ref:`hypervisor`, so make sure libvirtd is running.
3. Clone Anaconda-webui repository, we are going to use the testplan library from it::

    git clone https://github.com/rhinstaller/anaconda-webui.git

  .. note::
    In this case the test scripts are going to be sourced separetly by the workflow.
    Any changes made to the test code in this copy of the repository are not going to take effect.

4. Get URL for the compose or unpacked boot iso that you want to test. For now you can use
   https://fedorapeople.org/groups/anaconda/webui_permian_tests/sources/periodic/x86_64/,
   currently it is updated manually and should work with tests in the Anaconda master branch.
5. To run the 'WebUI Integration daily preview' test plan use github.scheduled.preview event,
   the default Permian settings should work, the only other thing that needs to be specified
   is InstallationSource event structure.::

    PYTHONPATH=../tplib ./pipeline run_event \
      -o "library.directPath=../anaconda-webui/test/test_cases/" \
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
