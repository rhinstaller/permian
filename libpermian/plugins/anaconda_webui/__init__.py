import tempfile
import subprocess
import os
import shutil
import json
import time
import logging
import threading
import ssl
import re
import errno
import urllib.request
import urllib.error
import urllib.parse
import libpermian.plugins.anaconda_webui.commands

from libpermian.plugins import api
from libpermian.result import Result
from libpermian.workflows.isolated import IsolatedWorkflow
from libpermian.events.structures.base import BaseStructure
from libpermian.plugins.compose import ComposeStructure
from libpermian.exceptions import StructureConversionError
from libpermian.plugins.anaconda_webui.execution_container import ExecutionContainer
from libpermian.plugins.anaconda_webui.hypervisor import Hypervisor

from flask import url_for
import libpermian.webui.builtin

LOGGER = logging.getLogger(__name__)


class AnacondaWebUISetupError(Exception):
    pass


@api.events.register_structure('InstallationSource')
class InstallationSourceStructure(BaseStructure):
    """ Structure with URLs and paths needed for compose installation

    Example:
    {"base_repo_id": "BaseOS",
     "repos": {"BaseOS": {"x86_64": {"os": "http://example.com/compose/x86_64/BaseOS/os",
                                     "kernel": "images/pxeboot/vmlinuz",
                                     "initrd": "images/pxeboot/initrd.img"},
                          "aarch64": {"os": "http://example.com/compose/aarch64/BaseOS/os",
                                      "kernel": "images/pxeboot/vmlinuz",
                                      "initrd": "images/pxeboot/initrd.img"}},
               "AppStream": {"x86_64": {"os": "http://example.com/compose/x86_64/AppStream/os"},
                             "aarch64": {"os": "http://example.com/compose/aarch64/AppStream/os"}}},
    }
    """
    def __init__(self, settings, base_repo_id, repos):
        super().__init__(settings)
        self.base_repo_id = base_repo_id
        self.repos = repos

        if self.base_repo_id not in self.repos.keys():
            raise ValueError(f'Invalid structure data, {base_repo_id} not in repos')

    @property
    def base_repo(self):
        return self.repos[self.base_repo_id]

    def kernel_path(self, arch):
        return self.repos[self.base_repo_id][arch].get('kernel')

    def initrd_path(self, arch):
        return self.repos[self.base_repo_id][arch].get('initrd')

    @classmethod
    def from_compose(cls, compose):
        """ Conversion method from ComposeStructure """
        settings = compose.settings

        if compose.product in ['RHEL']:
            base_repo_id = 'BaseOS'
        elif compose.product in ['Fedora']:
            base_repo_id = 'Everything'
        else:
            raise StructureConversionError(ComposeStructure,
                    InstallationSourceStructure,
                    f'Product "{compose.product}" not supported')

        repos = dict()
        for variant in compose.composeinfo.metadata.info.get_variants():
            repos[variant.id] = dict()
            for arch, os_path in variant.paths.os_tree.items():
                repos[variant.id][arch] = {'os': os_path}
                # Add information about kornel and initrd location to base repo
                if variant.id == base_repo_id:
                    repos[base_repo_id][arch]['kernel'] = compose.composeinfo.kernel_path(base_repo_id, arch)
                    repos[base_repo_id][arch]['initrd'] = compose.composeinfo.initrd_path(base_repo_id, arch)

        return cls(settings, base_repo_id, repos)


@api.workflows.register('anaconda-webui')
class AnacondaWebUIWorkflow(IsolatedWorkflow):
    """ Runs Anaconda WebUI unit and integration tests in virtual machine.

    Required configurations:
        branch: master    # Anaconda git repo branch - source of testing framework and upstream tests
        architecture: x86_64

    Automation data:
        script_file: ./check-navigation   # Path to file with the test case, relative to test_repo root
        test_case: TestNavigation       # Test case name
        # Optional
        test_repo: my-webui-tests    # Repository where the test is located, default anaconda
        additional_repos: ['AppStream', 'CRB']  # Additional repos for installation
        kernel_cmdline: 'nosmt'     # Additional kernel cmdline arguments
        webui_startup_timeout: 10   # Time to wait for WebUI to start, in minutes
    """

    instances = {}
    temp_dirs = {}
    npm_dependencies = ('chrome-remote-interface', 'sizzle')

    @classmethod
    def factory(cls, testRuns, crcList):
        """
        Make separate instances of this workflow for given crcIds.

        Also create Semaphore that will limit the number of VMs running at once
        and threading lock used for setup and teardown

        :param crcIds: List of CaseRunConfiguration which belong to this workflow.
        :type crcIds: list
        """
        vm_limit = testRuns.settings.getint('AnacondaWebUI', 'hypervisor_vm_limit')
        vm_semaphore = threading.Semaphore(vm_limit)
        setup_lock = threading.Lock()

        for singleCrcList in crcList.by_key(lambda x: x.id).values():
            cls(testRuns, singleCrcList, setup_lock, vm_semaphore)

    def __init__(self, testRuns, crcList, setup_lock, vm_semaphore):
        super().__init__(testRuns, crcList)
        self.installation_source = self.event.InstallationSource
        self.vm_semaphore = vm_semaphore
        self.setup_lock = setup_lock
        self.vm_name = f'anaconda-webui-{hash(self.crc)}'
        self.re_browser_snapshot = re.compile('\d+-snapshot-.*\.(png|html)')
        self.test_system_ip = None
        self.last_log = ''
        self.use_container = self.settings.getboolean('AnacondaWebUI', 'use_container')
        self.architecture = self.crc.configuration.get('architecture')
        self.webui_ssl_verify = self.settings.getboolean('AnacondaWebUI', 'webui_ssl_verify')
        self.debug = self.settings.getboolean('AnacondaWebUI', 'debug')
        self.test_timeout = self.settings.getint('AnacondaWebUI', 'test_timeout')

        self.git_anaconda_repo = self.settings.get('AnacondaWebUI', 'anaconda_repo')
        self.git_anaconda_branch = self.crc.configuration['branch']
        self.git_cockpit_repo = self.settings.get('AnacondaWebUI', 'cockpit_repo')
        self.git_cockpit_branch = self.settings.get('AnacondaWebUI', 'cockpit_branch')
        self.git_bots_repo = self.settings.get('AnacondaWebUI', 'bots_repo')
        self.git_bots_branch = self.settings.get('AnacondaWebUI', 'bots_branch')

        self.port_ssh = self.settings.get('AnacondaWebUI', 'port_ssh')
        self.port_webui = self.settings.get('AnacondaWebUI', 'port_webui')
        self.webui_location = self.settings.get('AnacondaWebUI', 'webui_location')

        automation_data = self.crc.testcase.execution.automation_data

        self.test_script_file = automation_data['script_file']
        self.test_case_name = automation_data['test_case']

        self.test_repo_dir = None
        self.test_repo_name = automation_data.get('test_repo')
        if self.test_repo_name:
            self.test_repo_url = self.settings.get('AnacondaWebUIRepos', self.test_repo_name)

        self.additional_repos = automation_data.get('additional_repos')

        self.kernel_cmdline = automation_data.get('kernel_cmdline')
        self.kernel_cmdline_settings_all = self.settings.get('AnacondaWebUIkernelCmdline', 'ALL')
        self.kernel_cmdline_settings_arch = self.settings.get('AnacondaWebUIkernelCmdline', self.architecture)

        self.webui_startup_timeout = automation_data.get(
            'webui_startup_timeout',
            self.settings.getint('AnacondaWebUI', 'webui_startup_timeout'),
        )

        try:
            self.hypervisor = Hypervisor(self.settings.get('VMHypervisors', self.architecture))
        except KeyError:
            self.hypervisor = None

    def setup(self):
        # Check if we have hypervisor for specified architecture
        if not self.hypervisor:
            raise AnacondaWebUISetupError('No hypervisor for {self.architecture} in settings')

        clone_common = False

        # Only one Anaconda WebUI workflow can run setup at a time, testcases
        # share container image, and if they use the same anaconda branch, also
        # temporary directory with testing framework and test scripts
        self.log('Waiting for setup lock', show=True)
        with self.setup_lock:
            if self.canceled:
                return
            self.log('Running setup', show=True)

            if self.use_container:
                self.log('Building container image for Anaconda WebUI tests, see container-build.txt')
                with self.crc.openLogfile('container-build.txt', 'w', True) as container_build_log:
                    self.container = ExecutionContainer(container_build_log)

            # Add self to instances using this branch setup
            if self.git_anaconda_branch in self.instances:
                self.instances[self.git_anaconda_branch].append(self)
            else:
                self.instances[self.git_anaconda_branch] = [self]

            # Create temporary directory for this branch setup - if it doesn't exists
            if self.git_anaconda_branch not in self.temp_dirs.keys():
                self.temp_dirs[self.git_anaconda_branch] = tempfile.TemporaryDirectory(dir='/var/tmp/', prefix="pipeline_awebui_")
                clone_common = True

            self.temp_dir = self.temp_dirs[self.git_anaconda_branch].name
            self.anaconda_dir = os.path.join(self.temp_dir, 'anaconda')
            self.webui_dir = os.path.join(self.anaconda_dir, 'ui/webui')

            if self.test_repo_name:
                self._clone_test_repo()

            # Clone common repositories
            if clone_common:
                self._clone_common()
                self._get_npm_dependecies()

            self.hypervisor.setup()

        self.test_workdir = self.anaconda_dir # CWD where the test is going to run
        if self.test_repo_name:
            self.test_workdir = self.test_repo_dir

        # Start VM
        self.log('Waiting for VM slot', show=True)
        self.vm_semaphore.acquire()
        if self.canceled:
            return
        self.reportResult(Result('started', None, False))

        if not self.dryRun:
            self._start_vm()
            self.log('Waiting for IP', show=True)
            vm_ip = self.hypervisor.wait_for_ip(self.vm_name)

            if self.hypervisor.remote:
                # Configure port forwarding
                self.port_ssh, self.port_webui = self.hypervisor.configure_forwarding(vm_ip, [self.port_ssh, self.port_webui])
                # After port forwarding the VM is access via localhost / host of the container
                self.test_system_ip = 'host.containers.internal' if self.use_container else 'localhost'
                self.webui_url = f'http://localhost:{self.port_webui}{self.webui_location}'
            else:
                self.test_system_ip = vm_ip
                self.webui_url = f'http://{vm_ip}:{self.port_webui}{self.webui_location}'

            # Wait for WebUI to start
            self._wait_for_webui()

    def dry_execute(self):
        self.log(f'Dry-run: {self.test_script_file}, {self.test_case_name}')
        self.reportResult(Result('complete', 'PASS', True))

    def execute(self):
        if self.canceled:
            return

        self.log(f'Running test {self.test_case_name}')
        # Copy dynamic log file with test report
        self.addLog('report.html', os.path.join(os.path.dirname(__file__), 'report.html'), copy_file=True)
        self.reportResult(Result('running', None, False))

        cmd = [self.test_script_file, self.test_case_name,
               '--browser', f'{self.test_system_ip}:{self.port_webui}',
               '--machine', f'{self.test_system_ip}:{self.port_ssh}']
        
        self.log('Running: ' + ' '.join(cmd))

        test_env = {'WEBUI_TEST_DIR': os.path.abspath(os.path.join(self.webui_dir, 'test'))}
        test_output = self.crc.openLogfile('output.txt', 'w', True)

        time.sleep(10) # Workaround, there is a race-condition, where WebUI is accessible but /run/anaconda/bus.address doesn't exist yet
        if self.use_container:
            cont_cwd = self.test_workdir.replace(self.temp_dir, '/root/workdir')
            test_env['WEBUI_TEST_DIR'] = test_env['WEBUI_TEST_DIR'].replace(self.temp_dir, '/root/workdir')
            process = self.container.popen(cmd, self.temp_dir, env=test_env, cwd=cont_cwd, stdout=test_output)
        else:
            process = subprocess.Popen(cmd, cwd=self.test_workdir, env=test_env, stdout=test_output, stderr=subprocess.STDOUT)

        # Wait for test to finish
        test_timeout = time.time() + self.test_timeout * 60

        while time.time() < test_timeout:
            try:
                process.wait(1)
                self.log('Test finished', show=True)
                break
            except subprocess.TimeoutExpired:
                self._collect_test_logs()
        else:
            # Test didn't end before timeout
            process.terminate()
            try:
                process.wait(10)
            except subprocess.TimeoutExpired:
                # Kill if it is still running
                process.kill()
                try:
                    process.wait(1)
                except subprocess.TimeoutExpired:
                    LOGGER.error('Test didn\'t end before timeout, and couldn\'t be killed')
            self.log('Test timeout', show=True)

        if process.returncode != 0:
            self.reportResult(Result('complete', 'FAIL', True))
        else:
            self.reportResult(Result('complete', 'PASS', True))

    def teardown(self):
        self.log('Teardown', show=True)
        try:
            self._collect_test_logs(True)
        except Exception as e:
            LOGGER.error(e)

        if not self.dryRun and not self.debug:
            # Kill VM - this should stop virt-install
            self.hypervisor.stop_vm(self.vm_name)

            try:
                # Wait for virt-install to end
                self.proc_virtinstall.wait(10)
            except subprocess.TimeoutExpired:
                # Terminate virt-install if it is still running
                self.proc_virtinstall.terminate()
                LOGGER.error('virt-install didn\'t end after virsh destroy')
                try:
                    # Wait for virt-install to end
                    self.proc_virtinstall.wait(10)
                except subprocess.TimeoutExpired:
                    # Kill virt-install if it is still running
                    self.proc_virtinstall.kill()
                    try:
                        self.proc_virtinstall.wait(1)
                    except subprocess.TimeoutExpired:
                        LOGGER.error('virt-install kill didn\'t work')

            # Close virt-install log
            self.virt_install_log.close()

            # Remove VM
            self.hypervisor.remove_vm(self.vm_name)
        
        # Stop port forwarding
        if self.hypervisor.remote:
            self.hypervisor.forwarding_cleanup()

        self.vm_semaphore.release()

        with self.setup_lock:
            # If this instance is the last one using temp dir -> remove it
            self.instances[self.git_anaconda_branch].remove(self)
            if len(self.instances[self.git_anaconda_branch]) == 0:
                self.temp_dirs[self.git_anaconda_branch].cleanup()
                
                del self.instances[self.git_anaconda_branch]
                # Remove container image, if this was the last anacoda-webui workflow
                if not self.instances:
                    self.container.remove_image()

    def terminate(self):
        if not self.dryRun:
            # Kill VM
            self.hypervisor.stop_vm(self.vm_name)

    def log(self, message, name='workflow', show=False):
        if name == 'workflow' and show:
            self.last_log = message
        super().log(message, name)

    def displayStatus(self):
        if self.crc.result.state == 'running':
            return f'[Test report]({url_for("main.logs", crcid=self.crc.id, name="report.html")})'
        return self.last_log

    @property
    def canceled(self):
        return self.crc.result.state == 'canceled'

    def _start_vm(self):
        """ Prepare virt-install command and start VM """
        self.log('Starting VM', show=True)

        # Get compose location
        os_url = self.installation_source.base_repo[self.architecture]['os']
        if (self.installation_source.kernel_path(self.architecture) and
            self.installation_source.initrd_path(self.architecture)):
            location = f'{os_url},kernel={self.installation_source.kernel_path(self.architecture)},initrd={self.installation_source.initrd_path(self.architecture)}'
        else:
            location = os_url

        # Construct kernel cmdline for --extra-args
        kernel_cmdline = f'inst.sshd inst.webui inst.webui.remote inst.graphical console=ttyS0 inst.stage2={os_url}'
        if self.additional_repos:
            for repo in self.additional_repos:
                kernel_cmdline += f' inst.addrepo={repo},{self.installation_source.repos[repo][self.architecture]["os"]}'

        if self.kernel_cmdline:
            kernel_cmdline += f' {self.kernel_cmdline}'
        if self.kernel_cmdline_settings_all:
            kernel_cmdline += f' {self.kernel_cmdline_settings_all}'
        if self.kernel_cmdline_settings_arch:
            kernel_cmdline += f' {self.kernel_cmdline_settings_arch}'

        # Assemble virt-install command
        cmd = ['virt-install', '--connect', self.hypervisor.qemu_host, '--autoconsole', 'text',
            '-n', self.vm_name, '--os-variant', 'rhel-unknown', '--location', location,
            '--memory', '4096', '--vcpus', '2', '--disk', 'size=10', '--serial', 'pty',
            '--extra-args', kernel_cmdline]

        self.virt_install_log = self.crc.openLogfile('virt-install', 'wb', True)

        LOGGER.info('Running: ' + repr(cmd))
        self.proc_virtinstall = subprocess.Popen(cmd, stdout=self.virt_install_log, stderr=subprocess.STDOUT)

    def _wait_for_webui(self):
        """ Wait for WebUI to be accessible

        Connection refused or reset are expected before the WebUI starts,
        any other error is going to be reraised.
        """
        self.log('Waiting for WebUI', show=True)
        startup_timeout = self.webui_startup_timeout*60 + time.time()
        LOGGER.debug(f'Expexted WebUI URL: {self.webui_url}')

        ssl_context = ssl.create_default_context()
        if not self.webui_ssl_verify:
            ssl_context.check_hostname=False
            ssl_context.verify_mode=ssl.CERT_NONE

        while True:
            if startup_timeout < time.time():
                self._take_vm_screenshot('screenshot_webui_not_accessible.ppm')
                raise AnacondaWebUISetupError('WebUI Connection refused, timeout')
            if self.canceled:
                break
            time.sleep(10)
            try:
                urllib.request.urlopen(self.webui_url, context=ssl_context)
            except (urllib.error.URLError, ConnectionResetError) as e:
                if isinstance(e, urllib.error.URLError) and e.reason.errno == errno.ECONNREFUSED:
                    # Connection refused - webui not yet started
                    continue
                elif isinstance(e, ConnectionResetError):
                    # Connection reset -  webui not yet started in case of port forwarding
                    continue
                else:
                    self._take_vm_screenshot('screenshot_webui_not_accessible.ppm')
                    raise e
            else:
                break

    def _take_vm_screenshot(self, name):
        """ Creates screenshot of VMs screen

        :param name: screenshot filename
        :type name: str
        """
        with tempfile.NamedTemporaryFile() as screenshot_tempfile:
            self.hypervisor.virsh_call(['screenshot', self.vm_name, screenshot_tempfile.name])
            self.addLog(name, screenshot_tempfile.name, copy_file=True)

    def _clone_repo(self, repo, branch, dir):
        """ Clones git repository

        :param repo: Repository URL
        :type repo: str
        :param branch: Branch name
        :type branch: str
        :param dir: Directory where the repo should be cloned
        :type dir: str
        """
        git_cmd = ['git', 'clone', '--depth', '1', '-b', branch, repo, dir]
        LOGGER.debug('Running: ' + repr(git_cmd))
        subprocess.check_call(git_cmd)

    def _clone_test_repo(self):
        """ Clones test repository with the same branch used for anaonda repo, if test repo doesn't already exist """
        self.test_repo_dir = os.path.join(self.temp_dir, self.test_repo_name)
        if  not os.path.isdir(self.test_repo_dir):
            self.log(f'Clonning test repo {self.test_repo_url}')
            self._clone_repo(self.test_repo_url, self.git_anaconda_branch, self.test_repo_dir)

    def _clone_common(self):
        """ Clones repositories common to all Anaconda WebUI tests """
        self.log(f'Clonning common repositories')
        bots_dir = os.path.join(self.webui_dir, 'bots')
        cockpit_common_dir = os.path.join(self.anaconda_dir, 'ui/webui/test/common')
        parsed_anaconda_url = urllib.parse.urlparse(self.git_anaconda_repo)

        if parsed_anaconda_url.scheme == 'file':
            # Create copy of anaconda repo
            shutil.copytree(parsed_anaconda_url.path, self.anaconda_dir, symlinks=True, ignore_dangling_symlinks=True)
        else:
            # clone anaconda
            self._clone_repo(self.git_anaconda_repo, self.git_anaconda_branch, self.anaconda_dir)

        if not os.path.exists(cockpit_common_dir):
            with tempfile.TemporaryDirectory() as temp_dir:
                # clone cockpit/test/common
                self._clone_repo(self.git_cockpit_repo, self.git_cockpit_branch, temp_dir)
                shutil.move(os.path.join(temp_dir, 'test/common'),
                            cockpit_common_dir)

        if not os.path.exists(bots_dir):
            # clone bots
            self._clone_repo(self.git_bots_repo, self.git_bots_branch, bots_dir)

    def _get_npm_dependecies(self):
        """ Get node.js dependecies

        Downloads only packages required for running tests,
        in the versions specified in WebUIs package.json.
        """
        with open(os.path.join(self.webui_dir, 'package.json')) as package_fo:
            npm_package = json.load(package_fo)

        self.log(f'Installing NPM dependencies')
        npm_command = ['npm', 'install', '--no-save']
        for dep in self.npm_dependencies:
            version = npm_package['devDependencies'][dep]
            npm_command.append(f'{dep}@{version}')

        with tempfile.TemporaryDirectory() as temp_dir:
            if self.use_container:
                proc = self.container.exec(npm_command, temp_dir, volume_mode='Z')
                if proc.returncode != 0:
                    raise AnacondaWebUISetupError('Error while downloading npm dependencies')
            else:
                subprocess.check_call(npm_command, cwd=temp_dir)

            shutil.move(os.path.join(temp_dir, 'node_modules'),
                        os.path.join(self.webui_dir, 'node_modules'))

    def _collect_test_logs(self, final=False):
        """ Collects logs generated by the WebUI test """
        for file in sorted(os.listdir(self.test_workdir)):
            # log new snapshots made by the test
            if re.match(self.re_browser_snapshot, file) and file not in self.crc.logs:
                self.addLog(file, os.path.join(self.test_workdir, file), copy_file=True)

        if not final:
            return

        test_logs_dir = os.path.join(self.test_workdir, 'test_logs', self.test_case_name)

        if not os.path.isdir(test_logs_dir):
            self.log('No log files generated')
            return

        for file in os.listdir(test_logs_dir):
            self.log(f'Adding log file {file}')
            self.addLog(file, os.path.join(test_logs_dir, file), copy_file=True)
