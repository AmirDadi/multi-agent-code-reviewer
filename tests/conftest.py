import subprocess

import pytest


@pytest.fixture(scope="session")
def fixture_repo(tmp_path_factory):
    """
    A real git repo with two branches for integration-level tests.

    main:
        main.py  — defines hello_world()

    feature/add-greeting:
        greeting.py  — has a hardcoded secret (intentional, for security tests)
        main.py      — updated to call get_greeting()
    """
    repo = tmp_path_factory.mktemp("repo")

    def git(*args):
        subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)

    git("init", "-b", "main")
    git("config", "user.name", "tester")
    git("config", "user.email", "tester@example.com")

    # main branch
    (repo / "main.py").write_text("def hello_world():\n    return 'hello'\n")
    git("add", ".")
    git("commit", "-m", "initial")

    # feature branch
    git("checkout", "-b", "feature/add-greeting")
    (repo / "greeting.py").write_text(
        "import os\n\n"
        "SECRET_KEY = 'hardcoded-bad-secret'\n\n"
        "def get_greeting(name: str) -> str:\n"
        "    return f'Hello, {name}'\n"
    )
    (repo / "main.py").write_text(
        "from greeting import get_greeting\n\n"
        "def hello_world():\n"
        "    return get_greeting('world')\n"
    )
    git("add", ".")
    git("commit", "-m", "add greeting module")
    git("checkout", "main")

    return str(repo)
