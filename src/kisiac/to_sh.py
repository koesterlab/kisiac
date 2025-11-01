import importlib
import re
import textwrap
from typing import Callable


module_import_re: re.Pattern = re.compile(
    r"from kisiac.(?P<module>[a-z0-9_]+) import [a-zA-Z0-0_,+]"
)


def func_to_sh(func: Callable) -> str:
    func_name = func.__name__
    module_code = get_module_code(func.__module__)
    return textwrap.dedent(f"""
    {module_code}
    {func_name}()
    """)


def get_module_code(module_name: str) -> str:
    module_path = importlib.import_module(module_name).__file__
    assert module_path is not None

    with open(module_path, mode="r") as f:
        module_code = module_import_re.sub(
            lambda match: get_module_code(f"kisiac.{match.group('module')}"), f.read()
        )

    return module_code
