def test_data_dir_isolated():
    import config
    assert "tradebot_test_" in str(config.DATA_DIR)


def test_core_modules_import():
    import main  # noqa: F401
    import dashboard  # noqa: F401
