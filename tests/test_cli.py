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
            assert "Agent State Infrastructure SDK" in result.output

    def test_demo(self):
        result = self.runner.invoke(cli, ["demo"])
        assert result.exit_code == 0
        assert "OMem" in result.output
        assert "recall" in result.output.lower() or "simulating" in result.output.lower()

    def test_benchmark(self):
        result = self.runner.invoke(cli, ["benchmark", "--n", "50"])
        assert result.exit_code == 0
        assert "Initiating benchmark profile routines" in result.output
        assert "ms" in result.output

    def test_init(self):
        with self.runner.isolated_filesystem():
            result = self.runner.invoke(cli, ["init"])
            assert result.exit_code == 0
            assert "initialized" in result.output.lower()

    def test_stats(self):
        result = self.runner.invoke(cli, ["stats"])
        assert result.exit_code == 0
        assert "Total Index Nodes" in result.output
