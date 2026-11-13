#!/usr/bin/env python3
"""抓取韭圈儿恐贪指数，写入 data/fear.json。供 GitHub Actions 定时运行。"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright

TZ = ZoneInfo("Asia/Shanghai")
ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "data" / "fear.json"

PAGES = {
    "sh": "https://app.jiucaishuo.com/pagesE/tool/fear_greed"
    "?urs=700001001&urpid=131308",
    "us": "https://app.jiucaishuo.com/pagesE/tool/fear_greed_new",
}

WAIT_JS = """
() => {
  const nodes = [...document.querySelectorAll('div[_echarts_instance_]')];
  return nodes.some((node) => {
    const chart = window.echarts && window.echarts.getInstanceByDom(node);
    const option = chart && chart.getOption();
    return option && option.series && option.series.length >= 2 &&
      option.xAxis && option.xAxis[0] && option.xAxis[0].data &&
      option.xAxis[0].data.length >= 45;
  });
}
"""

EXTRACT_JS = """
() => {
  const charts = [...document.querySelectorAll('div[_echarts_instance_]')]
    .map((node) => window.echarts && window.echarts.getInstanceByDom(node))
    .filter(Boolean);
  const option = charts.map((chart) => chart.getOption()).find((candidate) =>
    candidate.series && candidate.series.length >= 2 &&
    candidate.xAxis && candidate.xAxis[0] && candidate.xAxis[0].data &&
    candidate.xAxis[0].data.length >= 45 &&
    /恐惧|恐慌/.test(candidate.series[0].name || '')
  );
  if (!option) return null;

  const dates = option.xAxis[0].data.map(String);
  const fear = option.series[0].data.map(Number);
  const series = [];
  for (let i = 0; i < dates.length; i += 1) {
    if (Number.isFinite(fear[i])) series.push([dates[i], fear[i]]);
  }
  if (series.length < 45) return null;

  const tail = series.slice(-45);
  const values = tail.map((row) => row[1]);
  return {
    fear_greed: series[series.length - 1][1],
    fear_greed_45_high: Math.max(...values),
    fear_greed_45_low: Math.min(...values),
    last_date: series[series.length - 1][0],
    series: series.slice(-60),
  };
}
"""


def grab(page, key: str, attempts: int = 3) -> dict:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            page.goto(PAGES[key], wait_until="domcontentloaded", timeout=60_000)
            page.wait_for_function(WAIT_JS, timeout=45_000)
            data = page.evaluate(EXTRACT_JS)
            if not data:
                raise RuntimeError("未找到恐贪主图")
            print(f"[{key}] ok {data['last_date']} {data['fear_greed']}", file=sys.stderr)
            return data
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            print(f"[{key}] 第 {attempt} 次失败：{exc}", file=sys.stderr)
    raise RuntimeError(f"{key} 抓取失败：{last_error}")


def main() -> int:
    previous = {}
    if OUTPUT.exists():
        previous = json.loads(OUTPUT.read_text(encoding="utf-8"))

    result: dict = {
        "generated_at": datetime.now(TZ).isoformat(timespec="seconds"),
        "source": "app.jiucaishuo.com",
    }
    failed = []

    with sync_playwright() as playwright:
        channel = os.environ.get("PW_CHANNEL") or None
        browser = playwright.chromium.launch(channel=channel, args=["--no-sandbox"])
        context = browser.new_context(
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()

        for key in ("sh", "us"):
            try:
                result[key] = grab(page, key)
            except Exception as exc:  # noqa: BLE001
                failed.append(f"{key}: {exc}")
                if key in previous:
                    result[key] = previous[key]
                    result[key]["stale"] = True

        browser.close()

    if "sh" not in result or "us" not in result:
        print("抓取失败，未写入：" + "；".join(failed), file=sys.stderr)
        return 1

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    # 供 file:// 直接打开时使用：<script src> 不受 CORS 限制
    script = OUTPUT.with_suffix(".js")
    script.write_text(
        "window.FEAR_SNAPSHOT = "
        + json.dumps(result, ensure_ascii=False, indent=2)
        + ";\n",
        encoding="utf-8",
    )
    print(f"已写入 {OUTPUT}")
    if failed:
        print("部分失败（沿用旧值）：" + "；".join(failed), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
