import subprocess
import time
import logging
import os
import signal
import tempfile
import random
import re


LOGGER = logging.getLogger(__name__)


class VMIPTimeout(Exception):
    pass


class Hypervisor():
    def __init__(self, host):
        self.host = host
        self.ssh_master_pid = None
        self.pid_re = re.compile(r'Master running \(pid=(\d+)\)')

        if host in ['localhost', '127.0.0.1', '::1']:
            self.remote = False
            self.qemu_host = 'qemu:///system'
        else:
            self.remote = True
            self.qemu_host = f'qemu+ssh://{host}/system'
            self.tempdir = tempfile.TemporaryDirectory(prefix='permian_sshctl.')
            self.ssh_ctl_file = os.path.join(self.tempdir.name, self.host)
            self._open_connection()

    def setup(self):
        # Try to create storage pool boot-scratch to avoid issues later, if it exist its ok for this command to fail.
        self.virsh_call([
            'pool-create-as', '--name', 'boot-scratch',
            '--type', 'dir', '--target' ,'/var/lib/libvirt/boot',
            '--build'
        ])

    def forwarding_cleanup(self):
        self._close_connection()
        self.tempdir.cleanup()

    def _open_connection(self):
        """ Start ssh master connection """
        if os.path.exists(self.ssh_ctl_file):
            return

        subprocess.run(
            ['ssh', '-S', self.ssh_ctl_file,
            '-o', 'ControlPersist=yes',
            '-M', '-N', self.host
            ], check=True)
        # Get pid
        output = subprocess.run(
            ['ssh', '-S', self.ssh_ctl_file,
            '-O', 'check', self.host],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT
            ).stdout.decode()
        try:
            self.ssh_master_pid = re.match(self.pid_re, output).group(1)
        except AttributeError:
            LOGGER.error(f'Could not find pid of the ssh master connection: {output}, ssh may be left running after Permian ends')

    def _close_connection(self):
        """ Stop master connection """
        if not os.path.exists(self.ssh_ctl_file):
            return

        subprocess.run(
            ['ssh', '-S', self.ssh_ctl_file,
            '-O', 'exit', self.host
            ], check=True)
        self.ssh_master_pid = None

    def configure_forwarding(self, vm_ip, ports):
        """ Configure forwadring for specified ip and ports

        :param vm_ip: IP of the VM
        :type vm_ip: string
        :param ports: List of port numbers to forward
        :type ports: list
        :return: List of new ports, in the same order as input ports
        :rtype: list
        """
        if not self.remote:
            LOGGER.info('Forwarding is not needed on local hypervisor')
            return ports

        return [ self._forward_port(vm_ip, port) for port in ports ]

    def _forward_port(self, target_ip, target_port):
        for _ in range(100):
            local_port = random.randint(49152, 65535)
            try:
                subprocess.run(
                    ['ssh', '-S', self.ssh_ctl_file,
                    '-O', 'forward',
                    '-L', f'*:{local_port}:{target_ip}:{target_port}',
                    f'{self.host}'
                    ], check=True)
                LOGGER.debug(f'Forwarded {local_port} to {target_ip}:{target_port}')
                return local_port
            except:
                # couldn't use local_port, let's try another one
                continue

    def wait_for_ip(self, vm_name, attempts=30, wait=10):
        """  Wait for VM to get IP

        :param vm_name: VM name
        :type vm_name: string
        :param attempts: Number of attempts
        :type attempts: integer
        :param wait: How log to wait before next attempt (seconds)
        :type wait: float
        :return: CompletedProcess
        :rtype: string
        """
        LOGGER.info('Waiting for VM to start and get IP. (Failed to get domain errors are expected)')
        for _ in range(attempts):
            time.sleep(wait)
            output = self.virsh_call(['domifaddr', vm_name])
            if output:
                return output.split()[3].split('/')[0]
        else:
            raise VMIPTimeout('Timeout, VM still doesn\'t have IP')

    def stop_vm(self, vm_name):
        """ Call destroy on specified VM """
        self.virsh_call(['destroy', vm_name])

    def remove_vm(self, vm_name):
        """ Remove specified VM including storage """
        try:
            self.virsh_call(['undefine', vm_name, '--remove-all-storage'], check=True)
        except subprocess.CalledProcessError:
            LOGGER.error(f'Failed to undefine VM {vm_name}')

    def virsh_call(self, args, check=False):
        """ Runs virsh with specified arguments

        :param args: virsh arguments
        :type args: list
        :param check: Check if command was successful, defaults to False
        :type check: bool, optional
        :return: CompletedProcess
        :rtype: subprocess.CompletedProcess
        """
        cmd = ['virsh', '-q', '--connect', self.qemu_host] + args
        LOGGER.debug('Running: ' + repr(cmd))
        return subprocess.run(cmd, check=check, stdout=subprocess.PIPE).stdout.decode()

    def __del__(self):
        """ Kill ssh master process if it wasn't stoped properly """
        if self.ssh_master_pid is not None:
            os.kill(self.ssh_master_pid, signal.SIGTERM)
