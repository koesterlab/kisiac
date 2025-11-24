from argparse import ArgumentDefaultsHelpFormatter, ArgumentParser

from kisiac.common import UserError, log_msg
from kisiac.runtime_settings import (
    GlobalSettings,
    UpdateHostSettings,
)
from kisiac.update import setup_config, update_host


def get_argument_parser() -> ArgumentParser:
    parser = ArgumentParser(formatter_class=ArgumentDefaultsHelpFormatter)
    GlobalSettings.register_cli_args(parser)
    subparsers = parser.add_subparsers(dest="subcommand", help="subcommand help")
    update_hosts = subparsers.add_parser(
        "update-hosts",
        help="Update given hosts",
        description="Update given hosts",
        formatter_class=ArgumentDefaultsHelpFormatter,
    )
    UpdateHostSettings.register_cli_args(update_hosts)
    subparsers.add_parser(
        "setup-config",
        help="Setup the kisiac configuration",
        description="Setup the kisiac configuration",
    )

    return parser


def main() -> None:
    try:
        parser = get_argument_parser()
        args = parser.parse_args()
        GlobalSettings.from_cli_args(args)
        match args.subcommand:
            case "update-hosts":
                UpdateHostSettings.from_cli_args(args)
                for host in UpdateHostSettings.get_instance().hosts:
                    update_host(host)
            case "setup-config":
                setup_config()
            case _:
                parser.print_help()
    except UserError as e:
        log_msg(e)
        exit(1)
