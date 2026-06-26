from pathlib import Path

from stable_core.security.secret_scan import scan_paths


def test_secret_scan_detects_key_like_patterns(tmp_path: Path) -> None:
    secret_file = tmp_path / "leak.md"
    secret_file.write_text("token=" + "sk-" + "A" * 48 + "\n", encoding="utf-8")

    report = scan_paths([secret_file])

    assert report["status"] == "failed"
    assert report["findings"][0]["path"].endswith("leak.md")
    assert report["findings"][0]["pattern_type"] == "api_key_like"
    assert "A" * 20 not in report["findings"][0]["redacted_preview"]


def test_secret_scan_passes_placeholder_files(tmp_path: Path) -> None:
    placeholder_file = tmp_path / ".env.example"
    placeholder_file.write_text(
        "DEEPSEEK_API_KEY=<set-in-env>\n"
        "HF_TOKEN=<optional-set-in-env>\n",
        encoding="utf-8",
    )

    report = scan_paths([placeholder_file])

    assert report == {"status": "passed", "findings": []}


def test_secret_scan_skips_ignored_artifact_directories(tmp_path: Path) -> None:
    ignored_dir = tmp_path / "models"
    ignored_dir.mkdir()
    ignored_file = ignored_dir / "weights.txt"
    ignored_file.write_text("token=" + "sk-" + "B" * 48, encoding="utf-8")

    report = scan_paths([tmp_path])

    assert report == {"status": "passed", "findings": []}


def test_secret_scan_cli_writes_json_report(tmp_path: Path) -> None:
    from stable_core.security.secret_scan import main

    scan_root = tmp_path / "scan"
    scan_root.mkdir()
    (scan_root / "safe.md").write_text("api_key_env: DEEPSEEK_API_KEY\n", encoding="utf-8")
    output_path = tmp_path / "secret_scan_report.json"

    exit_code = main(["--paths", str(scan_root), "--output", str(output_path)])

    assert exit_code == 0
    assert output_path.read_text(encoding="utf-8").strip().startswith("{")
