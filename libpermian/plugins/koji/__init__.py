import os
import re
import json
import xmlrpc.client
import productmd
import requests
import time
import datetime

from libpermian.plugins import api
from libpermian.events.base import Event
from libpermian.events.structures.builtin import ProductStructure
from libpermian.events.structures.base import BaseStructure
from libpermian.cli.parser import bool_argument, ToPayload, AppendToPayload

from libpermian.plugins.compose import ComposeStructure
from libpermian.plugins.compose.exceptions import ComposeNotAvailable
from libpermian.plugins.beaker import BeakerCompose

TAG_REGEXPS = (
    # product-1.2.3-state
    re.compile('(?P<product>[^-]+)-(?P<major>[0-9]+).(?P<minor>[0-9]+).(?P<qr>[0-9]+)-(?P<state>[^-]+)'),
)

def parse_koji_tag(tag):
    for tag_regexp in TAG_REGEXPS:
        mo = tag_regexp.match(tag)
        if mo is None:
            continue
        return {
            'product' : mo.group('product'),
            'major' : mo.group('major'),
            'minor' : mo.group('minor'),
        }
    return None

@api.events.register_structure('koji_build')
class KojiBuild(BaseStructure):
    def __init__(self, settings, nvr, build_id=None, task_id=None, package_name=None, tags=None, new_tag=None):
        super().__init__(settings)
        self._info = None
        self.hub_url = self.settings.get('koji', 'hub_url')
        self.nvr = nvr
        self.build_id = None # have it set to None until it's discovered
        self.build_id = build_id or self.info['build_id']
        self._tags = tags
        self._new_tag = new_tag
        self.task_id = task_id or self.info['task_id']
        self.package_name = package_name or self.info['package_name']
        self.composes_baseurl = self.settings.get('koji', 'testcompose_baseurl')
        self._to_compose_exception = None

    @property
    def info(self):
        if self._info is not None:
            return self._info
        koji = xmlrpc.client.ServerProxy(self.hub_url)
        self._info = koji.getBuild(self.build_id or self.nvr, True) # use build_id if specified
        return self._info

    @property
    def tags(self):
        if self._tags is not None:
            return self._tags
        koji = xmlrpc.client.ServerProxy(self.hub_url, allow_none=True)
        self._tags = tuple(
            tag['name'] for tag in
            koji.listTags(self.build_id, None, False)
        )
        return self._tags

    @property
    def new_tag(self):
        if self._new_tag is not None:
            return self._new_tag
        self._new_tag = self.tags[0]
        return self._new_tag

    def to_compose(self):
        if self._to_compose_exception is not None:
            raise self._to_compose_exception
        if not self.composes_baseurl:
            return NotImplemented
        timeout = self.settings.getfloat('koji', 'testcompose_timeout')
        delay = self.settings.getfloat('koji', 'testcompose_retry_interval')
        wait_until = None if timeout <= 0 else datetime.datetime.now() + datetime.timedelta(seconds=timeout)
        entrypoint = f'{self.composes_baseurl}/{self.task_id}-{self.package_name}'
        entrypoint_dir = os.path.dirname(entrypoint)
        # try to locate the compose until timeout is reached
        while wait_until is None or datetime.datetime.now() < wait_until:
            response = requests.get(entrypoint)
            if response.ok:
                compose_relpaths = response.text.strip()
                compose_relpath = compose_relpaths.split('\n')[-1]
                compose_path = f'{entrypoint_dir}/{compose_relpath}'
                try:
                    compose_id = productmd.compose.Compose(compose_path).info.compose.id
                    return ComposeStructure(self.settings, compose_id, location=compose_path)
                except RuntimeError: # raised by productmd when failed to load compose metadata
                    pass
            # Don't repeat attempts if timeout was set to 0
            if timeout == 0:
                break
            time.sleep(delay)
        self._to_compose_exception = ComposeNotAvailable(f'''Entrypoint "{entrypoint}" either doesn't exist or points to a location which doesn't contain compose.''')
        raise self._to_compose_exception

    def to_beakerCompose(self):
        return BeakerCompose.from_compose(self.to_compose())

    def to_product(self):
        parsed_tag = parse_koji_tag(self.new_tag)
        return ProductStructure(
            self.settings,
            parsed_tag['product'],
            parsed_tag['major'],
            parsed_tag['minor'],
        )

@api.events.register('koji')
class KojiEvent(Event):
    def __init__(self, settings, type, koji_build, **kwargs):
        super().__init__(settings, type, koji_build=koji_build, **kwargs)

    def __str__(self):
        return f"{self.koji_build.package_name} {self.koji_build.nvr} {self.koji_build.new_tag}"

@api.cli.register_command_parser('koji_build_tag')
def koji_build_tag_command(base_parser, args):
    parser = base_parser
    parser.add_argument('nvr', action=ToPayload,
                        help='Koji build nvr like abc-1.2-3.fc4')
    # TODO: fix ToPayload to work with new-tag
    parser.add_argument('new_tag', action=ToPayload,
                        help='New tag that was added to the build')
    parser.add_argument('--event-type', default='koji.build.tag')
    parser.add_argument('--build-id', type=int, action=ToPayload,
                        help='Override build id')
    parser.add_argument('--task-id', type=int, action=ToPayload,
                        help='Override task id')
    parser.add_argument('--package-name', action=ToPayload,
                        help='Override package name')
    options = parser.parse_args(args)

    return options, json.dumps({'type': options.event_type, 'koji_build': options.payload})
