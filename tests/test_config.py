"""Tester for konfigurasjonskonstanter i config.py."""

import bilagbot.config as cfg


class TestConfigDefaults:
    def test_claude_cli_timeout_default(self):
        assert isinstance(cfg.CLAUDE_CLI_TIMEOUT, int)
        assert cfg.CLAUDE_CLI_TIMEOUT == 180

    def test_fiken_http_timeout_default(self):
        assert isinstance(cfg.FIKEN_HTTP_TIMEOUT, float)
        assert cfg.FIKEN_HTTP_TIMEOUT == 30.0

    def test_fiken_max_retries_default(self):
        assert isinstance(cfg.FIKEN_MAX_RETRIES, int)
        assert cfg.FIKEN_MAX_RETRIES == 3

    def test_fiken_retry_backoff_default(self):
        assert isinstance(cfg.FIKEN_RETRY_BACKOFF, int)
        assert cfg.FIKEN_RETRY_BACKOFF == 2
