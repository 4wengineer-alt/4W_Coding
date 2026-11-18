import asyncio
import csv
import difflib
import hashlib
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from pydantic import BaseModel


# =========================================================
# ส่วนที่ 1: โครงสร้างการตั้งค่า (Configuration) และ Data Models
# =========================================================
BASE_DIR = Path(__file__).resolve().parent


@dataclass
class MonitorConfig:
    """เก็บค่าตั้งค่าระบบทั้งหมด รองรับการดึงจาก Environment Variable และการ Inject ตอนรัน Test"""

    telegram_bot_token: str = field(
        default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN", "")
    )
    telegram_chat_id: str = field(
        default_factory=lambda: os.getenv("TELEGRAM_CHAT_ID", "")
    )
    line_channel_access_token: str = field(
        default_factory=lambda: os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
    )
    line_user_id: str = field(
        default_factory=lambda: os.getenv("LINE_USER_ID", "")
    )
    ai_base_url: str = field(
        default_factory=lambda: os.getenv("AI_BASE_URL", "http://localhost:11434/v1")
    )
    ai_api_key: str = field(
        default_factory=lambda: os.getenv("AI_API_KEY", "local-llm")
    )
    model_name: str = field(
        default_factory=lambda: os.getenv("MODEL_NAME", "qwen2.5:14b")
    )
    snapshot_dir: Path = field(default_factory=lambda: BASE_DIR / "snapshots")
    csv_file: Path = field(default_factory=lambda: BASE_DIR / "price_changes_history.csv")
    log_file: Path = field(default_factory=lambda: BASE_DIR / "monitor_run.log")


class ChangeItem(BaseModel):
    item_or_feature: str
    old_value: str
    new_value: str
    change_type: str  # เช่น "ลดราคา", "ขึ้นราคา", "ฟีเจอร์ใหม่", "โปรโมชั่น"


class DiffAnalysisResult(BaseModel):
    has_significant_change: bool
    summary: str
    changes: list[ChangeItem]


def setup_logging(log_file: Path | None = None) -> None:
    """ตั้งค่าสมุดบันทึกการทำงาน (Log) ทั้งลงไฟล์และหน้าจอ"""
    target_log = log_file or (BASE_DIR / "monitor_run.log")
    target_log.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.FileHandler(target_log, encoding="utf-8"),
            logging.StreamHandler(),
        ],
        force=True,
    )


# =========================================================
# ส่วนที่ 2: Pure Functions สำหรับจัดการ Snapshot, Diff, Format และ CSV
# =========================================================
def get_snapshot_filepath(url: str, snapshot_dir: Path | None = None) -> Path:
    """สร้างที่อยู่ไฟล์ Snapshot ที่ปลอดภัยจากอักขระพิเศษ พร้อมแนบ MD5 hash ป้องกันชื่อซ้ำ"""
    target_dir = snapshot_dir or (BASE_DIR / "snapshots")
    clean_name = re.sub(r"[^a-zA-Z0-9]", "_", url.split("//")[-1])[:40]
    url_hash = hashlib.md5(url.encode("utf-8")).hexdigest()[:8]
    return target_dir / f"{clean_name}_{url_hash}.md"


def normalize_markdown(text: str) -> list[str]:
    """ตัดช่องว่างหัวท้ายและบรรทัดว่างทิ้ง เพื่อลด Noise ก่อนเทียบความต่าง"""
    return [line.strip() for line in text.splitlines() if line.strip()]


def compute_diff(old_text: str, new_text: str, context_lines: int = 3) -> str:
    """เปรียบเทียบข้อความ Markdown เก่าและใหม่ คืนค่าเฉพาะบรรทัดที่เปลี่ยน"""
    old_lines = normalize_markdown(old_text)
    new_lines = normalize_markdown(new_text)
    diff = difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile="Yesterday",
        tofile="Today",
        lineterm="",
        n=context_lines,
    )
    return "\n".join(diff)


def format_alert_message(url: str, analysis: DiffAnalysisResult) -> str:
    """จัดหน้าตาข้อความแจ้งเตือนให้อ่านง่ายบนมือถือ"""
    lines = [
        "🚨 แจ้งเตือน: คู่แข่งมีการเปลี่ยนแปลงข้อมูล!",
        f"🌐 เว็บไซต์: {url}",
        f"📝 สรุป: {analysis.summary}",
        "-------------------------",
    ]
    for idx, item in enumerate(analysis.changes, 1):
        lines.append(
            f"{idx}. [{item.change_type}] {item.item_or_feature}\n"
            f"   ❌ เดิม: {item.old_value}\n"
            f"   ✅ ใหม่: {item.new_value}"
        )
    return "\n".join(lines)


def append_to_csv(
    url: str,
    analysis: DiffAnalysisResult,
    csv_file: Path | None = None,
    now: datetime | None = None,
) -> None:
    """บันทึกประวัติการเปลี่ยนราคาลงไฟล์ CSV (ใช้ utf-8-sig เปิดอ่านภาษาไทยใน Excel ได้ทันที)"""
    target_csv = csv_file or (BASE_DIR / "price_changes_history.csv")
    file_exists = target_csv.exists()
    timestamp = (now or datetime.now()).strftime("%Y-%m-%d %H:%M:%S")

    target_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(target_csv, mode="a", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow([
                "วัน-เวลา",
                "เว็บไซต์",
                "ประเภทการเปลี่ยน",
                "ชื่อสินค้า/ฟีเจอร์",
                "ข้อมูลเดิม",
                "ข้อมูลใหม่",
                "สรุปจาก AI",
            ])
        for item in analysis.changes:
            writer.writerow([
                timestamp,
                url,
                item.change_type,
                item.item_or_feature,
                item.old_value,
                item.new_value,
                analysis.summary,
            ])


# =========================================================
# ส่วนที่ 3: เชื่อมต่อภายนอก (Telegram, LINE, Crawl4AI, OpenAI-compatible LLM)
# =========================================================
def send_telegram_alert(
    message: str,
    config: MonitorConfig,
    post_fn: Callable[..., Any] | None = None,
) -> bool:
    """ส่งข้อความเข้า Telegram คืนค่า True เมื่อส่งสำเร็จ, False เมื่อข้ามหรือล้มเหลว"""
    if not config.telegram_bot_token or not config.telegram_chat_id or "ใส่_" in config.telegram_bot_token:
        return False

    if post_fn is None:
        import requests

        post_fn = requests.post

    api_url = f"https://api.telegram.org/bot{config.telegram_bot_token}/sendMessage"
    payload = {"chat_id": config.telegram_chat_id, "text": message}
    try:
        resp = post_fn(api_url, json=payload, timeout=10)
        resp.raise_for_status()
        logging.info("ส่งแจ้งเตือนเข้า Telegram สำเร็จ!")
        return True
    except Exception as e:
        logging.error(f"ส่ง Telegram ไม่สำเร็จ: {e}")
        return False


def send_line_alert(
    message: str,
    config: MonitorConfig,
    post_fn: Callable[..., Any] | None = None,
) -> bool:
    """ส่งข้อความเข้า LINE Messaging API คืนค่า True เมื่อส่งสำเร็จ, False เมื่อข้ามหรือล้มเหลว"""
    if (
        not config.line_channel_access_token
        or not config.line_user_id
        or "ใส่_" in config.line_channel_access_token
    ):
        return False

    if post_fn is None:
        import requests

        post_fn = requests.post

    api_url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {config.line_channel_access_token}",
    }
    payload = {"to": config.line_user_id, "messages": [{"type": "text", "text": message}]}
    try:
        resp = post_fn(api_url, headers=headers, json=payload, timeout=10)
        resp.raise_for_status()
        logging.info("ส่งแจ้งเตือนเข้า LINE สำเร็จ!")
        return True
    except Exception as e:
        logging.error(f"ส่ง LINE ไม่สำเร็จ: {e}")
        return False


async def fetch_clean_markdown(url: str) -> str:
    """ใช้ Crawl4AI เปิดหน้าเว็บและตัดส่วนเกินออก เหลือเฉพาะ Clean Markdown"""
    from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig
    from crawl4ai.content_filter_strategy import PruningContentFilter
    from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator

    browser_conf = BrowserConfig(headless=True)
    md_generator = DefaultMarkdownGenerator(
        content_filter=PruningContentFilter(threshold=0.48, threshold_type="fixed")
    )
    run_conf = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        markdown_generator=md_generator,
        excluded_tags=["nav", "footer", "header", "aside", "script", "style"],
    )

    async with AsyncWebCrawler(config=browser_conf) as crawler:
        result = await crawler.arun(url=url, config=run_conf)
        if not result.success:
            raise RuntimeError(f"เปิดหน้าเว็บไม่สำเร็จ: {result.error_message}")
        return result.markdown.fit_markdown


def analyze_diff_with_ai(
    url: str,
    diff_text: str,
    config: MonitorConfig,
    client: Any = None,
) -> DiffAnalysisResult:
    """ส่งเฉพาะจุดต่าง (Diff) ให้ AI วิเคราะห์ว่าเป็นการเปลี่ยนราคา/โปรโมชั่นจริงหรือไม่"""
    if client is None:
        from openai import OpenAI

        client = OpenAI(base_url=config.ai_base_url, api_key=config.ai_api_key)

    system_prompt = (
        "คุณคือผู้ช่วยตรวจสอบราคาและฟีเจอร์ของร้านคู่แข่ง "
        "ผู้ใช้งานจะส่งเฉพาะจุดที่ข้อความเปลี่ยนไป (Diff) มาให้: "
        "เครื่องหมาย '-' คือของเก่าเมื่อวาน และ '+' คือของใหม่วันนี้ "
        "ช่วยสรุปหน่อยว่าเขาลดราคา ขึ้นราคา หรือออกโปรโมชั่น/ฟีเจอร์ใหม่อะไรบ้าง "
        "แต่ถ้าเป็นแค่ข้อความโฆษณาหรือเวลาที่เปลี่ยนไปเฉยๆ ให้ตอบว่า has_significant_change เป็น false"
    )

    response = client.beta.chat.completions.parse(
        model=config.model_name,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"เว็บไซต์: {url}\n\nจุดที่เปลี่ยนไป:\n{diff_text}"},
        ],
        response_format=DiffAnalysisResult,
        temperature=0.1,
    )
    return response.choices[0].message.parsed


# =========================================================
# ส่วนที่ 4: Orchestration (ควบคุม Flow การส่องเว็บและการแจ้งเตือน)
# =========================================================
async def monitor_competitor(
    url: str,
    config: MonitorConfig | None = None,
    fetcher: Callable[[str], Any] | None = None,
    analyzer: Callable[[str, str, MonitorConfig], DiffAnalysisResult] | None = None,
    telegram_sender: Callable[[str, MonitorConfig], bool] | None = None,
    line_sender: Callable[[str, MonitorConfig], bool] | None = None,
) -> str:
    """
    ตรวจสอบเว็บคู่แข่ง 1 URL และคืนสถานะการทำงาน:
    - "initialized": รันครั้งแรก สร้าง Snapshot ตั้งต้น
    - "unchanged": เนื้อหาเหมือนเดิม ข้าม AI (0 Token)
    - "ignored": เนื้อหาเปลี่ยนเล็กน้อย ไม่ใช่ราคา/ฟีเจอร์สำคัญ
    - "alerted": พบการเปลี่ยนสำคัญ บันทึก CSV และแจ้งเตือนแล้ว
    - "error": เกิดข้อผิดพลาด
    """
    cfg = config or MonitorConfig()
    cfg.snapshot_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = get_snapshot_filepath(url, snapshot_dir=cfg.snapshot_dir)

    fetch_fn = fetcher or fetch_clean_markdown
    analyze_fn = analyzer or analyze_diff_with_ai
    tg_fn = telegram_sender or send_telegram_alert
    ln_fn = line_sender or send_line_alert

    logging.info(f"กำลังเข้าไปส่องเว็บ: {url}")
    try:
        today_markdown = await fetch_fn(url)

        if not snapshot_path.exists():
            snapshot_path.write_text(today_markdown, encoding="utf-8")
            logging.info(f"จดบันทึกหน้าเว็บวันแรกเก็บไว้ที่: {snapshot_path.name}")
            return "initialized"

        yesterday_markdown = snapshot_path.read_text(encoding="utf-8")
        diff_result = compute_diff(yesterday_markdown, today_markdown, context_lines=3)

        if not diff_result:
            logging.info("หน้าเว็บเหมือนเมื่อวานเป๊ะ! ข้ามการทำงานของ AI")
            return "unchanged"

        logging.info(f"เจอจุดที่เปลี่ยนไป ({len(diff_result)} ตัวอักษร) กำลังให้ AI ช่วยอ่าน...")
        analysis = analyze_fn(url, diff_result, cfg)

        snapshot_path.write_text(today_markdown, encoding="utf-8")

        if analysis.has_significant_change:
            logging.warning(f"พบการเปลี่ยนราคา/ฟีเจอร์สำคัญ: {analysis.summary}")
            append_to_csv(url, analysis, csv_file=cfg.csv_file)
            alert_msg = format_alert_message(url, analysis)
            tg_fn(alert_msg, cfg)
            ln_fn(alert_msg, cfg)
            return "alerted"

        logging.info(f"มีข้อความเปลี่ยนนิดหน่อยแต่ไม่ใช่เรื่องราคา: {analysis.summary}")
        return "ignored"

    except Exception as e:
        logging.error(f"เกิดปัญหาตอนตรวจเว็บ {url}: {e}", exc_info=True)
        return "error"


async def run_all(urls: list[str], config: MonitorConfig | None = None) -> dict[str, str]:
    """รันตรวจทุก URL ตามลำดับ และคืนผลลัพธ์สรุปราย URL"""
    cfg = config or MonitorConfig()
    setup_logging(cfg.log_file)
    logging.info("=== เริ่มภารกิจส่องราคาคู่แข่งประจำวัน ===")
    results: dict[str, str] = {}
    for url in urls:
        results[url] = await monitor_competitor(url, config=cfg)
    logging.info("=== จบภารกิจประจำวัน ===\n")
    return results


if __name__ == "__main__":
    competitor_urls = [
        "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html"
    ]
    asyncio.run(run_all(competitor_urls))