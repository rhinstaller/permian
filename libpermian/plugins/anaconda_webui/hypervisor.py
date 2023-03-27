import subprocess
import time
import logging


START_PORT = '42000'
LOGGER = logging.getLogger(__name__)


class Hypervisor():
    def __init__(self, host):
        if host in ['localhost', '127.0.0.1', '::1']:
            self.remote = False
            self.qemu_host = 'qemu:///system'
        else:
            self.remote = True
            self.qemu_host = f'qemu+ssh://root@{host}/system'
        self.host = host

        self.configured_preroutings = {}

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
        for _ in range(attempts):
            time.sleep(wait)
            output = self.virsh_call(['domifaddr', vm_name])
            if output:
                return output.split()[3].split('/')[0]
        else:
            raise Exception('Timeout, VM still doesn\'t have IP')

    def stop_vm(self, vm_name):
        """ Call destroy on specified VM """
        self.virsh_call(['destroy', vm_name])

    def remove_vm(self, vm_name):
        """ Remove specified VM including storage """
        self.virsh_call(['undefine', vm_name, '--remove-all-storage'], check=True)

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

    def _run_cmd(self, cmd):
        """ Run command on hypervisor

        :param cmd: Command
        :type cmd: string
        :return: Command output, including stderr
        :rtype: string
        """
        proc = subprocess.run(['ssh', '-p', '22', f'root@{self.host}', cmd], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        return proc.stdout.decode().strip()

    def configure_prerouting(self, vm_ip, ports):
        """ Configure preroutings for specified ip and ports

        :param vm_ip: IP of the VM
        :type vm_ip: string
        :param ports: List of port numbers to pre-route (strings)
        :type ports: list
        :return: List of new ports, in the same order as input ports
        :rtype: list
        """
        if not self.remote:
            LOGGER.info('Prerouting is not needed on local hypervisor')
            return ports

        if not self._aquire_config_lock():
            raise Exception('Could not aquire prerouting lock on the hypervisor')

        return_ports = []
        for port in ports:
            host_port = self._get_available_port()
            self._add_prerouting(vm_ip, port, host_port)
            self.configured_preroutings[port] = (vm_ip, host_port)
            return_ports.append(host_port)
        
        self._release_config_lock()
        return return_ports

    def clean_prerouting(self):
        """ Undo all configuration done by this instance """
        for vm_port, ip_host_port in self.configured_preroutings.items():
            self._remove_prerouting(ip_host_port[0], vm_port, ip_host_port[1])
        self.configured_preroutings.clear()

    def _aquire_config_lock(self, attempts=60):
        for _ in range(attempts):
            output = self._run_cmd('if [ -e prerouting.lock ]; then echo 0; else touch prerouting.lock; echo 1; fi')
            if output == '1':
                break
            time.sleep(1)
        else:
            return False
        return True

    def _release_config_lock(self):
        self._run_cmd('rm -f prerouting.lock')

    def _remove_prerouting(self, vm_ip, vm_port, host_port):
        """ Remove configuration of prerouting and forwarding for specified ip and ports """
        self._run_cmd(f'iptables -D FORWARD -o virbr0 -p tcp -d {vm_ip} --dport {vm_port} -j ACCEPT')
        self._run_cmd(f'iptables -t nat -D PREROUTING -p tcp --dport {host_port} -j DNAT --to {vm_ip}:{vm_port}')

    def _add_prerouting(self, vm_ip, vm_port, host_port):
        """ Configure prerouting and forwarding for specified ip and ports """
        try:
            self._run_cmd(f'iptables -I FORWARD -o virbr0 -p tcp -d {vm_ip} --dport {vm_port} -j ACCEPT')
            self._run_cmd(f'iptables -t nat -I PREROUTING -p tcp --dport {host_port} -j DNAT --to {vm_ip}:{vm_port}')
        except Exception:
            raise Exception(f'Failed to configure prerouting on the hypervisor')

    def _get_available_port(self):
        """ Get next port not used for prerouting """
        # Get list of configured preroutings
        output = self._run_cmd('iptables -S PREROUTING -t nat')

        used_ports = []
        for line in output.splitlines():
            if line.startswith('-A PREROUTING -p tcp -m tcp --dport '):
                used_ports.append(int(line.split(' ')[7])) # get port number

        # Return one higher than highest used port
        try:
            return str(sorted(used_ports)[-1]+1)
        except IndexError:
            return START_PORT