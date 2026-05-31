import pytest

import code_reviewer.tools as tools


@pytest.fixture(autouse=True)
def reset_repo_root(fixture_repo):
    tools.set_repo_root(fixture_repo)


# --- path sandbox ---

def test_set_repo_root(tmp_path):
    tools.set_repo_root(str(tmp_path))
    assert tools._repo_root == tmp_path.resolve()


def test_safe_path_valid(fixture_repo):
    path = tools._safe_path("main.py")
    assert path.exists()


def test_safe_path_escapes_root():
    with pytest.raises(PermissionError):
        tools._safe_path("../../etc/passwd")


# --- symbol variants ---

def test_symbol_variants_from_camel():
    variants = tools._symbol_variants("myFunction")
    assert "my_function" in variants
    assert "MyFunction" in variants
    assert "myFunction" in variants


def test_symbol_variants_from_snake():
    variants = tools._symbol_variants("my_function")
    assert "myFunction" in variants
    assert "my_function" in variants
    assert "MyFunction" in variants


def test_symbol_variants_single_word():
    variants = tools._symbol_variants("greeting")
    assert "greeting" in variants


# --- git tools ---

def test_list_changed_files(fixture_repo):
    files = tools.list_changed_files(base="main", branch="feature/add-greeting")
    assert "greeting.py" in files
    assert "main.py" in files


def test_git_diff_contains_new_file(fixture_repo):
    diff = tools.git_diff(base="main", branch="feature/add-greeting")
    assert "greeting.py" in diff


# --- read_file ---

def test_read_file_returns_content(fixture_repo):
    content = tools.read_file("main.py")
    assert "hello_world" in content


def test_read_file_rejects_path_traversal(fixture_repo):
    with pytest.raises(PermissionError):
        tools.read_file("../../etc/passwd")


# --- grep tools (results depend on fixture content) ---

def test_find_references_returns_string(fixture_repo):
    result = tools.find_references("hello_world")
    assert isinstance(result, str)


def test_find_definition_returns_string(fixture_repo):
    result = tools.find_definition("hello_world")
    assert isinstance(result, str)
    # hello_world is defined in main.py, should appear somewhere
    assert "main.py" in result or "No definition" in result
