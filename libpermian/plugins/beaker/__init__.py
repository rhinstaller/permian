import json
import subprocess
import functools
import time
import re
import os
import tempfile
import threading
import xmlrpc.client

import bkr.common.pyconfig
import bkr.common.hub
import gssapi.raw.misc
import libpermian.plugins.api.events
from libpermian.events.structures.base import BaseStructure

"""
This package provides various additional functionality related to beaker used
by the legacy_puzzle_merger workflow. It's related to composes available in
beaker.
"""

class BeakerException(Exception):
    pass

class UnknownProduct(Exception):
    pass

def _compose_cmp(this, that):
    """
    Comparator function serving as best-effort way for comparing composes based
    on their ids.
    """
    # if this or that is shorter version of the second one it's release and should be used
    if this.startswith(that.strip()):
        return -1
    if that.startswith(this.strip()):
        return 1
    if this > that:
        return 1
    if this < that:
        return -1
    if this == that:
        return 0
    return None # something is wrong at this point


@libpermian.plugins.api.events.register_structure('beakerCompose')
class BeakerCompose(BaseStructure):
    """
    :param compose_id: Id of compose like RHEL-X.Y.Q-YYYYMMDD.S
    :type compose_id: str
    :param product: Name of product like RHEL of Fedora.
    :type product: str
    :param major: Major version number
    :type major: int
    :param minor: Minor version number
    :type minor: int
    """
    def __init__(self, settings, compose_id, product, major, minor):
        super().__init__(settings)
        self.id = compose_id
        self.product = product
        self.major = major
        self.minor = minor

    @classmethod
    def from_compose(cls, compose):
        return cls(
            compose.settings,
            compose.id,
            compose.product,
            compose.major,
            compose.minor,
        )

    @property
    def rtt_accepted(self):
        """
        This method it trying to mimic current RTT practice of determining
        last (previous) RTT accepted compose corresponding to this compose.

        :raises BeakerException: When no RTT_ACCEPTED compose relevant to this compose could be found.
        :return: Compose id if relevant RTT_ACCEPTED compose.
        :rtype: str
        """
        product = self.product if self.product != 'Gemini' else 'RHEL'
        name_part = f'{product}-{self.major}.{self.minor}'
        last_name_part = None
        while name_part != last_name_part:
            last_name_part = name_part
            composes = list_tagged_composes(f'{name_part}%')
            if composes:
                break
            cut_point = name_part.replace('-', '.').rfind('.')
            if cut_point == -1:
                break
            name_part = name_part[0:cut_point]

        if not composes:
            raise BeakerException(f"Couldn't find tagged compose corresponding to {self.id}")
        compose_names = [compose['distro_name'] for compose in composes]
        return max(compose_names, key=functools.cmp_to_key(_compose_cmp))

    @property
    def family(self):
        "Beaker family name used for this compose."
        if self.product.upper() in ["RHEL", "GEMINI"]:
            return f"RedHatEnterpriseLinux{self.major}"
        if self.product.upper() == "FEDORA":
            return f"Fedora{self.major}"
        if self.product.upper() == "CENTOS":
            return f"CentOSLinux{self.major}"
        raise UnknownProduct(self.product)

def list_tagged_composes(pattern, tags=('RTT_ACCEPTED',)):
    """
    :param pattern: Name pattern used in beaker. Use '%' character as wildcard for zero ore more character.
    :type pattern: str
    :param tags: List of tags the composes must have.
    :type tags: iterable
    :return: list of compose information matching provided name pattern and having the provided tags.
    :rtype: list
    """
    command = ['bkr', 'distros-list','--format', 'json', '--name', pattern]
    for tag in tags:
        command += ['--tag', tag]
    try:
        process = subprocess.run(command, stdout=subprocess.PIPE, check=True)
        return json.loads(process.stdout)
    except subprocess.CalledProcessError as exp:
        if exp.stdout.strip() == b'[]':
            return None
        raise BeakerException(f'bkr command call failed on: {exp}')


def wait_for_compose(name, architecture=None, labcontroller=None, timeout=7200, wait_step=600):
    """
    :param name: Compose ID
    :type name: str
    :param architecture: Architecture like x86_64 or aarch64. If not provided, any available architecture is sufficient.
    :type architecture: str, optional
    :param labcontroller: Name of beaker labcontroller. If not provided, any labcontroller is sufficient.
    :type labcontroller: str, optional
    :param timeout: Number of seconds how long it should be waited for the compose to be available.
    :type timeout: int, optional
    :param wait_step: Interval used for re-cheking the availability of the compose.
    :type wait_step: int, optional
    :return: True if the compose of given name and architecture is available in the labcontroller in less than timeout seconds. Return False otherwise.
    :rtype: bool
    """
    command = ['bkr', 'distro-trees-list', '--name', name]
    if architecture:
        command += ['--arch', architecture]
    if labcontroller:
        command += ['--labcontroller', labcontroller]
    while timeout > 0:
        with open('/dev/null', 'wb') as devnull:
            if subprocess.run(command, stdout=devnull, stderr=devnull).returncode == 0:
                return True
        time.sleep(wait_step)
        timeout -= wait_step
    return False


def retry_call(func, ignore_exceptions, attempts=5, interval=1, interval_exponential_growth=1):
    """
    Attempt to call func repeatedly if one of provided exceptions is hit.
    Should different exception type be hit, such exception is raised.
    Should maximum number of attempts be hit, the last exception is raised.

    :param func: callable to run
    :type func: callable
    :param ignore_exceptions: One exception or iterable of exceptions under which the callable should be re-run
    :type ignore_exceptions: Exception or iterable of Exception
    :param attempts: Number of attempts. Must be larger or equal 1. Use float('inf') for infinite number of retries.
    :type attempts: int or float
    :param interval: Sleep time between re-runs
    :type interval: int or float
    :param interval_exponential_growth: Grow the interval exponentially using the provided base. If the call is not successful, the next attempt will take the the previous iterval value multiplied by exponential_growth seconds. If the growth is 2, the iterval will be: 1, 2, 4, 8, 16, ...
    :param interval_exponential_growth: int
    :return: Return value of the func
    """
    if attempts < 1:
        raise ValueError('Number of attempts must be larger or equal 1')
    while True:
        attempts -= 1
        try:
            return func()
        except ignore_exceptions:
            if attempts <= 0:
                raise
            time.sleep(interval)
            interval *= interval_exponential_growth


def retry_beaker_call(func, *args, **kwargs):
    """
    Shortcut for retry_call with desired (hard-coded and global) beaker
    timeouts and intervals.

    :param func: callable to run
    :type func: callable
    :param args: arguments passed to the callable
    :param kwargs: keyword arguments passed to the callable
    :return: Return value of the func called with provided args and kwargs
    """
    return retry_call(
        functools.partial(
            func,
            *args,
            **kwargs,
        ),
        (xmlrpc.client.Fault, xmlrpc.client.ProtocolError),
        attempts=10, interval_exponential_growth=2,
    )


def xmlrpc_server(settings):
    """
    Construct XMLRPC proxy server that can be used for XMLRPC communication with
    beaker instance configured in settings.
    """
    CONF = bkr.common.pyconfig.PyConfigParser()
    CONF.load_from_file('/etc/beaker/client.conf')
    CONF.load_from_dict({
        option : settings.get('beaker', option)
        for option in settings.options('beaker')
    })
    # Try ten times with growing retry waiting up to 17 minutes in total
    # before raising exception.
    return retry_call(
        functools.partial(bkr.common.hub.HubProxy, conf=CONF),
        (
            gssapi.raw.misc.GSSError,
        ),
        attempts=10,
        interval=1,
        interval_exponential_growth=2,
    )
