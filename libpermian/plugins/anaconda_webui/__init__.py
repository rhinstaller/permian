import tempfile
import subprocess
import os
import shutil
import json
import time
import logging
import threading
import ssl
import urllib.request
import urllib.error
import urllib.parse

from libpermian.plugins import api
from libpermian.result import Result
from libpermian.workflows.isolated import IsolatedWorkflow
from libpermian.events.structures.base import BaseStructure
from libpermian.plugins.compose import ComposeStructure
from libpermian.exceptions import StructureConversionError


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


class ExecutionContainer():
    """ Handles creation, removal of container image and running commands in it """
    def __init__(self):
        # Initialization of ExecutionContainer is not thread safe and is expected to be done only once in setup_lock
        self.image_name = 'anaconda-webui'

        img = subprocess.check_output(['podman', 'images', '-q', '-f', f'reference={self.image_name}']).decode()
        if img == '':
            containerfile = os.path.join(os.path.dirname(__file__), 'Containerfile')
            subprocess.check_call(['podman', 'build', '-f', containerfile, '-t', self.image_name])

    def exec(self, cmd, volume, env={}, cwd='/root/workdir', volume_mode='z', log_error=True):
        # Workaround for https://github.com/containers/podman/issues/15789
        # volume_mode should be 'O' but that doesn't work when workdir is in it
        env_params = []
        for key, val in env.items():
            env_params += ['-e', f'{key}={val}']

        podman_cmd = ['podman', 'run', '--rm', '-it',
                      '-v', f'{volume}:/root/workdir:{volume_mode}',
                      '-w', cwd] + env_params + ['anaconda-webui'] + cmd

        LOGGER.debug('Running: ' + repr(podman_cmd))
        proc = subprocess.run(podman_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

        if proc.returncode != 0 and log_error:
            LOGGER.error(proc.stdout.decode())

        return proc

    def remove_image(self):
        subprocess.check_call(['podman', 'rmi', self.image_name])


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
        self.vm_ip = None
        self.last_log = ''
        self.use_container = self.settings.getboolean('AnacondaWebUI', 'use_container')
        self.architecture = self.crc.configuration.get('architecture')
        self.webui_ssl_verify = self.settings.getboolean('AnacondaWebUI', 'webui_ssl_verify')
        self.debug = self.settings.getboolean('AnacondaWebUI', 'debug')

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
            self.hypervisor_host = self.settings.get('VMHypervisors', self.architecture)
        except KeyError:
            self.hypervisor_host = None

    def setup(self):
        # Check if we have hypervisor for specified architecture
        if not self.hypervisor_host:
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
                self.container = ExecutionContainer()

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

            # Wait for WebUI to start
            self._wait_for_ip()
            self._wait_for_webui()

    def dry_execute(self):
        self.log(f'Dry-run: {self.test_script_file}, {self.test_case_name}')
        self.reportResult(Result('complete', 'PASS', True))

    def execute(self):
        if self.canceled:
            return
        self.log(f'Running test {self.test_case_name}', show=True)
        self.reportResult(Result('running', None, False))

        cmd = [self.test_script_file, self.test_case_name,
               '--browser', f'{self.vm_ip}:{self.port_webui}',
               '--machine', f'{self.vm_ip}:{self.port_ssh}']
        
        self.log('Running: ' + ' '.join(cmd))

        test_env = {'WEBUI_TEST_DIR': os.path.abspath(os.path.join(self.webui_dir, 'test'))}

        time.sleep(10) # Workaround, there is a race-condition, where WebUI is accessible but /run/anaconda/bus.address doesn't exist yet
        if self.use_container:
            cont_cwd = self.test_workdir.replace(self.temp_dir, '/root/workdir')
            test_env['WEBUI_TEST_DIR'] = test_env['WEBUI_TEST_DIR'].replace(self.temp_dir, '/root/workdir')
            process = self.container.exec(cmd, self.temp_dir, env=test_env, cwd=cont_cwd, log_error=False)
        else:
            process = subprocess.run(cmd, cwd=self.test_workdir, env=test_env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

        self.log(process.stdout.decode(), 'output')
        self.log('Test finished', show=True)

        if process.returncode != 0:
            self.reportResult(Result('complete', 'FAIL', True))
        else:
            self.reportResult(Result('complete', 'PASS', True))

    def teardown(self):
        self.log('Teardown', show=True)
        try:
            self._collect_test_logs()
        except Exception as e:
            LOGGER.error(e)

        if not self.dryRun and not self.debug:
            # Kill VM - this should stop virt-install
            self._virsh_call(['destroy', self.vm_name])

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
                    if self.proc_virtinstall.poll() is None:
                        LOGGER.error('virt-install kill didn\'t work')

            # Close virt-install log
            self.virt_install_log.close()

            # Remove VM
            self._virsh_call(['undefine', self.vm_name, '--remove-all-storage'], check=True)
        
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
            self._virsh_call(['destroy', self.vm_name])

    def log(self, message, name='workflow', show=False):
        if name == 'workflow' and show:
            self.last_log = message
        super().log(message, name)

    def displayStatus(self):
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
        cmd = ['virt-install', '--connect', self.hypervisor_host, '--autoconsole', 'text',
            '-n', self.vm_name, '--os-variant', 'rhel-unknown', '--location', location,
            '--memory', '4096', '--vcpus', '2', '--disk', 'size=10', '--serial', 'pty',
            '--extra-args', kernel_cmdline]

        self.virt_install_log = self.crc.openLogfile('virt-install', 'wb', True)

        LOGGER.info('Running: ' + repr(cmd))
        self.proc_virtinstall = subprocess.Popen(cmd, stdout=self.virt_install_log, stderr=subprocess.STDOUT)

    def _wait_for_ip(self):
        """ Wait for VM to start and get IP """
        self.log('Waiting for IP', show=True)

        for _ in range(12):
            time.sleep(20)
            output = self._virsh_call(['domifaddr', self.vm_name])
            if output:
                self.vm_ip = output.split()[3].split('/')[0]
                break
            if self.canceled:
                break
        else:
            AnacondaWebUISetupError('Timeout, VM still doesn\'t have IP')

    def _wait_for_webui(self):
        """ Wait for WebUI to be accessible

        URLError 111 is expected before the WebUI starts, any othe error is
        going to be reraised.
        """
        self.log('Waiting for WebUI', show=True)
        startup_timeout = self.webui_startup_timeout*60 + time.time()
        webui_url = f'http://{self.vm_ip}:{self.port_webui}{self.webui_location}'
        LOGGER.debug(f'Expexted WebUI URL: {webui_url}')

        ssl_context = ssl.create_default_context()
        if not self.webui_ssl_verify:
            ssl_context.check_hostname=False
            ssl_context.verify_mode=ssl.CERT_NONE

        while True:
            if startup_timeout < time.time():
                raise AnacondaWebUISetupError('WebUI Connection refused, timeout')
            if self.canceled:
                break
            time.sleep(10)
            try:
                urllib.request.urlopen(webui_url, context=ssl_context)
            except urllib.error.URLError as e:
                if e.reason.errno == 111:
                    # Connection refused - webui not yet started
                    continue
                else:
                    raise e
            else:
                break

    def _virsh_call(self, args, check=False):
        """ Runs virsh with specified arguments

        :param args: virsh arguments
        :type args: list
        :param check: Check if command was successful, defaults to False
        :type check: bool, optional
        :return: CompletedProcess
        :rtype: subprocess.CompletedProcess
        """
        cmd = ['virsh', '-q', '--connect', self.hypervisor_host] + args
        LOGGER.debug('Running: ' + repr(cmd))
        return subprocess.run(cmd, check=check, stdout=subprocess.PIPE).stdout.decode()

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

    def _collect_test_logs(self):
        """ Collects logs generated by the WebUI test """
        test_logs_dir = os.path.join(self.test_workdir, 'test_logs', self.test_case_name)

        if not os.path.isdir(test_logs_dir):
            self.log('No log files generated')
            return

        for file in os.listdir(test_logs_dir):
            self.log(f'Adding log file {file}')
            self.addLog(file, os.path.join(test_logs_dir, file), copy_file=True)
