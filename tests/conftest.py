def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "no_leaks(tasks=True, threads=True, blocking=True): mark test to run only on named environment",
    )
