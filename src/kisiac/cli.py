from dataclasses import dataclass
from kisiac.common import run_cmd
from kisiac.config import Config
from kisiac.to_sh import func_to_sh
from kisiac.update import update_host
from simple_parsing import ArgumentParser


@dataclass
class GlobalSettings:
    pass


@dataclass
class UpdateHostSettings:
    host: str = "localhost"  # Host to update


def get_argument_parser() -> ArgumentParser:
    parser: ArgumentParser = ArgumentParser()
    parser.add_arguments(GlobalSettings, dest="global_settings")
    subparsers = parser.add_subparsers(help="subcommand help")
    update_host = subparsers.add_parser("update-host", help="Update given host")
    update_host.add_arguments(UpdateHostSettings, dest="update_host_settings")

    return parser


def main() -> None:
    args = get_argument_parser().parse_args()
    if args.subparser_name == "update-host":
        run_cmd(
            ["python", "-"],
            input=func_to_sh(update_host),
            sudo=True,
            host=args.update_host_settings.host,
            env={"KISIAC_CONFIG": Config().as_str()},
        )
