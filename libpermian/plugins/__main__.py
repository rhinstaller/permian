import argparse
from libpermian import plugins


def list_modules(names_only=False, paths_only=False):
    fmt = '{name}:{path}'
    if paths_only:
        fmt = '{path}'
    elif names_only:
        fmt = '{name}'

    plugins.load()
    plugins.loaded_plugin_modules()
    for p in plugins.loaded_plugin_modules():
        print(fmt.format(name=p.__name__, path=p.__path__[0]))


parser = argparse.ArgumentParser()
subparsers = parser.add_subparsers(dest='command')
parser_list = subparsers.add_parser('list',
                             help='Lists all enabled permian plugins')
parser_list_fmt = parser_list.add_mutually_exclusive_group(required=False)
parser_list_fmt.add_argument('--paths', action='store_true',
                             help='Lists paths of all enabled permian plugins')
parser_list_fmt.add_argument('--names', action='store_true',
                             help='Lists names of all enabled permian plugins')
args = parser.parse_args()

if args.command == 'list':
    list_modules(names_only=args.names, paths_only=args.paths)
