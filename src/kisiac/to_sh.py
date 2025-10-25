import importlib
import re
import textwrap
from typing import Callable

from kisiac.common import run_cmd


common_import_re: re.Pattern = re.compile(r"from kisiac import common")


def run_func_in_sh(func: Callable, hostname: str, sudo: bool) -> None:
    sh_script = func_to_sh(func)
    bash = "bash" if not sudo else "sudo bash"
    cmd = [bash] if hostname == "localhost" else ["ssh", hostname, bash]
    run_cmd(cmd, input=sh_script)


def func_to_sh(func: Callable) -> str:
    func_name = func.__name__
    module_code = get_module_code(func.__module__)

    return textwrap.dedent(
        f"""
        {func_name}() {{
            python - << EOF
            {module_code}
            {func_name}()
            EOF
        }}
        """
    )


def get_module_code(module_name: str, replace_common: bool = True) -> str:
    module_path = importlib.import_module(module_name).__file__
    assert module_path is not None

    with open(module_path, mode="r") as f:
        module_code = f.read()
        if replace_common:
            module_code = common_import_re.sub(
                get_module_code("kisiac.common", replace_common=False), module_code
            )

    return module_code
