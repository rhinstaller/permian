import unittest
import re
from unittest.mock import patch, create_autospec
import productmd

from libpermian.cli.factory import CliFactory
from libpermian.settings import Settings
from libpermian.exceptions import StructureConversionError
from libpermian.events.factory import EventFactory
from libpermian.plugins.compose import ComposeStructure
from libpermian.plugins.compose.compose_diff import ComposeDiff
from libpermian.plugins.kickstart_test import BootIsoStructure


class MockComposeResponse():
    def __init__(self, url):
        self.url = url
    def geturl(self):
        return self.url.replace('example.com/compose', 'example.com/here')

class DummyImage():
    def __init__(self, image_type, image_path):
        self.type = image_type
        self.path = image_path

def MockProductmdCompose(location):
    instance = create_autospec(productmd.compose.Compose)(location)
    if '.n.' in location:
        instance.info.compose.type = "nightly"
        instance.info.compose.label = None
    else:
        instance.info.compose.type = "production"
        instance.info.compose.label = "Hello-3.14"
    return instance

def MockProductmdComposeImages(location):
    instance = MockProductmdCompose(location)
    instance.images.images = {'Main': {'x86_64': {DummyImage('dvd', 'Main/isos/x86_64/dvd.iso'),
                                                  DummyImage('boot', 'Main/isos/x86_64/boot.iso'),
                                                  DummyImage('qcow2', 'Main/images/x86_64/guest.qcow2')},
                                       'aarch64': {DummyImage('dvd', 'Main/isos/aarch64/dvd.iso'),
                                                   DummyImage('boot', 'Main/isos/aarch64/boot.iso'),
                                                   DummyImage('qcow2', 'Main/images/aarch64/guest.qcow2')}},
                              'Other': {'x86_64': {DummyImage('dvd', 'Other/isos/x86_64/dvd.iso'),
                                                   DummyImage('qcow2', 'Other/images/x86_64/guest.qcow2')},
                                        'aarch64': {DummyImage('dvd', 'Other/isos/aarch64/dvd.iso'),
                                                    DummyImage('qcow2', 'Other/images/aarch64/guest.qcow2')}}}
    return instance

def MockProductmdComposeImagesMultipleBoot(location):
    instance = MockProductmdComposeImages(location)
    instance.images.images['Other']['x86_64'].add(DummyImage('boot', 'Other/isos/x86_64/boot.iso'))
    return instance

class MockUrlopen():
    def __init__(self, url):
        self.url = url
    def __enter__(self):
        return MockComposeResponse(self.url)
    def __exit__(self, type, value, traceback):
        pass

@patch('productmd.compose.Compose', new=MockProductmdCompose)
@patch('urllib.request.urlopen', new=MockUrlopen)
class TestEventCompose(unittest.TestCase):
    def setUp(self):
        self.settings = Settings(cmdline_overrides={'compose': {'location': 'http://example.com/compose/%s'}},
                                 environment={},
                                 settings_locations=[])
    def test_rhel_idonly(self):
        event = EventFactory.make(self.settings, CliFactory.parse('compose', ['RHEL-8.3.0-20200701.2'])[1])
        self.assertEqual(event.compose.id, 'RHEL-8.3.0-20200701.2')
        self.assertEqual(event.compose.version, '8.3.0')
        self.assertEqual(event.compose.major, '8')
        self.assertEqual(event.compose.minor, '3')
        self.assertEqual(event.compose.qr, '0')
        self.assertEqual(event.compose.spin, '2')
        self.assertEqual(event.compose.date, '20200701')
        self.assertEqual(event.compose.product, 'RHEL')
        self.assertIsNone(event.compose.parent_product)
        self.assertIsNone(event.compose.parent_version)
        self.assertFalse(event.compose.nightly)
        self.assertTrue(event.compose.prerelease)
        self.assertFalse(event.compose.layered)
        self.assertEqual(event.compose.location, 'http://example.com/here/RHEL-8.3.0-20200701.2')

    def test_supp_idonly(self):
        event = EventFactory.make(self.settings, CliFactory.parse('compose', ['Supp-9.2.1-RHEL-8-20200811.n.5'])[1])
        self.assertEqual(event.compose.id, 'Supp-9.2.1-RHEL-8-20200811.n.5')
        self.assertEqual(event.compose.version, '9.2.1')
        self.assertEqual(event.compose.major, '9')
        self.assertEqual(event.compose.minor, '2')
        self.assertEqual(event.compose.qr, '1')
        self.assertEqual(event.compose.spin, '5')
        self.assertEqual(event.compose.date, '20200811')
        self.assertEqual(event.compose.product, 'Supp')
        self.assertEqual(event.compose.parent_product, 'RHEL')
        self.assertEqual(event.compose.parent_version, '9.2.1')
        self.assertTrue(event.compose.nightly)
        self.assertFalse(event.compose.prerelease)
        self.assertTrue(event.compose.layered)
        self.assertEqual(event.compose.location, 'http://example.com/here/Supp-9.2.1-RHEL-8-20200811.n.5')

    def test_updates_idonly(self):
        event = EventFactory.make(self.settings, CliFactory.parse('compose', ['RHEL-8.3.0-updates-20200701.t.4'])[1])
        self.assertEqual(event.compose.id, 'RHEL-8.3.0-updates-20200701.t.4')
        self.assertEqual(event.compose.version, '8.3.0')
        self.assertEqual(event.compose.major, '8')
        self.assertEqual(event.compose.minor, '3')
        self.assertEqual(event.compose.qr, '0')
        self.assertEqual(event.compose.spin, '4')
        self.assertEqual(event.compose.date, '20200701')
        self.assertEqual(event.compose.product, 'RHEL')
        self.assertIsNone(event.compose.parent_product)
        self.assertIsNone(event.compose.parent_version)
        self.assertFalse(event.compose.nightly)
        self.assertTrue(event.compose.prerelease)
        self.assertFalse(event.compose.layered)
        self.assertEqual(event.compose.location, 'http://example.com/here/RHEL-8.3.0-updates-20200701.t.4')

    def test_supp_updates_idonly(self):
        event = EventFactory.make(self.settings, CliFactory.parse('compose', ['Supp-9.2.1-updates-RHEL-8-20200811.5'])[1])
        self.assertEqual(event.compose.id, 'Supp-9.2.1-updates-RHEL-8-20200811.5')
        self.assertEqual(event.compose.version, '9.2.1')
        self.assertEqual(event.compose.major, '9')
        self.assertEqual(event.compose.minor, '2')
        self.assertEqual(event.compose.qr, '1')
        self.assertEqual(event.compose.spin, '5')
        self.assertEqual(event.compose.date, '20200811')
        self.assertEqual(event.compose.product, 'Supp')
        self.assertEqual(event.compose.parent_product, 'RHEL')
        self.assertEqual(event.compose.parent_version, '9.2.1')
        self.assertFalse(event.compose.nightly)
        self.assertTrue(event.compose.prerelease)
        self.assertTrue(event.compose.layered)
        self.assertEqual(event.compose.location, 'http://example.com/here/Supp-9.2.1-updates-RHEL-8-20200811.5')

    def test_rhel_overrides(self):
        event = EventFactory.make(self.settings,
                                  CliFactory.parse('compose', ['RHEL-8.3.0-20200701.2',
                                                               '--product=Test',
                                                               '--version=1.3.2',
                                                               '--location=test/location',
                                                               '--nightly=1',
                                                               '--prerelease=false',
                                                               '--layered=true',
                                                               '--parent-product=TEST',
                                                               '--parent-version=7.2.0'])[1])
        self.assertEqual(event.compose.id, 'RHEL-8.3.0-20200701.2')
        self.assertEqual(event.compose.version, '1.3.2')
        self.assertEqual(event.compose.major, '1')
        self.assertEqual(event.compose.minor, '3')
        self.assertEqual(event.compose.qr, '2')
        self.assertEqual(event.compose.spin, '2')
        self.assertEqual(event.compose.date, '20200701')
        self.assertEqual(event.compose.product, 'Test')
        self.assertEqual(event.compose.parent_product, 'TEST')
        self.assertEqual(event.compose.parent_version, '7.2.0')
        self.assertTrue(event.compose.nightly)
        self.assertFalse(event.compose.prerelease)
        self.assertTrue(event.compose.layered)
        self.assertEqual(event.compose.location, 'test/location')

    def test_rhel_overrides_version(self):
        event = EventFactory.make(self.settings,
                                  CliFactory.parse('compose', ['RHEL-8.3.0-20200701.2',
                                                               '--version=ahoj',
                                                               '--major=10',
                                                               '--minor=9',
                                                               '--qr=8'])[1])
        self.assertEqual(event.compose.id, 'RHEL-8.3.0-20200701.2')
        self.assertEqual(event.compose.version, 'ahoj')
        self.assertEqual(event.compose.major, '10')
        self.assertEqual(event.compose.minor, '9')
        self.assertEqual(event.compose.qr, '8')

    def test_supp_overrides(self):
        event = EventFactory.make(self.settings,
                                  CliFactory.parse('compose', ['Supp-9.2.1-RHEL-8-20200811.n.5',
                                                               '--product=Test',
                                                               '--version=1.3.2',
                                                               '--location=test/location',
                                                               '--nightly=no',
                                                               '--prerelease=yes',
                                                               '--layered=no',
                                                               '--parent-product=TEST',
                                                               '--parent-version=7.2.0'])[1])
        self.assertEqual(event.compose.id, 'Supp-9.2.1-RHEL-8-20200811.n.5')
        self.assertEqual(event.compose.version, '1.3.2')
        self.assertEqual(event.compose.major, '1')
        self.assertEqual(event.compose.minor, '3')
        self.assertEqual(event.compose.qr, '2')
        self.assertEqual(event.compose.spin, '5')
        self.assertEqual(event.compose.date, '20200811')
        self.assertEqual(event.compose.product, 'Test')
        self.assertEqual(event.compose.parent_product, 'TEST')
        self.assertEqual(event.compose.parent_version, '7.2.0')
        self.assertFalse(event.compose.nightly)
        self.assertTrue(event.compose.prerelease)
        self.assertFalse(event.compose.layered)
        self.assertEqual(event.compose.location, 'test/location')

    def test_event_type(self):
        event = EventFactory.make(
            self.settings,
            CliFactory.parse('compose', ['RHEL-8.3.0-20200701.2'])[1]
        )
        self.assertEqual(event.type, 'compose')

    def test_custom_event_type(self):
        event = EventFactory.make(
            self.settings,
            CliFactory.parse('compose', ['RHEL-8.3.0-20200701.2', '--event-type', 'compose.foo.bar'])[1]
        )
        self.assertEqual(event.type, 'compose.foo.bar')

    def test_str_label(self):
        event = EventFactory.make(
            self.settings,
            CliFactory.parse('compose', ['RHEL-8.3.0-20200701.2', '--event-type', 'compose.foo.bar.baz'])[1]
        )
        self.assertEqual(str(event), 'RHEL-8.3.0-20200701.2 (Hello) baz')

    def test_str_nolabel(self):
        event = EventFactory.make(
            self.settings,
            CliFactory.parse('compose', ['RHEL-8.3.0-20200701.n.2', '--event-type', 'compose.foo.bar.baz'])[1]
        )
        self.assertEqual(str(event), 'RHEL-8.3.0-20200701.n.2 baz')


def mock_list_tagged_composes(pattern, tags):
    return [{'distro_id': 1, 'distro_tags': tags, 'distro_version': 'RedHatEnterpriseLinux8.2', 'distro_name': 'RHEL-8.2.0-20200404.0'},
            {'distro_id': 2, 'distro_tags': tags, 'distro_version': 'RedHatEnterpriseLinux8.2', 'distro_name': 'RHEL-8.2.0-20200401.0'},
            {'distro_id': 3, 'distro_tags': tags, 'distro_version': 'RedHatEnterpriseLinux8.2', 'distro_name': 'RHEL-8.2.0-20200331.0'},
            {'distro_id': 4, 'distro_tags': tags, 'distro_version': 'RedHatEnterpriseLinux8.2', 'distro_name': 'RHEL-8.2.0-20200310.0'}]

class TestComposePrevious(unittest.TestCase):
    @patch('libpermian.plugins.compose.list_tagged_composes', new=mock_list_tagged_composes)
    def test_previous_compose_exists(self):
        compose = ComposeStructure(None, 'RHEL-8.2.0-20200402.0')
        self.assertEqual(compose.previous(beaker_tag='test').id, 'RHEL-8.2.0-20200401.0')

    @patch('libpermian.plugins.compose.list_tagged_composes', new=mock_list_tagged_composes)
    def test_previous_compose_exists_latest(self):
        compose = ComposeStructure(None, 'RHEL-8.3.0-20210402.d.1')
        self.assertEqual(compose.previous(beaker_tag='test').id, 'RHEL-8.2.0-20200404.0')

    @patch('libpermian.plugins.compose.list_tagged_composes', new=mock_list_tagged_composes)
    def test_previous_compose_none_current_in_list(self):
        compose = ComposeStructure(None, 'RHEL-8.2.0-20200310.0')
        self.assertEqual(compose.previous(beaker_tag='test'), None)

    @patch('libpermian.plugins.compose.list_tagged_composes', new=mock_list_tagged_composes)
    def test_previous_compose_none(self):
        compose = ComposeStructure(None, 'RHEL-8.2.0-20200210.0')
        self.assertEqual(compose.previous(beaker_tag='test'), None)

    @patch('libpermian.plugins.compose.list_tagged_composes')
    def test_previous_compose_no_relevant_composes(self, list_tagged_mock):
        list_tagged_mock.return_value = None
        compose = ComposeStructure(None, 'RHEL-8.2.0-20200402.0')
        self.assertEqual(compose.previous(beaker_tag='test'), None)
        list_tagged_mock.assert_called_once_with('RHEL-8.2._-%', ('test',))


class ComposeTest1():
    components = {'anaconda-0:29.19.2.17-1.el8.src',
                  'python-blivet-1:3.1.0-20.el8.src'}

class ComposeTest2():
    components = {'anaconda-0:29.21.1.5-1.el8.src',
                  'python-blivet-1:3.1.0-20.el8.src',
                  'grub2-1:2.02-81.el8.src'}

class TestComposeDiff(unittest.TestCase):
    def test_compose_diff(self):
        diff = ComposeDiff(ComposeTest1(), ComposeTest2())
        self.assertEqual(diff.component_names, {'anaconda', 'grub2'})

    def test_compose_diff_no_compose(self):
        with self.assertLogs() as cm:
            diff = ComposeDiff(ComposeTest1(), None)
            self.assertEqual(diff.component_names, {'anaconda', 'python-blivet'})
        self.assertTrue(cm.output[0].startswith('WARNING:libpermian.plugins.compose.compose_diff:'))

@patch('productmd.compose.Compose', new=MockProductmdComposeImages)
@patch('urllib.request.urlopen', new=MockUrlopen)
class TestComposeToBootIso(unittest.TestCase):
    def setUp(self):
        self.settings = Settings(cmdline_overrides={'compose': {'location': 'http://example.com/compose/%s/'}},
                            environment={},
                            settings_locations=[])
        self.comp = ComposeStructure(self.settings, 'OS-1.0.2-20220221.1')

    def test_succesfull_conversion(self):
        boot_iso = self.comp.to_bootIso()
        self.assertIsInstance(boot_iso, BootIsoStructure)
        self.assertAlmostEqual(boot_iso.fields, {'x86_64': 'http://example.com/here/OS-1.0.2-20220221.1/Main/isos/x86_64/boot.iso',
                                                 'aarch64': 'http://example.com/here/OS-1.0.2-20220221.1/Main/isos/aarch64/boot.iso'})

@patch('productmd.compose.Compose', new=MockProductmdComposeImagesMultipleBoot)
@patch('urllib.request.urlopen', new=MockUrlopen)
class TestComposeToBootIsoFail(unittest.TestCase):
    def setUp(self):
        self.settings = Settings(cmdline_overrides={'compose': {'location': 'http://example.com/compose/%s/'}},
                            environment={},
                            settings_locations=[])
        self.comp = ComposeStructure(self.settings, 'OS-1.0.2-20220221.1')

    def test_failed_conversion(self):
        self.assertRaises(StructureConversionError, self.comp.to_bootIso)
