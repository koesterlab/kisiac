from dataclasses import dataclass, field, fields, Field
from argparse import ArgumentParser, Namespace
from typing import Self, get_args, get_origin

from kisiac.common import Singleton


@dataclass
class SettingsBase(Singleton):
    @classmethod
    def register_cli_args(cls, parser: ArgumentParser) -> None:
        for cls_field in fields(cls):
            positional = cls_field.metadata.get("positional", False)

            arg_name = cls_field.name.replace("_", "-")

            parse_method = getattr(cls, f"parse_{cls_field.name}", None)
            arg_type = parse_method or cls_field.type

            default = None
            if callable(cls_field.default_factory):
                default = cls_field.default_factory()
            elif cls_field.default is not None:
                default = cls_field.default

            kwargs = dict(
                help=cls_field.metadata["help"],
            )
            if cls_field.metadata.get("required", False) and not positional:
                kwargs["required"] = True

            if arg_type is bool:
                kwargs["action"] = "store_true" if not default else "store_false"
            else:
                kwargs["default"] = default
                if cls_field.type is list or get_origin(cls_field.type) is list:
                    kwargs["type"] = get_args(cls_field.type)[0]
                    kwargs["nargs"] = "+"
                else:
                    kwargs["type"] = arg_type

            metavar = cls_field.metadata.get("metavar", None)
            if metavar is not None:
                kwargs["metavar"] = metavar

            parser.add_argument(
                f"--{arg_name}" if not positional else arg_name,
                **kwargs,
            )

    @classmethod
    def from_cli_args(cls, args: Namespace) -> Self:
        kwargs = {
            cls_field.name: getattr(args, cls_field.name) for cls_field in fields(cls)
        }
        return cls(**kwargs)


@dataclass
class GlobalSettings(SettingsBase):
    non_interactive: bool = field(
        default=False, metadata={"help": "Run in non-interactive mode"}
    )


@dataclass
class UpdateHostSettings(SettingsBase):
    hosts: list[str] = field(
        default_factory=lambda: ["localhost"],
        metadata={
            "required": True,
            "positional": True,
            "help": "Hosts to update (default: localhost)",
            "metavar": "HOST",
        },
    )
