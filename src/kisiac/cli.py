from kisiac.common import (
    GlobalSettings,
    UpdateHostSettings,
    UserError,
)
from kisiac.update import setup_config, update_host
from simple_parsing import ArgumentParser


def get_argument_parser() -> ArgumentParser:
    parser: ArgumentParser = ArgumentParser()
    parser.add_arguments(GlobalSettings, dest="global_settings")
    subparsers = parser.add_subparsers(dest="subcommand", help="subcommand help")
    update_host = subparsers.add_parser("update-hosts", help="Update given hosts")
    update_host.add_arguments(UpdateHostSettings, dest="update_host_settings")

    setup_config = subparsers.add_parser(
        "setup-config", help="Setup the kisiac configuration"
    )

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
