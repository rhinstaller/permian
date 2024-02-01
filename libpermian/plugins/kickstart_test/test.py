import unittest
import os
import copy
import shutil
from textwrap import dedent

from libpermian.testruns import TestRuns
from libpermian.events.base import Event
from libpermian.settings import Settings
from libpermian.exceptions import UnsupportedConfiguration
from libpermian.plugins.kickstart_test import SUPPORTED_ARCHITECTURES, \
    KstestParamsStructure, MissingBootIso, MissingInformation, KickstartTestWorkflow

from tplib.library import Library

DUMMY_BOOT_ISO_URL = "file:///tmp/boot.iso"

OUTPUT_DUMP_FILE = "output.txt"
OUTPUT_DUMP_FILE_REGULAR = "kstest.daily-iso.stripped.log.txt"
OUTPUT_DUMP_FILE_MISSING = "kstest.daily-iso.stripped.log.missing.result.txt"
OUTPUT_DUMP_FILE_UNEXPECTED = "kstest.daily-iso.stripped.log.unexpected.result.txt"

EXPECTED_RESULTS = {
    OUTPUT_DUMP_FILE_REGULAR: {
        'authselect-not-set': ('complete', 'FAIL', True),
        'clearpart-1': ('complete', 'PASS', True),
        'container': ('complete', 'PASS', True),
        'keyboard-convert-vc': ('complete', 'PASS', True),
        'lang': ('complete', 'PASS', True),
        'packages-multilib': ('complete', 'FAIL', True),
        'selinux-permissive': ('complete', 'PASS', True),
        'services': ('complete', 'PASS', True),
    }
}


class TestFakeMissingPlatformEvent(Event):
    def __init__(self, settings, event_type='kstest-poc'):
        super().__init__(
            settings,
            event_type,
            bootIso={
                'x86_64': DUMMY_BOOT_ISO_URL,
            },
        )


class TestFakeMissingBootIsoEvent(Event):
    def __init__(self, settings, event_type='kstest-poc'):
        super().__init__(
            settings,
            event_type,
            kstestParams={
                'platform': "rhel8",
            },
        )


class TestFakeMinimalEvent(Event):
    def __init__(self, settings, event_type='kstest-poc'):
        super().__init__(
            settings,
            event_type,
            kstestParams={
                'platform': "rhel8",
            },
            bootIso={
                'x86_64': DUMMY_BOOT_ISO_URL,
            },
        )

class TestFakeKstestParamsOnly(Event):
    def __init__(self, settings, event_type='kstest-poc'):
        super().__init__(
            settings,
            event_type,
            kstestParams={
                'platform': "rhel9",
                'urls': {
                    'x86_64': {
                        'installation_tree': 'http://example.org/the-rhel-9/compose/BaseOS/x86_64/os'
                    }
                }
            }
        )

class TestFakeScenariosEventRhel9(Event):
    def __init__(self, settings, event_type='github.scheduled.daily.kstest.rhel9'):
        super().__init__(
            settings,
            event_type,
            bootIso={
                'x86_64': DUMMY_BOOT_ISO_URL,
            },
            kstestParams={
                'platform': "rhel9",
                'urls': {
                    'x86_64': {
                        'installation_tree': 'http://example.org/the-rhel-9/compose/BaseOS/x86_64/os',
                        'modular_url': 'http://example.org/the-rhel-9/compose/AppStream/x86_64/os',
                        'ftp_url': 'ftp://example.org/the-rhel-9/compose/BaseOS/x86_64/os'
                    }
                }
            },
        )


class TestFakeScenariosEventDailyiso(Event):
    def __init__(self, settings, event_type='github.scheduled.daily.kstest.daily-iso'):
        super().__init__(
            settings,
            event_type,
            bootIso={
                'x86_64': DUMMY_BOOT_ISO_URL,
            },
            kstestParams={
                'platform': "fedora_rawhide",
                'urls': {
                    'x86_64': {
                        'installation_tree': 'http://dl.fedoraproject.org/pub/fedora/linux/development/rawhide/Everything/$basearch/os/',
                        'modular_url': 'http://dl.fedoraproject.org/pub/fedora/linux/development/rawhide/Modular/$basearch/os/',
                        'metalink': 'https://mirrors.fedoraproject.org/metalink?repo=fedora-$releasever&arch=$basearch',
                        'mirrorlist': 'https://mirrors.fedoraproject.org/mirrorlist?repo=fedora-$releasever&arch=$basearch',
                        'ftp_url': 'ftp://ftp.tu-chemnitz.de/pub/linux/fedora/linux/development/rawhide/Everything/$basearch/os/',
                    }
                }
            },
        )


class TestKickstartTestWrorkflow(unittest.TestCase):
    """Basic test with dummy / noop launcher."""
    @classmethod
    def setUpClass(cls):
        cls.library = Library('./tests/test_library/kickstart-test/basic')
        cls.settings = Settings(
            cmdline_overrides={
                'kickstart_test': {
                    'runner_command': "echo containers/runner/launch",
                    'kstest_local_repo': "/tmp/mockrepo",
                },
            },
            environment={},
            settings_locations=[],
        )

    def setUp(self):
        self._ensure_file_exists(DUMMY_BOOT_ISO_URL[7:])

    def _ensure_file_exists(self, path):
        if not os.path.isfile(path):
            with open(path, 'w'):
                pass

    def testWorkflowRun(self):
        event = TestFakeMinimalEvent(self.settings)
        testRuns = TestRuns(self.library, event, self.settings)
        executed_workflows = set()
        for caseRunConfiguration in testRuns.caseRunConfigurations:
            with self.subTest(caseRunConfiguration=caseRunConfiguration):
                if id(caseRunConfiguration.workflow) not in executed_workflows:
                    caseRunConfiguration.workflow.run()
                    executed_workflows.add(id(caseRunConfiguration.workflow))
        self.assertEqual(len(executed_workflows), 1)

    def testParamsOnlyWorkflowRun(self):
        event = TestFakeKstestParamsOnly(self.settings)
        testRuns = TestRuns(self.library, event, self.settings)
        executed_workflows = set()
        for caseRunConfiguration in testRuns.caseRunConfigurations:
            with self.subTest(caseRunConfiguration=caseRunConfiguration):
                if id(caseRunConfiguration.workflow) not in executed_workflows:
                    caseRunConfiguration.workflow.run()
                    executed_workflows.add(id(caseRunConfiguration.workflow))
        self.assertEqual(len(executed_workflows), 1)

    def testMissingBootIsoWorkflowRun(self):
        event = TestFakeMissingBootIsoEvent(self.settings)
        testRuns = TestRuns(self.library, event, self.settings)
        executed_workflows = set()
        for caseRunConfiguration in testRuns.caseRunConfigurations:
            with self.subTest(caseRunConfiguration=caseRunConfiguration):
                if id(caseRunConfiguration.workflow) not in executed_workflows:
                    caseRunConfiguration.workflow.run()
                    executed_workflows.add(id(caseRunConfiguration.workflow))
        self.assertEqual(len(executed_workflows), 1)

    def testMissingBootIsoWorkflowException(self):
        event = TestFakeMissingBootIsoEvent(self.settings)
        testRuns = TestRuns(self.library, event, self.settings)
        executed_workflows = set()
        for caseRunConfiguration in testRuns.caseRunConfigurations:
            with self.subTest(caseRunConfiguration=caseRunConfiguration):
                if id(caseRunConfiguration.workflow) not in executed_workflows:
                    caseRunConfiguration.workflow.silent_exceptions = ()
                    with self.assertRaises(MissingBootIso):
                        caseRunConfiguration.workflow.run()
                    executed_workflows.add(id(caseRunConfiguration.workflow))

    def testMissingPlatformWorkflowException(self):
        event = TestFakeMissingPlatformEvent(self.settings)
        testRuns = TestRuns(self.library, event, self.settings)
        executed_workflows = set()
        for caseRunConfiguration in testRuns.caseRunConfigurations:
            with self.subTest(caseRunConfiguration=caseRunConfiguration):
                if id(caseRunConfiguration.workflow) not in executed_workflows:
                    with self.assertRaises(MissingInformation):
                        caseRunConfiguration.workflow.run()
                    executed_workflows.add(id(caseRunConfiguration.workflow))

    def testUnsupportedArchWorkflowRun(self):
        event = TestFakeMinimalEvent(self.settings, event_type="kstest-unsupported-arch")
        testRuns = TestRuns(self.library, event, self.settings)
        executed_workflows = set()
        for caseRunConfiguration in testRuns.caseRunConfigurations:
            with self.subTest(caseRunConfiguration=caseRunConfiguration):
                if id(caseRunConfiguration.workflow) not in executed_workflows:
                    if caseRunConfiguration.workflow.arch not in SUPPORTED_ARCHITECTURES:
                        with self.assertRaises(UnsupportedConfiguration) as uc:
                            caseRunConfiguration.workflow.setup()
                    else:
                        caseRunConfiguration.workflow.run()
                        executed_workflows.add(id(caseRunConfiguration.workflow))
        self.assertEqual(len(executed_workflows), 1)

    def testMissingArchWorkflowRun(self):
        event = TestFakeMinimalEvent(self.settings, event_type="kstest-missing-arch")
        testRuns = TestRuns(self.library, event, self.settings)
        executed_workflows = set()
        for caseRunConfiguration in testRuns.caseRunConfigurations:
            with self.subTest(caseRunConfiguration=caseRunConfiguration):
                if id(caseRunConfiguration.workflow) not in executed_workflows:
                    caseRunConfiguration.workflow.run()

    def testWorkflowWithPlatformRun(self):
        event = TestFakeMinimalEvent(self.settings)
        testRuns = TestRuns(self.library, event, self.settings)
        executed_workflows = set()
        for caseRunConfiguration in testRuns.caseRunConfigurations:
            with self.subTest(caseRunConfiguration=caseRunConfiguration):
                if id(caseRunConfiguration.workflow) not in executed_workflows:
                    caseRunConfiguration.workflow.run()
                    executed_workflows.add(id(caseRunConfiguration.workflow))
        self.assertEqual(len(executed_workflows), 1)


class TestKickstartTestWorkflowResultsParsing(unittest.TestCase):
    """Test parsing of results from output supplied by mocked launcher."""
    @classmethod
    def setUpClass(cls):
        library_rel_path = './tests/test_library/kickstart-test/results_parsing'
        cls.library_abs_path = os.path.join(os.getcwd(), library_rel_path)
        mock_launcher_path = os.path.join(cls.library_abs_path, "launch-mock.py")
        output_dump_path = os.path.join(cls.library_abs_path, OUTPUT_DUMP_FILE)

        cls.library = Library(library_rel_path)
        cls.settings = Settings(
            cmdline_overrides={
                'kickstart_test': {
                    'runner_command': "%s %s 1000 0" %
                    (mock_launcher_path, output_dump_path),
                    'kstest_local_repo': "/tmp/mockrepo",
                    'retry_on_failure': True,
                },
            },
            environment={},
            settings_locations=[],
        )
        cls.event = TestFakeMinimalEvent(cls.settings)

    def setUp(self):
        self.testRuns = TestRuns(self.library, self.event, self.settings)
        self._ensure_file_exists(DUMMY_BOOT_ISO_URL[7:])

    def _ensure_file_exists(self, path):
        if not os.path.isfile(path):
            with open(path, 'w'):
                pass

    def _run_with_expected_result(self, expected_result):
        executed_workflows = set()
        for caseRunConfiguration in self.testRuns.caseRunConfigurations:
            with self.subTest(caseRunConfiguration=caseRunConfiguration):
                if id(caseRunConfiguration.workflow) not in executed_workflows:
                    caseRunConfiguration.workflow.run()
                    executed_workflows.add(id(caseRunConfiguration.workflow))
        for caseRunConfiguration in self.testRuns.caseRunConfigurations:
            result = caseRunConfiguration.result
            self.assertEqual(
                (result.state, result.result, result.final),
                expected_result[caseRunConfiguration.testcase.name]
            )

    def _prepare_output_dump_file(self, dump_file):
        shutil.copyfile(
            os.path.join(self.library_abs_path, dump_file),
            os.path.join(self.library_abs_path, OUTPUT_DUMP_FILE),
        )

    def testResultsParsingRun(self):
        """Check individual test results parsed from output."""
        self._prepare_output_dump_file(OUTPUT_DUMP_FILE_REGULAR)
        self._run_with_expected_result(EXPECTED_RESULTS[OUTPUT_DUMP_FILE_REGULAR])

    def testResultsParsingRunWithUnexpectedResult(self):
        """Check individual test results parsed from output with unexpected result.

        The output contains test results of a test which is not in the test plan.
        """
        self._prepare_output_dump_file(OUTPUT_DUMP_FILE_UNEXPECTED)
        self._run_with_expected_result(EXPECTED_RESULTS[OUTPUT_DUMP_FILE_REGULAR])

    def testResultsParsingRunWithMissingResult(self):
        """Check individual test results parsed from output with missing result.

        The output is missing results of a test from the test plan.
        """
        self._prepare_output_dump_file(OUTPUT_DUMP_FILE_MISSING)
        expected_results = copy.copy(EXPECTED_RESULTS[OUTPUT_DUMP_FILE_REGULAR])
        expected_results['keyboard-convert-vc'] = ('running', None, False)
        self._run_with_expected_result(expected_results)


class TestInstallationUrlStructureProcessing(unittest.TestCase):
    """Test processing of installation url event structure."""

    DEFAULTS_FILE_TEMPLATE = """
{kstest_url}
{kstest_metalink}
{kstest_mirrorlist}
{kstest_ftp_url}
{kstest_modular_url}
    """

    cases = [
        (
            KstestParamsStructure(
                None,
                platform="",
                urls={
                    'x86_64': {
                        'installation_tree': "http://dl.fedoraproject.org/pub/fedora/linux/development/rawhide/Everything/x86_64/os/",
                        'some_url': "http://some.url.org",
                    }
                }
            ),
            # content of the override defaults file
            DEFAULTS_FILE_TEMPLATE.format(
                kstest_url="export KSTEST_URL=http://dl.fedoraproject.org/pub/fedora/linux/development/rawhide/Everything/x86_64/os/",
                kstest_metalink="",
                kstest_mirrorlist="",
                kstest_ftp_url="",
                kstest_modular_url="",
            ),
        ),
        (
            # empty values should result in no file created
            KstestParamsStructure(
                None,
                platform="",
                urls={
                    'x86_64': {
                        'installation_tree': "",
                        'modular_url': "",
                    }
                }
            ),
            None,
        ),
        (
            # empty values should result in no file created
            KstestParamsStructure(
                None,
                platform="",
                urls={},
            ),
            None,
        ),
        (
            KstestParamsStructure(
                None,
                platform="",
                urls={
                    'x86_64': {
                        'installation_tree': 'http://dl.fedoraproject.org/pub/fedora/linux/development/rawhide/Everything/$basearch/os/',
                        'metalink': 'https://mirrors.fedoraproject.org/metalink?repo=fedora-$releasever&arch=$basearch',
                        'mirrorlist': 'https://mirrors.fedoraproject.org/mirrorlist?repo=fedora-$releasever&arch=$basearch',
                        'modular_url': 'http://dl.fedoraproject.org/pub/fedora/linux/development/rawhide/Modular/$basearch/os/',
                        'ftp_url': 'ftp://ftp.tu-chemnitz.de/pub/linux/fedora/linux/development/rawhide/Everything/$basearch/os/',
                    }
                }
            ),
            DEFAULTS_FILE_TEMPLATE.format(
                kstest_url="export KSTEST_URL=http://dl.fedoraproject.org/pub/fedora/linux/development/rawhide/Everything/$basearch/os/",
                kstest_metalink="export KSTEST_METALINK=https://mirrors.fedoraproject.org/metalink?repo=fedora-$releasever&arch=$basearch",
                kstest_mirrorlist="export KSTEST_MIRRORLIST=https://mirrors.fedoraproject.org/mirrorlist?repo=fedora-$releasever&arch=$basearch",
                kstest_ftp_url="export KSTEST_FTP_URL=ftp://ftp.tu-chemnitz.de/pub/linux/fedora/linux/development/rawhide/Everything/$basearch/os/",
                kstest_modular_url="export KSTEST_MODULAR_URL=http://dl.fedoraproject.org/pub/fedora/linux/development/rawhide/Modular/$basearch/os/",
            ),
        ),
        (
            KstestParamsStructure(
                None,
                platform="",
                urls={
                    'x86_64': {},
                    'aarch64': {
                        'installation_tree': "http://dl.fedoraproject.org/pub/fedora/linux/development/rawhide/Everything/aarch64/os/",
                    },
                }
            ),
            DEFAULTS_FILE_TEMPLATE.format(
                kstest_url="",
                kstest_metalink="",
                kstest_mirrorlist="",
                kstest_ftp_url="",
                kstest_modular_url="",
            ),
        ),
    ]

    @classmethod
    def setUpClass(cls):
        cls.library = Library('./tests/test_library/kickstart-test/basic')
        cls.settings = Settings(
            cmdline_overrides={
                'kickstart_test': {
                    'runner_command': "echo containers/runner/launch",
                    'kstest_local_repo': "/tmp/mockrepo",
                },
            },
            environment={},
            settings_locations=[],
        )
        cls.event = TestFakeMinimalEvent(cls.settings)

    def setUp(self):
        self.testRuns = TestRuns(self.library, self.event, self.settings)
        self._ensure_file_exists(DUMMY_BOOT_ISO_URL[7:])

    def _ensure_file_exists(self, path):
        if not os.path.isfile(path):
            with open(path, 'w'):
                pass

    def _check_result(self, workflow, urls, expected_result):
        fpath = workflow.process_installation_urls(urls)
        if expected_result is None:
            self.assertIsNone(fpath)
        else:
            content = ""
            if fpath:
                with open(fpath, "r") as f:
                    content = f.read()
                os.unlink(fpath)
            self.assertEqual(dedent(expected_result.strip()), dedent(content.strip()))

    def testWorkflowRun(self):
        executed_workflows = set()
        self.assertEqual(len(self.testRuns.caseRunConfigurations), 1)
        workflow = self.testRuns.caseRunConfigurations[0].workflow
        for kstest_params_struct, expected_result in self.cases:
            self._check_result(workflow, kstest_params_struct.urls, expected_result)


class TestKickstartTestScenarios(unittest.TestCase):
    """Test with example of scenarios defined in test plans."""
    @classmethod
    def setUpClass(cls):
        cls.library = Library('./tests/test_library/kickstart-test/scenarios')
        cls.settings = Settings(
            cmdline_overrides={
                'kickstart_test': {
                    'runner_command': "echo containers/runner/launch",
                    'kstest_local_repo': "/tmp/mockrepo",
                },
            },
            environment={},
            settings_locations=[],
        )

    def setUp(self):
        self._ensure_file_exists(DUMMY_BOOT_ISO_URL[7:])

    def _ensure_file_exists(self, path):
        if not os.path.isfile(path):
            with open(path, 'w'):
                pass

    def _check_scenario_event(self, event, expected_num_of_crcs):
        self.testRuns = TestRuns(self.library, event, self.settings)
        self.assertEqual(len(self.testRuns.caseRunConfigurations), expected_num_of_crcs)
        executed_workflows = set()
        for caseRunConfiguration in self.testRuns.caseRunConfigurations:
            with self.subTest(caseRunConfiguration=caseRunConfiguration):
                if id(caseRunConfiguration.workflow) not in executed_workflows:
                    caseRunConfiguration.workflow.run()
                    executed_workflows.add(id(caseRunConfiguration.workflow))
        self.assertEqual(len(executed_workflows), 1)

    def testScenarioRhel9Run(self):
        """Test multiple platform configurations in test plan."""
        event = TestFakeScenariosEventRhel9(self.settings)
        self._check_scenario_event(event, 4)

    def testScenarioRhelDailyiso(self):
        """Test multiple platform configurations in test plan."""
        event = TestFakeScenariosEventDailyiso(self.settings)
        self._check_scenario_event(event, 3)

class TestParamsToBootIso(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.library = Library('./tests/test_library/kickstart-test/basic')
        cls.settings = Settings(
            cmdline_overrides={},
            environment={},
            settings_locations=[],
        )

    def testConversion(self):
        event = TestFakeKstestParamsOnly(self.settings)
        testRuns = TestRuns(self.library, event, self.settings)
        kstest_workflow = KickstartTestWorkflow(testRuns, [], 'x86_64')
        kstest_workflow.setup()
        self.assertAlmostEqual(kstest_workflow.boot_iso_url, 'http://example.org/the-rhel-9/compose/BaseOS/x86_64/os/images/boot.iso')

    def testNoConversion(self):
        event = TestFakeMinimalEvent(self.settings)
        testRuns = TestRuns(self.library, event, self.settings)
        kstest_workflow = KickstartTestWorkflow(testRuns, [], 'x86_64')
        kstest_workflow.setup()
        self.assertAlmostEqual(kstest_workflow.boot_iso_url, DUMMY_BOOT_ISO_URL)

    def testParamsPriority(self):
        event = TestFakeScenariosEventDailyiso(self.settings)
        testRuns = TestRuns(self.library, event, self.settings)
        kstest_workflow = KickstartTestWorkflow(testRuns, [], 'x86_64')
        kstest_workflow.setup()
        self.assertAlmostEqual(kstest_workflow.boot_iso_url, DUMMY_BOOT_ISO_URL)

class TestSupportedSettings(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.library = Library('./tests/test_library/kickstart-test/basic')
        cls.settings = Settings(
            cmdline_overrides={},
            environment={},
            settings_locations=['./tests/test_library/kickstart-test/test-settings.ini']
        )

    def testSupportedSettingsParsing(self):
        event = TestFakeMinimalEvent(self.settings)
        testRuns = TestRuns(self.library, event, self.settings)
        kstest_workflow = KickstartTestWorkflow(testRuns, [], 'x86_64')
        self.assertEqual(kstest_workflow.runner_command, ["runner_cmd", "arg1", "arg2"])
        self.assertEqual(kstest_workflow.boot_opts, "inst.xtimeout=100 inst.sshd=1")
        self.assertEqual(kstest_workflow.retry, False)
        self.assertEqual(kstest_workflow.timeout, "0")
        self.assertEqual(kstest_workflow.ksrepo,
                         "https://github.com/rhinstaller/kickstart-tests.git")
        self.assertEqual(kstest_workflow.ksrepo_branch, "master")
        self.assertEqual(kstest_workflow.ksrepo_local_dir, "/var/tmp/kickstart-tests")
        self.assertEqual(kstest_workflow.updates_img,
                         "http://cobra02/users/rv/updates.getmac.img")
