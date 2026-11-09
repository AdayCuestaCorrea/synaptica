from typer.testing import CliRunner

from synaptica import __version__, cli, config

runner = CliRunner()


def test_version():
    result = runner.invoke(cli.app, ["--version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == f"syn {__version__}"


def test_doctor_passes(tmp_path, monkeypatch):
    monkeypatch.setenv("SYN_DATA_DIR", str(tmp_path))
    result = runner.invoke(cli.app, ["doctor"])
    assert result.exit_code == 0, result.stdout
    assert "✓ Python" in result.stdout
    assert str(tmp_path) in result.stdout


def test_doctor_fails_on_missing_required_var(monkeypatch):
    monkeypatch.setattr(
        config, "ENV_VARS", (config.EnvVar("SYN_TEST_KEY", "Test key", required=True),)
    )
    monkeypatch.delenv("SYN_TEST_KEY", raising=False)
    result = runner.invoke(cli.app, ["doctor"])
    assert result.exit_code == 1
    assert "✗ SYN_TEST_KEY: not set" in result.stdout


def test_doctor_never_prints_values(monkeypatch):
    monkeypatch.setattr(
        config, "ENV_VARS", (config.EnvVar("SYN_TEST_KEY", "Test key", required=True),)
    )
    monkeypatch.setenv("SYN_TEST_KEY", "s3cr3t-value")
    result = runner.invoke(cli.app, ["doctor"])
    assert result.exit_code == 0
    assert "s3cr3t-value" not in result.stdout
    assert "✓ SYN_TEST_KEY: set" in result.stdout


def test_doctor_fails_on_wrong_python(monkeypatch):
    monkeypatch.setattr(cli, "REQUIRED_PYTHON", (3, 99))
    result = runner.invoke(cli.app, ["doctor"])
    assert result.exit_code == 1
    assert "✗ Python" in result.stdout
