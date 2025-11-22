import subprocess as sp


def test_all():
    for i in range(2):
        print(f"Run {i}")
        sp.run(
            [
                "kisiac",
                "--non-interactive",
                "update-hosts",
                "--skip-system-upgrade",
                "localhost",
            ],
            check=True,
        )
