import json
import os
from libpermian.plugins import api


@api.cli.register_command_parser('run_awebui_tc')
def run_awebui_tc_command(base_parser, args):
    parser = base_parser
    parser.add_argument('path_to_anaconda',
                        help='Path to local Anaconda git repository where the test case is located')
    parser.add_argument('test_case_name',
                        help='Name of the test case as specified in tc.yaml')
    source_group = parser.add_mutually_exclusive_group()
    source_group.add_argument('--install-source',
                        default='https://fedorapeople.org/groups/anaconda/webui_permian_tests/sources/periodic/x86_64/',
                        help='URL of the installation source (compose os directory or unpack iso')
    source_group.add_argument('--compose',
                        help='Compose ID of a compose that should be used as installation source')
    parser.add_argument('--compose-url',
                        help='URL of the compose that should be used as installation source')
    parser.add_argument('--install-source-kernel',
                        default='images/pxeboot/vmlinuz',
                        help='Path to the kernel, relative to --install-source')
    parser.add_argument('--install-source-initrd',
                        default='images/pxeboot/initrd.img',
                        help='Path to the initrd, relative to --install-source')
    parser.add_argument('--architecture',
                        default='x86_64',
                        help='Needs to match your system architecture')
    options = parser.parse_args(args)

    event = {
        'type': 'run_subset',
        'run_subset': {
            'event': {
                'type': 'everything',
                'everything_testplan': {
                    'configurations': [{'architecture': 'x86_64', 'branch': 'master'}],
                    'point_person': '',
                },
            },
            'testcases': [options.test_case_name],
            'display_name': options.test_case_name,
        },
    }

    if options.compose:
        event['compose'] = {'id': options.compose}
        if 'compose_url' in options:
            event['compose']['location'] = options.compose_url
    else:
        event['InstallationSource'] = {
            "base_repo_id": "bootiso",
            "repos": {
                "bootiso": {
                    "x86_64": {
                        "os": options.install_source,
                        "kernel": options.install_source_kernel,
                        "initrd": options.install_source_initrd
                    }
                }
            }
        }

    os.environ.setdefault(
        "PIPELINE_library_directPath",
        os.path.join(options.path_to_anaconda, 'ui/webui/test/integration/'),
    )
    os.environ.setdefault(
        "PIPELINE_AnacondaWebUI_anaconda_repo",
        'file://' + os.path.abspath(options.path_to_anaconda),
    )

    return options, json.dumps(event)
