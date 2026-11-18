import asyncio
import csv
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from competitor_diff_monitor import (
    ChangeItem,
    DiffAnalysisResult,
    MonitorConfig,
    analyze_diff_with_ai,
    append_to_csv,
    compute_diff,
    format_alert_message,
    get_snapshot_filepath,
    monitor_competitor,
    normalize_markdown,
    send_line_alert,
    send_telegram_alert,
)


# =========================================================
# Tier 1: Fast Unit Tests (Pure Functions & Data Models)
# =========================================================
class TestSnapshotAndDiff(unittest.TestCase):
    def test_get_snapshot_filepath_sanitizes_url_and_adds_hash(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            url = "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html"
            result = get_snapshot_filepath(url, snapshot_dir=tmp_path)

            self.assertEqual(result.parent, tmp_path)
            self.assertEqual(result.suffix, ".md")
            self.assertIn("books_toscrape_com_catalogue_a_light_in_", result.name)
            self.assertNotIn(":", result.name)
            self.assertNotIn("/", result.name)

    def test_normalize_markdown_strips_whitespace_and_empty_lines(self):
        raw = "\n  # สินค้า A  \n\n   ราคา 500 บาท   \n   \n"
        self.assertEqual(normalize_markdown(raw), ["# สินค้า A", "ราคา 500 บาท"])

    def test_compute_diff_returns_empty_string_when_content_identical(self):
        old_md = "# สินค้า A\nราคา 500 บาท\n"
        new_md = "  # สินค้า A  \n\n  ราคา 500 บาท  "
        self.assertEqual(compute_diff(old_md, new_md), "")

    def test_compute_diff_detects_price_change_lines(self):
        old_md = "# พู่กันเกรดศิลปิน\nราคา: 450 บาท\nสถานะ: มีสินค้า"
        new_md = "# พู่กันเกรดศิลปิน\nราคา: 390 บาท\nสถานะ: มีสินค้า"
        diff = compute_diff(old_md, new_md, context_lines=1)

        self.assertIn("-ราคา: 450 บาท", diff)
        self.assertIn("+ราคา: 390 บาท", diff)


class TestFormattingAndCsv(unittest.TestCase):
    def setUp(self):
        self.sample_analysis = DiffAnalysisResult(
            has_significant_change=True,
            summary="คู่แข่งลดราคาพู่กันและเพิ่มโปรส่งฟรี",
            changes=[
                ChangeItem(
                    item_or_feature="พู่กันเบอร์ 8",
                    old_value="450 บาท",
                    new_value="390 บาท",
                    change_type="ลดราคา",
                ),
            ],
        )

    def test_format_alert_message_renders_all_items_clearly(self):
        url = "https://example-artshop.com/brushes"
        msg = format_alert_message(url, self.sample_analysis)

        self.assertIn("🚨 แจ้งเตือน: คู่แข่งมีการเปลี่ยนแปลงข้อมูล!", msg)
        self.assertIn(f"🌐 เว็บไซต์: {url}", msg)
        self.assertIn("1. [ลดราคา] พู่กันเบอร์ 8", msg)
        self.assertIn("❌ เดิม: 450 บาท", msg)
        self.assertIn("✅ ใหม่: 390 บาท", msg)

    def test_append_to_csv_writes_header_once_and_appends_rows(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            csv_path = Path(tmp_dir) / "price_changes_history.csv"
            fixed_time = datetime(2026, 11, 18, 8, 0, 0)
            url = "https://example-artshop.com/brushes"

            append_to_csv(url, self.sample_analysis, csv_file=csv_path, now=fixed_time)
            append_to_csv(url, self.sample_analysis, csv_file=csv_path, now=fixed_time)

            with open(csv_path, mode="r", encoding="utf-8-sig", newline="") as f:
                rows = list(csv.reader(f))

            self.assertEqual(len(rows), 3)  # 1 header + 2 rows
            self.assertEqual(rows[0][0], "วัน-เวลา")
            self.assertEqual(rows[1][3], "พู่กันเบอร์ 8")

    def test_monitor_config_reads_environment_variables(self):
        with patch.dict(
            os.environ,
            {"TELEGRAM_BOT_TOKEN": "123456:ABC", "MODEL_NAME": "qwen2.5:7b"},
        ):
            cfg = MonitorConfig()
            self.assertEqual(cfg.telegram_bot_token, "123456:ABC")
            self.assertEqual(cfg.model_name, "qwen2.5:7b")


# =========================================================
# Tier 2: Mocked Unit & Integration Tests (Notifications, AI, & Full Flow)
# =========================================================
class TestExternalIntegrations(unittest.TestCase):
    def test_send_telegram_alert_skips_when_token_missing(self):
        cfg = MonitorConfig(telegram_bot_token="", telegram_chat_id="")
        mock_post = MagicMock()
        result = send_telegram_alert("hello", cfg, post_fn=mock_post)

        self.assertFalse(result)
        mock_post.assert_not_called()

    def test_send_telegram_alert_posts_payload_when_configured(self):
        cfg = MonitorConfig(telegram_bot_token="123:ABC", telegram_chat_id="999")
        mock_resp = MagicMock()
        mock_post = MagicMock(return_value=mock_resp)

        result = send_telegram_alert("แจ้งเตือนทดสอบ", cfg, post_fn=mock_post)

        self.assertTrue(result)
        mock_post.assert_called_once_with(
            "https://api.telegram.org/bot123:ABC/sendMessage",
            json={"chat_id": "999", "text": "แจ้งเตือนทดสอบ"},
            timeout=10,
        )
        mock_resp.raise_for_status.assert_called_once()

    def test_send_line_alert_posts_bearer_header_and_message(self):
        cfg = MonitorConfig(line_channel_access_token="LINE_TOKEN", line_user_id="U12345")
        mock_resp = MagicMock()
        mock_post = MagicMock(return_value=mock_resp)

        result = send_line_alert("แจ้งเตือน LINE", cfg, post_fn=mock_post)

        self.assertTrue(result)
        mock_post.assert_called_once_with(
            "https://api.line.me/v2/bot/message/push",
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer LINE_TOKEN",
            },
            json={"to": "U12345", "messages": [{"type": "text", "text": "แจ้งเตือน LINE"}]},
            timeout=10,
        )

    def test_analyze_diff_with_ai_returns_parsed_pydantic_result(self):
        cfg = MonitorConfig(model_name="qwen2.5:14b")
        expected = DiffAnalysisResult(
            has_significant_change=True,
            summary="ลดราคาสินค้า",
            changes=[
                ChangeItem(
                    item_or_feature="Book A",
                    old_value="£51.77",
                    new_value="£39.00",
                    change_type="ลดราคา",
                )
            ],
        )
        mock_client = MagicMock()
        mock_client.beta.chat.completions.parse.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(parsed=expected))]
        )

        result = analyze_diff_with_ai("https://example.com", "-£51.77\n+£39.00", cfg, client=mock_client)

        self.assertTrue(result.has_significant_change)
        self.assertEqual(result.changes[0].new_value, "£39.00")
        mock_client.beta.chat.completions.parse.assert_called_once()


class TestMonitorCompetitorFlow(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp_dir.name)
        self.config = MonitorConfig(
            telegram_bot_token="123:ABC",
            telegram_chat_id="999",
            line_channel_access_token="LINE_TOKEN",
            line_user_id="U12345",
            snapshot_dir=self.base / "snapshots",
            csv_file=self.base / "history.csv",
            log_file=self.base / "run.log",
        )
        self.url = "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html"

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_first_run_initializes_snapshot_without_ai_or_alerts(self):
        async def fake_fetch(_url: str) -> str:
            return "# Book A\nPrice: £51.77"

        mock_analyzer = MagicMock()
        mock_tg = MagicMock()
        mock_line = MagicMock()

        status = asyncio.run(
            monitor_competitor(
                self.url,
                config=self.config,
                fetcher=fake_fetch,
                analyzer=mock_analyzer,
                telegram_sender=mock_tg,
                line_sender=mock_line,
            )
        )

        self.assertEqual(status, "initialized")
        mock_analyzer.assert_not_called()
        mock_tg.assert_not_called()
        mock_line.assert_not_called()
        self.assertTrue(get_snapshot_filepath(self.url, self.config.snapshot_dir).exists())

    def test_unchanged_content_skips_ai_zero_tokens(self):
        snap_path = get_snapshot_filepath(self.url, self.config.snapshot_dir)
        snap_path.parent.mkdir(parents=True, exist_ok=True)
        snap_path.write_text("# Book A\nPrice: £51.77", encoding="utf-8")

        async def fake_fetch(_url: str) -> str:
            return "  # Book A  \n\n  Price: £51.77  "

        mock_analyzer = MagicMock()
        status = asyncio.run(
            monitor_competitor(
                self.url, config=self.config, fetcher=fake_fetch, analyzer=mock_analyzer
            )
        )

        self.assertEqual(status, "unchanged")
        mock_analyzer.assert_not_called()

    def test_significant_change_updates_snapshot_writes_csv_and_sends_alerts(self):
        snap_path = get_snapshot_filepath(self.url, self.config.snapshot_dir)
        snap_path.parent.mkdir(parents=True, exist_ok=True)
        snap_path.write_text("# Book A\nPrice: £51.77", encoding="utf-8")

        async def fake_fetch(_url: str) -> str:
            return "# Book A\nPrice: £39.00"

        mock_analyzer = MagicMock(
            return_value=DiffAnalysisResult(
                has_significant_change=True,
                summary="ลดราคาหนังสือ",
                changes=[
                    ChangeItem(
                        item_or_feature="Book A",
                        old_value="£51.77",
                        new_value="£39.00",
                        change_type="ลดราคา",
                    )
                ],
            )
        )
        mock_tg = MagicMock(return_value=True)
        mock_line = MagicMock(return_value=True)

        status = asyncio.run(
            monitor_competitor(
                self.url,
                config=self.config,
                fetcher=fake_fetch,
                analyzer=mock_analyzer,
                telegram_sender=mock_tg,
                line_sender=mock_line,
            )
        )

        self.assertEqual(status, "alerted")
        self.assertEqual(snap_path.read_text(encoding="utf-8"), "# Book A\nPrice: £39.00")
        self.assertTrue(self.config.csv_file.exists())
        mock_tg.assert_called_once()
        mock_line.assert_called_once()

    def test_insignificant_change_ignores_alerts_and_csv(self):
        snap_path = get_snapshot_filepath(self.url, self.config.snapshot_dir)
        snap_path.parent.mkdir(parents=True, exist_ok=True)
        snap_path.write_text("# Book A\nVisitors: 100", encoding="utf-8")

        async def fake_fetch(_url: str) -> str:
            return "# Book A\nVisitors: 105"

        mock_analyzer = MagicMock(
            return_value=DiffAnalysisResult(
                has_significant_change=False,
                summary="ยอดผู้เข้าชมเปลี่ยนเท่านั้น",
                changes=[],
            )
        )
        mock_tg = MagicMock()

        status = asyncio.run(
            monitor_competitor(
                self.url,
                config=self.config,
                fetcher=fake_fetch,
                analyzer=mock_analyzer,
                telegram_sender=mock_tg,
            )
        )

        self.assertEqual(status, "ignored")
        self.assertFalse(self.config.csv_file.exists())
        mock_tg.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)