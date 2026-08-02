#!/usr/bin/env python3
"""
قیمت طلا و سکه را از وب‌سرویس nerkh.io می‌گیرد و prices.json را می‌سازد.

توکن از متغیر محیطی NERKH_TOKEN خوانده می‌شود
(GitHub → Settings → Secrets and variables → Actions → NERKH_TOKEN)
و به صورت هدر Authorization: Bearer ارسال می‌شود.
"""

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

BASE = "https://api.nerkh.io/v1/prices/json/"

# (عنوان روی سایت، مسیر بعد از BASE، دلاری؟)
# اگر نماد اشتباه باشد سرویس 404 می‌دهد و همان یک قلم رد می‌شود، بقیه کار می‌کنند.
ITEMS = [
    ("طلای ۱۸ عیار (گرم)", "gold/GOLD18K", False),
    ("طلای ۲۴ عیار (گرم)", "gold/GOLD24K", False),
    ("سکه امامی",          "gold/COIN_EMAMI", False),
    ("اونس جهانی",         "gold/ONS", True),
]

# اگر سرویس ریال می‌دهد، 10 بگذارید تا تومان شود
DIVIDE_BY = 1

PRICE_KEYS = ("current", "price", "value", "sell", "rate", "last", "amount", "close")
CHANGE_KEYS = ("change_percent", "changepercent", "percent", "change", "diff")
FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")

first_dump_done = False
service_date = None


def fa(text):
    return str(text).translate(FA_DIGITS)


def fetch(path, token):
    req = urllib.request.Request(
        BASE + path,
        headers={
            "Authorization": "Bearer " + token,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (compatible; site-price-bot)",
        },
    )
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read().decode("utf-8"))


def walk(node, path=""):
    if isinstance(node, dict):
        for k, v in node.items():
            yield from walk(v, f"{path}.{k}" if path else str(k))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from walk(v, f"{path}[{i}]")
    else:
        yield path, node


def grab_date(data):
    """تاریخ شمسی خود سرویس را برمی‌دارد."""
    global service_date
    if service_date:
        return
    for path, value in walk(data):
        if path.split(".")[-1].lower() in ("date", "datetime", "update"):
            text = str(value).strip()
            if len(text) >= 10:
                service_date = text[:16]  # تا دقیقه
                return


def load_previous():
    """قیمت‌های اجرای قبلی را می‌خواند تا درصد تغییر واقعی حساب شود."""
    try:
        with open("prices.json", encoding="utf-8") as f:
            return {r["t"]: r["v"] for r in json.load(f).get("rates", [])}
    except Exception:
        return {}


def dump_once(data):
    """ساختار اولین پاسخ موفق را چاپ می‌کند تا اگر لازم شد اصلاحش کنیم."""
    global first_dump_done
    if first_dump_done:
        return
    first_dump_done = True
    print("\n" + "=" * 58)
    print("ساختار پاسخ سرویس:")
    for p, v in list(walk(data))[:60]:
        text = str(v)
        print(f"  {p} = {text[:60] + '…' if len(text) > 60 else text}")
    print("=" * 58 + "\n")


def to_number(value):
    try:
        return float(str(value).replace(",", "").replace("٬", "").strip())
    except (TypeError, ValueError):
        return None


def pull(data):
    """قیمت و درصد تغییر را از هر ساختاری بیرون می‌کشد."""
    price = change = None
    for path, value in walk(data):
        leaf = path.split(".")[-1].lower()
        if price is None and leaf in PRICE_KEYS:
            price = to_number(value)
        if change is None and leaf in CHANGE_KEYS:
            change = to_number(value)
    return price, change


def main():
    token = os.environ.get("NERKH_TOKEN", "").strip()
    if not token:
        sys.exit("NERKH_TOKEN تنظیم نشده است. آن را در Secrets ریپو بسازید.")

    previous = load_previous()
    rates = []
    for title, path, is_usd in ITEMS:
        try:
            data = fetch(path, token)
        except urllib.error.HTTPError as e:
            print(f"⚠ {title} — خطای {e.code} روی {path}")
            if e.code == 401:
                sys.exit("توکن پذیرفته نشد. اعتبار توکن را بررسی کنید.")
            continue
        except Exception as e:
            print(f"⚠ {title} — {e}")
            continue

        dump_once(data)
        grab_date(data)
        price, change = pull(data)
        if price is None:
            print(f"⚠ {title} — قیمت در پاسخ پیدا نشد")
            continue

        price = int(price) if is_usd else int(price / DIVIDE_BY)

        # اگر سرویس درصد تغییر نداد، از قیمت اجرای قبلی حساب می‌کنیم
        if change is None:
            old = previous.get(title)
            change = ((price - old) / old * 100) if old else 0.0
        sign = "+" if change >= 0 else "-"
        change_txt = f"{sign}{fa(f'{abs(change):.1f}').replace('.', '٫')}٪"

        rates.append({"t": title, "v": price, "d": change_txt, "usd": is_usd})
        print(f"✓ {title}: {price}")

    if not rates:
        sys.exit("هیچ نرخی گرفته نشد — نمادهای ITEMS را با مستندات تطبیق دهید.")

    if service_date:
        stamp = fa(service_date.replace("-", "/").replace(" ", " - "))
    else:
        now = datetime.now(timezone(timedelta(hours=3, minutes=30)))  # وقت تهران
        stamp = fa(now.strftime("%Y/%m/%d - %H:%M"))

    out = {"updated_at": stamp, "rates": rates}

    with open("prices.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\nprices.json ساخته شد با {len(rates)} قلم.")


if __name__ == "__main__":
    main()
