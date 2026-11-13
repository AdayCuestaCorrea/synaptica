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


def test_build_runs_dbt_with_the_data_dir_and_as_of(tmp_path, monkeypatch):
    calls = []

    class Done:
        returncode = 0

    def fake_run(cmd, env, check):
        calls.append((cmd, env))
        return Done()

    monkeypatch.setenv("SYN_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    result = runner.invoke(cli.app, ["build", "--as-of", "2026-11-09"])
    assert result.exit_code == 0
    cmd, env = calls[0]
    assert cmd[:2] == ["dbt", "build"] and cmd[-2:] == ["--vars", "{as_of: '2026-11-09'}"]
    assert env["SYN_DATA_DIR"] == str(tmp_path)


def _models(status):
    import httpx

    return httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(status, json={})))


def test_the_key_check_fails_red_when_missing_or_refused(monkeypatch):
    from synaptica.llm import check_key

    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    assert check_key("groq", _models(200)) == (False, "GROQ_API_KEY not set")
    monkeypatch.setenv("GROQ_API_KEY", "s3cr3t-value")
    assert check_key("groq", _models(401)) == (False, "groq refused the key (HTTP 401)")
    ok, detail = check_key("groq", _models(200))
    assert ok and "s3cr3t-value" not in detail
    assert check_key("ollama") == (True, "local provider, no key")


def test_doctor_llm_exits_1_without_the_key(tmp_path, monkeypatch):
    monkeypatch.setenv("SYN_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    result = runner.invoke(cli.app, ["doctor", "--llm", "groq"])
    assert result.exit_code == 1
    assert "✗ groq API key: GROQ_API_KEY not set" in result.stdout


def test_a_daily_limit_429_stops_at_once_and_others_are_retried(monkeypatch):
    import httpx
    import pytest

    from synaptica import llm

    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    calls = []

    def answer(body):
        def handler(request):
            calls.append(1)
            return httpx.Response(429, text=body, headers={"retry-after": "600"})

        return httpx.Client(transport=httpx.MockTransport(handler))

    day = "Rate limit reached for model `openai/gpt-oss-120b` on tokens per day (TPD): ..."
    with pytest.raises(llm.QuotaExhausted):
        llm.post_json(answer(day), "https://x/chat", {}, headers={})
    assert len(calls) == 1  # no retry: waiting cannot help
    calls.clear()
    with pytest.raises(llm.HttpError):
        llm.post_json(answer("on tokens per minute (TPM)"), "https://x/chat", {}, headers={})
    assert len(calls) == 5  # a minute limit is retried
