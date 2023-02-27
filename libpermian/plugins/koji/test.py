import unittest
import re
from unittest.mock import patch, create_autospec, call
import productmd
import io
import urllib.error

from libpermian.events.factory import EventFactory
from libpermian.cli.factory import CliFactory
from libpermian.settings import Settings

from . import KojiEvent, KojiBuild
from libpermian.plugins.compose.exceptions import ComposeNotAvailable

@patch('xmlrpc.client.ServerProxy')
class TestKojiEvent(unittest.TestCase):
    def setUp(self):
        self.hub_url = 'http://koji.example.com/path/to/hub'
        self.nvr = 'foo-1.2-3.dt4'
        self.tag = 'bar'
        self.settings = Settings(
            {
                'koji' : {
                    'hub_url' : self.hub_url,
                },
            },
            {},
            {},
        )

    def test_minimal(self, koji_proxy_class):
        event = EventFactory.make(
            self.settings,
            CliFactory.parse('koji_build_tag', [self.nvr, self.tag])[1]
        )
        self.assertIsInstance(event, KojiEvent)
        self.assertIsInstance(event.koji_build, KojiBuild)
        self.assertEqual(event.koji_build.nvr, self.nvr)
        self.assertEqual(event.koji_build.new_tag, self.tag)
        self.assertEqual(event.type, 'koji.build.tag')

    def test_all(self, koji_proxy_class):
        event_type = 'koji.hello'
        build_id = 67890
        task_id = 12345
        package_name = 'stress-o-meter'
        command_args = [
            self.nvr,
            self.tag,
            '--event-type', event_type,
            '--build-id', str(build_id),
            '--task-id', str(task_id),
            '--package-name', package_name,
        ]
        event = EventFactory.make(
            self.settings,
            CliFactory.parse('koji_build_tag', command_args)[1]
        )
        self.assertIsInstance(event, KojiEvent)
        self.assertIsInstance(event.koji_build, KojiBuild)
        self.assertEqual(event.koji_build.nvr, self.nvr)
        self.assertEqual(event.koji_build.new_tag, self.tag)
        self.assertEqual(event.type, event_type)
        self.assertEqual(event.koji_build.build_id, build_id)
        self.assertEqual(event.koji_build.task_id, task_id)
        self.assertEqual(event.koji_build.package_name, package_name)
        self.assertEqual(str(event), f'stress-o-meter {self.nvr} {self.tag}')

@patch('xmlrpc.client.ServerProxy')
class TestKojiEventStructure(unittest.TestCase):
    def setUp(self):
        self.hub_url = 'http://koji.example.com/path/to/hub'
        self.nvr = 'foo-1.2-3.dt4'
        self.build_id = 1001
        self.task_id = 1337
        self.package_name = 'surprise!'
        self.new_tag = 'acme-1.2.3-poof'
        self.composes_baseurl = 'http://example.com/composes/foo'
        self.settings = Settings(
            {
                'koji' : {
                    'hub_url' : self.hub_url,
                    'testcompose_timeout' : 3,
                    'testcompose_retry_interval' : 1.2,
                    'testcompose_baseurl' : self.composes_baseurl
                },
            },
            {},
            {},
        )

    def test_minimal(self, koji_proxy_class):
        koji_build = KojiBuild(self.settings, self.nvr)
        self.assertEqual(koji_build.hub_url, self.hub_url)
        self.assertEqual(koji_build.nvr, self.nvr)

    def test_discovery(self, koji_proxy_class):
        koji_proxy_class.return_value.getBuild.return_value = {
            'build_id' : self.build_id,
            'task_id' : self.task_id,
            'package_name' : self.package_name,
        }
        koji_proxy_class.return_value.listTags.return_value = (
            {'name': self.new_tag},
            {'name': 'foo'},
        )
        koji_build = KojiBuild(self.settings, self.nvr)
        self.assertEqual(koji_build.hub_url, self.hub_url)
        self.assertEqual(koji_build.nvr, self.nvr)
        self.assertEqual(koji_build.build_id, self.build_id)
        self.assertEqual(koji_build.task_id, self.task_id)
        self.assertEqual(koji_build.package_name, self.package_name)
        self.assertEqual(koji_build.new_tag, self.new_tag)
        koji_proxy_class.assert_called_with(self.hub_url, allow_none=True)
        koji_proxy_class.return_value.getBuild.assert_called_once_with(self.nvr, True)
        koji_proxy_class.return_value.listTags.assert_called_once_with(self.build_id, None, False)

    def test_all(self, koji_proxy_class):
        koji_build = KojiBuild(
            self.settings,
            self.nvr, build_id=self.build_id,
            task_id=self.task_id, package_name=self.package_name,
            new_tag=self.new_tag
        )
        self.assertEqual(koji_build.nvr, self.nvr)
        self.assertEqual(koji_build.build_id, self.build_id)
        self.assertEqual(koji_build.task_id, self.task_id)
        self.assertEqual(koji_build.package_name, self.package_name)
        self.assertEqual(koji_build.new_tag, self.new_tag)
        koji_proxy_class.assert_not_called()
        koji_proxy_class.return_value.getBuild.assert_not_called()

    @patch('urllib.request.urlopen')
    @patch('productmd.compose.Compose')
    def test_convert_compose(self, Compose, urlopen, koji_proxy_class):
        compose_id = 'FooBar-1.23-123456.t.98'
        compose_relpath = '../some_compose_dir'
        koji_proxy_class.return_value.getBuild.return_value = {
            'build_id' : self.build_id,
            'task_id' : self.task_id,
            'package_name' : self.package_name,
        }
        koji_proxy_class.return_value.listTags.return_value = (
            {'name': self.new_tag},
        )
        Compose.return_value.info.compose.id = compose_id
        urlopen.return_value = io.BytesIO(bytes(f'{compose_relpath}\n', 'utf-8'))
        koji_build = KojiBuild(self.settings, self.nvr)
        compose = koji_build.to_compose()
        self.assertEqual(compose.id, compose_id)
        self.assertEqual(
            compose.location,
            f'{self.composes_baseurl}/{compose_relpath}'
        )

    @patch('urllib.request.urlopen')
    @patch('productmd.compose.Compose')
    def test_convert_compose_multiple(self, Compose, urlopen, koji_proxy_class):
        compose_id = 'FooBar-1.23-123456.t.98'
        mocked_compose_relpath = '../some_compose_dir\n../another_compose_dir\n'
        desired_compose_relpath = '../another_compose_dir'
        koji_proxy_class.return_value.getBuild.return_value = {
            'build_id' : self.build_id,
            'task_id' : self.task_id,
            'package_name' : self.package_name,
        }
        koji_proxy_class.return_value.listTags.return_value = (
            {'name': self.new_tag},
        )
        Compose.return_value.info.compose.id = compose_id
        urlopen.return_value = io.BytesIO(bytes(mocked_compose_relpath, 'utf-8'))
        koji_build = KojiBuild(self.settings, self.nvr)
        compose = koji_build.to_compose()
        self.assertEqual(compose.id, compose_id)
        self.assertEqual(
            compose.location,
            f'{self.composes_baseurl}/{desired_compose_relpath}'
        )

    @patch('urllib.request.urlopen')
    @patch('productmd.compose.Compose')
    def test_convert_compose_fail(self, Compose, urlopen, koji_proxy_class):
        compose_id = 'FooBar-1.23-123456.t.98'
        compose_relpath = '../some_compose_dir'
        koji_proxy_class.return_value.getBuild.return_value = {
            'build_id' : self.build_id,
            'task_id' : self.task_id,
            'package_name' : self.package_name,
        }
        koji_proxy_class.return_value.listTags.return_value = (
            {'name': self.new_tag},
        )
        urlopen.side_effect = urllib.error.URLError('reason')
        koji_build = KojiBuild(self.settings, self.nvr)
        with self.assertRaises(ComposeNotAvailable):
            compose = koji_build.to_compose()
        entrypoint = f'{self.composes_baseurl}/{self.task_id}-{self.package_name}'
        # testcompose_timeout=3
        # testcompose_retry_interval=1.2
        # There should be 3 attempts (but not more) before the timeout
        urlopen.assert_has_calls([
            call(entrypoint, timeout=5),
            call(entrypoint, timeout=5),
            call(entrypoint, timeout=5)
        ])
        self.assertEqual(urlopen.call_count, 3)

    def test_convert_product_base(self, tag):
        expected_mapping = {
            'foo-1.2.3-bar' : {
                'name' : 'foo',
                'major' : '1',
                'minor' : '2',
                'other' : '3',
                'flag' : None,
            },
            'Woody-0.4.2-damaged-lost' : {
                'name' : 'Woody',
                'major' : '0',
                'minor' : '4',
                'other' : '2',
                'flag' : 'damaged',
            },
            'acme-1956.5.5-Gee-Whiz-z-z-z-z-z-z' : {
                'name' : 'acme',
                'major' : '1956',
                'minor' : '5',
                'other' : '5',
                'flag' : 'Gee-Whiz-z-z-z-z-z',
            },
        }
        for tag, expected_product_attrs in expected_mapping.items():
            with self.subTest(tag=tag):
                koji_build = KojiBuild(
                    self.settings,
                    self.nvr, build_id=self.build_id,
                    task_id=self.task_id, package_name=self.package_name,
                    new_tag=tag,
                )
                product = koji_build.to_product()
                for attr, expected_value in expected_product_attrs.items():
                    self.assertEqual(getattr(product, attr), expected_value)
