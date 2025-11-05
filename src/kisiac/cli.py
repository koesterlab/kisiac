from dataclasses import dataclass
from kisiac.common import run_cmd
from kisiac.config import Config
from kisiac.to_sh import func_to_sh
from kisiac.update import setup_config, update_host
from simple_parsing import ArgumentParser


@dataclass
class GlobalSettings:
    pass


@dataclass
class UpdateHostSettings:
    hosts: list[str] = ["localhost"]  # Hosts to update


@dataclass
class SetupConfigSettings:
    repo: str  # URL to the configuration repository


def get_argument_parser() -> ArgumentParser:
    parser: ArgumentParser = ArgumentParser()
    parser.add_arguments(GlobalSettings, dest="global_settings")
    subparsers = parser.add_subparsers(help="subcommand help")
    update_host = subparsers.add_parser("update-hosts", help="Update given hosts")
    update_host.add_arguments(UpdateHostSettings, dest="update_host_settings")

    setup_config = subparsers.add_parser("setup-config", help="Setup the kisiac configuration")
    setup_config.add_arguments(SetupConfigSettings, dest="setup_config_settings")

    return parser


def main() -> None:
    args = get_argument_parser().parse_args()
    match args.subparser_name:
        case "setup-config":
            run_cmd(
                ["python", "-"],
                input=func_to_sh(setup_config),
                sudo=True,
            )

        case "update-hosts":
            for host in args.update_host_settings.hosts:
                run_cmd(
                    ["python", "-"],
                    input=func_to_sh(update_host),
                    sudo=True,
                    host=host,
                    env={"KISIAC_CONFIG": Config().as_str()},
                )
