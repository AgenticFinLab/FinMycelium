"""Exercise the platform launcher with synthetic settings and no external services."""
from concurrent.futures import ThreadPoolExecutor
import os
import subprocess
import sys

from finmy.url_collector.MediaCollector.platform_crawler import PlatformCrawler


def test_runtime_configuration_is_private_to_each_child(tmp_path, monkeypatch):
    crawler = PlatformCrawler()
    config = crawler.mediacrawler_path / "config"
    original = {p: p.read_bytes() for p in (config / "db_config.py", config / "base_config.py")}
    monkeypatch.chdir(tmp_path)
    for key in ("DB_USER", "DB_PASSWORD", "DB_HOST", "DB_PORT", "DB_NAME", "DB_DIALECT"):
        monkeypatch.delenv(key, raising=False)
    (tmp_path / ".env").write_text("DB_USER=fixture\nDB_PORT=4406\nDB_NAME=sample\nDB_PASSWORD=file\n")
    monkeypatch.setenv("DB_PASSWORD", "fixture:@/quoted")
    parent = os.environ.copy()
    calls = {}
    real_run = subprocess.run

    def local_config_probe(args, *, cwd, env, timeout):
        platform = args[args.index("--platform") + 1]
        calls[platform] = (args, env)
        # Import the same two settings modules in a fresh process without launching a crawler.
        probe = ("import os; from config import db_config as db, base_config as base; "
                 "assert db.MYSQL_DB_PWD==os.environ['DB_PASSWORD'] and db.MYSQL_DB_PORT==4406; "
                 "assert base.CRAWLER_MAX_NOTES_COUNT==int(os.environ['FINMY_MEDIA_MAX_NOTES'])")
        return real_run([sys.executable, "-B", "-c", probe], cwd=cwd, env=env, timeout=10, check=True)

    monkeypatch.setattr(subprocess, "run", local_config_probe)
    with ThreadPoolExecutor(2) as pool:
        tasks = [pool.submit(crawler.run_crawler, platform, [word], max_notes=limit)
                 for platform, word, limit in (("wb", 'a"b', 7), ("bili", "另一项", 12))]
        assert all(task.result()["success"] for task in tasks)
    for platform, word, limit in (("wb", 'a"b', 7), ("bili", "另一项", 12)):
        args, env = calls[platform]
        assert "--keywords=" + word in args and env["FINMY_MEDIA_MAX_NOTES"] == str(limit)
        assert env["MYSQL_DB_USER"] == "fixture" and env["MYSQL_DB_NAME"] == "sample"
        assert env["MYSQL_DB_PWD"] not in args
    assert dict(os.environ) == parent
    assert original == {p: p.read_bytes() for p in original}


def test_unsupported_writer_fails_before_launch(tmp_path, monkeypatch):
    from finmy.url_collector.MediaCollector.database_settings import database_url
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DB_DIALECT", "postgres")
    def unexpected_launch(*args, **kwargs):
        raise AssertionError("Unexpected launch")

    monkeypatch.setattr(subprocess, "run", unexpected_launch)
    assert database_url().get_backend_name() == "postgresql"
    result = PlatformCrawler().run_crawler("wb", ["local"])
    assert not result["success"] and "MySQL only" in result["error"]
