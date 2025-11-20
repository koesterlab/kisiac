from dataclasses import dataclass, field, fields, Field
from argparse import ArgumentParser, Namespace
from typing import Self

from kisiac.common import Singleton

@dataclass
class SettingsBase(Singleton):
    @classmethod
    def register_cli_args(cls, parser: ArgumentParser) -> None:
        for cls_field in fields(cls):
            positional = cls_field.metadata.get("positional", False)

            arg_name = cls_field.name.replace("_", "-")


            parse_method = getattr(cls, f"parse_{cls_field.name}", None)
            
            default = None
            if callable(cls_field.default_factory):
                default = cls_field.default_factory()
            elif cls_field.default is not None:
                default = cls_field.default

            kwargs = dict(
                type=parse_method or cls_field.type,
                help=cls_field.metadata["help"],
                default=default,
                nargs="+" if cls_field.type == list[str] else None,
            )
            if cls_field.metadata.get("required", False) and not positional:
                kwargs["required"] = True

            parser.add_argument(
                f"--{arg_name}" if not positional else arg_name,
                **kwargs,
            )

    @classmethod
    def from_cli_args(cls, args: Namespace) -> Self:
        def arg_to_field_value(cls_field: Field):
            value = getattr(args, cls_field.name.replace("_", "-"))
            if cls_field.default_factory is not None and value is None:
                assert callable(cls_field.default_factory)
                value = cls_field.default_factory()
            return value

        kwargs = {cls_field.name: arg_to_field_value(cls_field)  for cls_field in fields(cls)}
        return cls(**kwargs)


@dataclass
class GlobalSettings(SettingsBase):
    non_interactive: bool = field(default=False, metadata={"help": "Run in non-interactive mode"})


@dataclass
class UpdateHostSettings(SettingsBase):
    hosts: list[str] = field(
        default_factory=lambda: ["localhost"], metadata={"required": True, "positional": True, "help": "Hosts to update (default: localhost)"}
    )