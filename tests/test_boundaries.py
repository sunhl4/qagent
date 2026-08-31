from qagent.services.boundaries import scan_forbidden_imports


def test_no_science_package_imports() -> None:
    hits = scan_forbidden_imports()
    assert hits == []
