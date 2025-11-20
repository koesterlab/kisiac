from argparse import ArgumentDefaultsHelpFormatter, ArgumentParser

from kisiac.common import UserError
from kisiac.runtime_settings import (
    GlobalSettings,
    UpdateHostSettings,
)
from kisiac.update import setup_config, update_host


def get_argument_parser() -> ArgumentParser:
    parser = ArgumentParser(formatter_class=ArgumentDefaultsHelpFormatter)
    GlobalSettings.register_cli_args(parser)
    subparsers = parser.add_subparsers(dest="subcommand", help="subcommand help")
    update_hosts = subparsers.add_parser("update-hosts", help="Update given hosts", formatter_class=ArgumentDefaultsHelpFormatter)
    UpdateHostSettings.register_cli_args(update_hosts)
    subparsers.add_parser("setup-config", help="Setup the kisiac configuration")

    return parser


def main() -> None:
    try:
        parser = get_argument_parser()
        args = parser.parse_args()
        match args.subcommand:
            case "update-hosts":
                for host in args.update_host_settings.hosts:
                    update_host(host)
            case "setup-config":
                setup_config()
            case _:
                parser.print_help()
    except UserError as e:
        print(e)
        exit(1)
