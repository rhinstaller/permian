import os
import unittest

from ..compose import ComposeStructure
from . import BeakerCompose, BeakerException

class TestBeakerComposeStructure(unittest.TestCase):
    def test_from_compose(self):
        compose = ComposeStructure(None, 'FOO-1.2.3-20380119.42')
        beaker_compose = BeakerCompose.from_compose(compose)
        self.assertEqual(beaker_compose.id, 'FOO-1.2.3-20380119.42')
        self.assertEqual(beaker_compose.product, 'FOO')
        self.assertEqual(beaker_compose.major, '1')
        self.assertEqual(beaker_compose.minor, '2')

    def test_family_RHEL(self):
        beaker_compose = BeakerCompose(None, None, 'rhel', 4, None)
        self.assertEqual(beaker_compose.family, 'RedHatEnterpriseLinux4')

    def test_family_Fedora(self):
        beaker_compose = BeakerCompose(None, None, 'fedora', 13, None)
        self.assertEqual(beaker_compose.family, 'Fedora13')

    def test_family_CentOS(self):
        beaker_compose = BeakerCompose(None, None, 'centos', 6, None)
        self.assertEqual(beaker_compose.family, 'CentOSLinux6')

@unittest.skipUnless(os.environ.get('EXTENDED_TESTSUITE', '0') != '0', 'Extended testcase involving Beaker.')
class TestBeakerComposeExtended(unittest.TestCase):
    def test_accepted_fictional(self):
        compose = BeakerCompose(None, 'FOO-1.2.3-20380119.42', 'FOO', '1', '2')
        with self.assertRaises(BeakerException):
            compose.rtt_accepted

    def test_accepted_exact(self):
        compose = BeakerCompose(None, 'RHEL-7.9', 'RHEL', '7', '9')
        self.assertEqual(compose.rtt_accepted, 'RHEL-7.9')

    def test_accepted_previous(self):
        compose = BeakerCompose(None, 'RHEL-7.10', 'RHEL', '7', '10')
        self.assertEqual(compose.rtt_accepted, 'RHEL-7.9')

    def test_accepted_most_recent(self):
        # NOTE THIS TEST IS VERY UNRELIABLE AS IT DEPENDS ON LATEST MAJOR
        # VERSION AVAILABLE IN USED BEAKER INSTANCE
        expected_major = '8'
        compose = BeakerCompose(None, 'RHEL-20.30', 'RHEL', '20', '30')
        self.assertRegex(compose.rtt_accepted, rf'^RHEL-{expected_major}\.[0-9]')
