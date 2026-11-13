#!/usr/bin/env python3
"""生成每日五行模板并发送邮件。由 GitHub Actions 在定时任务里调用。"""
from __future__ import annotations

import argparse
import json
import os
import smtplib
import ssl
import urllib.parse
import urllib.request
from datetime import datetime
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Shanghai")
ROOT = Path(__file__).resolve().parent.parent
FEAR_DATA = ROOT / "data" / "fear.json"
KLINE_URL = (
    "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
    "?param={symbol},day,,,320,qfq"
)
SHENZHEN = "sz399001"
CHINEXT = "sz399006"
NASDAQ = "us.NDX"

SMTP_DEFAULTS = {
    "qq.com": ("smtp.qq.com", 465),
    "foxmail.com": ("smtp.qq.com", 465),
    "163.com": ("smtp.163.com", 465),
    "126.com": ("smtp.126.com", 465),
    "gmail.com": ("smtp.gmail.com", 587),
    "outlook.com": ("smtp.office365.com", 587),
    "hotmail.com": ("smtp.office365.com", 587),
}


def ema(values: list[float], period: int) -> list[float]:
    alpha = 2 / (period + 1)
    out: list[float] = []
    for value in values:
        out.append(value if not out else value * alpha + out[-1] * (1 - alpha))
    return out


def fetch_daily(symbol: str) -> tuple[list[str], list[float]]:
    url = KLINE_URL.format(symbol=urllib.parse.quote(symbol, safe="."))
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.load(response)

    node = payload.get("data", {}).get(symbol) or {}
    rows = node.get("day") or node.get("qfqday") or []
    ordered = sorted((str(row[0]), float(row[2])) for row in rows if len(row) >= 3)
    if len(ordered) < 60:
        raise RuntimeError(f"{symbol} 日K不足（{len(ordered)} 根）")
    return [row[0] for row in ordered], [row[1] for row in ordered]


def macd(symbol: str) -> dict:
    dates, closes = fetch_daily(symbol)
    dif = [a - b for a, b in zip(ema(closes, 12), ema(closes, 26))]
    dea = ema(dif, 9)
    return {
        "date": dates[-1],
        "hist": 2 * (dif[-1] - dea[-1]),
        "dif": dif[-1],
        "dea": dea[-1],
    }


def build() -> dict:
    now = datetime.now(TZ)
    shenzhen = macd(SHENZHEN)
    chinext = macd(CHINEXT)
    nasdaq = macd(NASDAQ)
    fear = json.loads(FEAR_DATA.read_text(encoding="utf-8"))
    sh, us = fear["sh"], fear["us"]

    signed = lambda value: f"{value:+.2f}"  # noqa: E731
    sh_low = f"{float(sh['fear_greed_45_low']):.2f}" if sh.get("fear_greed_45_low") is not None else "--"
    us_low = f"{float(us['fear_greed_45_low']):.2f}" if us.get("fear_greed_45_low") is not None else "--"

    rows = [
        ("深圳指数日macd", signed(shenzhen["hist"]), ""),
        ("创业板指数日macd", signed(chinext["hist"]), ""),
        (
            "上证恐贪指数",
            f"{float(sh['fear_greed']):.2f}",
            f"高 {float(sh['fear_greed_45_high']):.2f} / 低 {sh_low}",
        ),
        ("纳斯达克指数日macd", signed(nasdaq["hist"]), ""),
        (
            "纳指恐贪指数",
            f"{float(us['fear_greed']):.2f}",
            f"高 {float(us['fear_greed_45_high']):.2f} / 低 {us_low}",
        ),
    ]

    text_lines = [
        f"深圳指数日macd：{signed(shenzhen['hist'])}",
        f"创业板指数日macd：{signed(chinext['hist'])}",
        f"上证恐贪指数：{float(sh['fear_greed']):.2f}，"
        f"上证恐贪指数近45日高点：{float(sh['fear_greed_45_high']):.2f}，"
        f"近45日低点：{sh_low}",
        f"纳斯达克指数日macd：{signed(nasdaq['hist'])}",
        f"纳指恐贪指数：{float(us['fear_greed']):.2f}，"
        f"纳指恐贪指数的近45日高点：{float(us['fear_greed_45_high']):.2f}，"
        f"近45日低点：{us_low}",
    ]
    intraday = shenzhen["date"] == now.strftime("%Y-%m-%d") and now.hour < 15
    footer = (
        f"A股 {shenzhen['date']} {now:%H:%M} "
        f"{'盘中，MACD 为暂定值' if intraday else '收盘'}；"
        f"上证恐贪 {sh['last_date']}，美股恐贪 {us['last_date']}。"
        "45日高低点取恐贪指数自身最高/最低值。"
    )

    def color(value: float) -> str:
        return "#f0455f" if value > 0 else "#23c07f" if value < 0 else "#e7ecf3"

    html_rows = []
    for index, (label, value, extra) in enumerate(rows):
        border = "border-top:1px solid #23272e;" if index else ""
        value_color = color(float(value)) if value[0] in "+-" else "#e7ecf3"
        html_rows.append(
            f'<tr><td style="{border}padding:12px 18px;color:#b9c2cf;font-size:14px">'
            f"{label}</td>"
            f'<td style="{border}padding:12px 18px;text-align:right;font-size:18px;'
            f'font-weight:600;color:{value_color};font-family:ui-monospace,Menlo,monospace">'
            f"{value}"
            + (
                f'<span style="color:#8b95a5;font-size:13px;font-weight:400"> · {extra}</span>'
                if extra
                else ""
            )
            + "</td></tr>"
        )

    html = f"""\
<div style="background:#0b0d10;padding:28px 20px;font-family:-apple-system,'PingFang SC',sans-serif">
  <div style="max-width:560px;margin:0 auto">
    <div style="color:#e7ecf3;font-size:18px;font-weight:600;margin-bottom:4px">每日市场模板</div>
    <div style="color:#8b95a5;font-size:12px;margin-bottom:14px">日线 MACD 12/26/9 · 恐贪 45 日高低点</div>
    <table style="width:100%;border-collapse:collapse;background:#14171c;border:1px solid #23272e;border-radius:12px;overflow:hidden">
      {''.join(html_rows)}
    </table>
    <div style="color:#8b95a5;font-size:11px;line-height:1.7;margin-top:12px">{footer}</div>
    <div style="color:#5c6673;font-size:11px;margin-top:8px">
      <a href="https://sean-daniel.github.io/market-daily-snapshot/" style="color:#8b95a5">网页版</a>
    </div>
  </div>
</div>"""

    return {
        "subject": f"每日市场模板 {now:%Y-%m-%d}",
        "text": "\n".join(text_lines) + "\n\n" + footer,
        "html": html,
    }


def send(subject: str, text: str, html: str) -> None:
    username = os.environ.get("MAIL_USERNAME", "").strip()
    password = os.environ.get("MAIL_PASSWORD", "").strip()
    recipients = [item.strip() for item in os.environ.get("MAIL_TO", "").split(",") if item.strip()]
    if not username or not password or not recipients:
        raise RuntimeError("缺少 MAIL_USERNAME / MAIL_PASSWORD / MAIL_TO")

    domain = username.split("@")[-1].lower()
    default_host, default_port = SMTP_DEFAULTS.get(domain, ("", 465))
    host = os.environ.get("MAIL_HOST") or default_host
    port = int(os.environ.get("MAIL_PORT") or default_port)
    if not host:
        raise RuntimeError("无法推断 SMTP 服务器，请设置 MAIL_HOST / MAIL_PORT")

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = formataddr(("每日市场模板", username))
    message["To"] = ", ".join(recipients)
    message.set_content(text)
    message.add_alternative(html, subtype="html")

    if port == 465:
        with smtplib.SMTP_SSL(host, port, context=ssl.create_default_context(), timeout=30) as server:
            server.login(username, password)
            server.send_message(message)
    else:
        with smtplib.SMTP(host, port, timeout=30) as server:
            server.starttls(context=ssl.create_default_context())
            server.login(username, password)
            server.send_message(message)


def main() -> int:
    parser = argparse.ArgumentParser(description="生成每日市场模板邮件")
    parser.add_argument("--dry-run", action="store_true", help="只打印，不发信")
    args = parser.parse_args()

    payload = build()
    if args.dry_run:
        print(payload["subject"])
        print()
        print(payload["text"])
        return 0

    send(payload["subject"], payload["text"], payload["html"])
    print("邮件已发送")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
