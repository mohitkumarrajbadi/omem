"""Tests for the OMem CLI."""

from click.testing import CliRunner

from omem.cli import cli


class TestCLI:
    def setup_method(self):
        self.runner = CliRunner()

    def test_version(self):
        result = self.runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "version" in result.output.lower() or "0." in result.output

    def test_help(self):
        # Click supports --help and -h natively; -help is not a valid Click flag
        for help_flag in ["-h", "--help"]:
            result = self.runner.invoke(cli, [help_flag])
            assert result.exit_code == 0
            assert "Audit & rollback" in result.output
            # Simple first-run surface only
            assert "Get started:" in result.output
            assert "Everyday:" in result.output
            assert "omem commands" in result.output
            assert "Governance:" not in result.output
            assert "Connectors:" not in result.output
            assert "Aliases:" not in result.output
            assert "More:" not in result.output
            assert "\n  codebase" not in result.output
            assert "\n  ingest " not in result.output
            assert "\n  sync" not in result.output
            assert "dashboard" in result.output
            assert "\n  bench" not in result.output
            assert "\n  benchmark" not in result.output

    def test_commands_lists_full_catalog(self):
        result = self.runner.invoke(cli, ["commands"])
        assert result.exit_code == 0, result.output
        assert "Governance:" in result.output
        assert "Connectors:" in result.output
        assert "Memory:" in result.output

    def test_demo(self):
        # Default demo is kill-resume (OMem v1 primary story)
        result = self.runner.invoke(cli, ["demo"])
        assert result.exit_code == 0, result.output
        assert "PROCESS KILLED" in result.output or "killed" in result.output.lower()
        assert "resume" in result.output.lower()
        assert "Kill-the-Agent demo complete" in result.output
        assert "MongoDB" not in result.output

    def test_demo_poison_recovery(self):
        result = self.runner.invoke(cli, ["demo", "poison-recovery"])
        assert result.exit_code == 0, result.output
        assert "Baseline saved" in result.output
        assert "Memory poisoned" in result.output
        assert "untrusted_web_scrape" in result.output
        assert "REMEDIATED" in result.output
        assert "MongoDB" not in result.output

    def test_benchmark(self):
        result = self.runner.invoke(cli, ["benchmark", "--n", "50"])
        assert result.exit_code == 0
        assert "Benchmarking" in result.output
        assert "ms" in result.output

    def test_init(self):
        with self.runner.isolated_filesystem():
            result = self.runner.invoke(cli, ["init"])
            assert result.exit_code == 0
            assert "initialized" in result.output.lower()

    def test_stats(self):
        result = self.runner.invoke(cli, ["stats"])
        assert result.exit_code == 0
        assert "Memory statistics" in result.output
        assert "Total" in result.output

    def test_unknown_command_suggests(self):
        result = self.runner.invoke(cli, ["recal", "x"])
        assert result.exit_code != 0
        assert "Did you mean" in result.output
        assert "recall" in result.output

    def test_no_color_strips_ansi(self, monkeypatch):
        monkeypatch.setenv("NO_COLOR", "1")
        result = self.runner.invoke(cli, ["health"])
        assert result.exit_code == 0
        assert "\x1b[" not in result.output  # no ANSI escape codes
