#!/usr/bin/env python3
"""
قیمت طلا/سکه/ارز را از وب‌سرویس می‌گیرد و prices.json را می‌سازد.

آدرس کامل API (همراه با کلید) از متغیر محیطی API_URL خوانده می‌شود،
که در GitHub → Settings → Secrets → Actions با نام API_URL ذخیره می‌شود.
اینطوری کلید هیچ‌جای کد و لاگ نمی‌افتد.

حالت اول (کشف ساختار): اگر MAP خالی بماند، اسکریپت فقط ساختار خروجی
سرویس را چاپ می‌کند تا ببینیم اسم فیلدها چیست.
"""

import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

# ------------------------------------------------------------------
# تنظیمات — بعد از دیدن خروجی، این بخش را پر می‌کنیم
# ------------------------------------------------------------------

# هر ردیف: (عنوانی که روی سایت نشان داده می‌شود، مسیر/کلیدواژه در خروجی، دلاری؟)
MAP = [
    # ("طلای ۱۸ عیار (گرم)", "geram18", False),
    # ("سکه امامی",          "sekee_emami", False),
]

# اگر سرویس قیمت را به ریال می‌دهد، اینجا 10 بگذارید تا به تومان تبدیل شود
DIVIDE_BY = 1

# ------------------------------------------------------------------

PRICE_KEYS = ("current", "price", "value", "sell", "rate", "last", "amount", "close")
CHANGE_KEYS = ("change_percent", "changePercent", "percent", "change", "diff", "d")
FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def fa(text):
    return str(text).translate(FA_DIGITS)


def fetch(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; site-price-bot)",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read().decode("utf-8"))


def walk(node, path=""):
    """همه شاخه‌های JSON را به صورت (مسیر، مقدار) برمی‌گرداند."""
    if isinstance(node, dict):
        for k, v in node.items():
            yield from walk(v, f"{path}.{k}" if path else str(k))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from walk(v, f"{path}[{i}]")
    else:
        yield path, node


def describe(data):
    print("\n" + "=" * 62)
    print("ساختار خروجی سرویس (این را برای تنظیم MAP لازم داریم):")
    print("=" * 62)
    leaves = list(walk(data))
    for path, value in leaves[:120]:
        text = str(value)
        if len(text) > 60:
            text = text[:60] + "…"
        print(f"  {path} = {text}")
    if len(leaves) > 120:
        print(f"  … و {len(leaves) - 120} مورد دیگر")
    print("=" * 62 + "\n")


def node_at(data, needle):
    """گره‌ای را پیدا می‌کند که مسیرش شامل needle باشد."""
    needle = needle.lower()

    def rec(node, path=""):
        if isinstance(node, dict):
            for k, v in node.items():
                p = f"{path}.{k}" if path else str(k)
                if needle in p.lower() or needle in str(k).lower():
                    return v
                found = rec(v, p)
                if found is not None:
                    return found
        elif isinstance(node, list):
            for i, v in enumerate(node):
                found = rec(v, f"{path}[{i}]")
                if found is not None:
                    return found
        return None

    return rec(data)


def to_number(value):
    try:
        return float(str(value).replace(",", "").replace("٬", "").strip())
    except (TypeError, ValueError):
        return None


def pull(node):
    """از یک گره، قیمت و درصد تغییر را بیرون می‌کشد."""
    price = change = None
    if isinstance(node, dict):
        for k in PRICE_KEYS:
            for key in node:
                if str(key).lower() == k:
                    price = to_number(node[key])
                    break
            if price is not None:
                break
        for k in CHANGE_KEYS:
            for key in node:
                if str(key).lower() == k.lower():
                    change = to_number(node[key])
                    break
            if change is not None:
                break
    else:
        price = to_number(node)
    return price, change


def main():
    url = os.environ.get("API_URL", "").strip()
    if not url:
        sys.exit("API_URL تنظیم نشده است. آن را در Secrets ریپو بسازید.")

    data = fetch(url)

    if not MAP:
        describe(data)
        print("MAP خالی است — فعلاً فقط ساختار چاپ شد و prices.json دست نخورد.")
        return

    describe(data)

    rates = []
    for title, needle, is_usd in MAP:
        node = node_at(data, needle)
        if node is None:
            print(f"⚠ پیدا نشد: {title}  (کلیدواژه: {needle})")
            continue

        price, change = pull(node)
        if price is None:
            print(f"⚠ قیمت خوانده نشد: {title}")
            continue

        price = int(price / DIVIDE_BY) if not is_usd else int(price)
        change = change or 0.0
        sign = "+" if change >= 0 else "-"
        change_txt = f"{sign}{fa(f'{abs(change):.1f}').replace('.', '٫')}٪"

        rates.append({"t": title, "v": price, "d": change_txt, "usd": is_usd})
        print(f"✓ {title}: {price}")

    if not rates:
        sys.exit("هیچ نرخی استخراج نشد — کلیدواژه‌های MAP را با خروجی بالا تطبیق دهید.")

    now = datetime.now(timezone(timedelta(hours=3, minutes=30)))  # وقت تهران
    out = {"updated_at": fa(now.strftime("%Y/%m/%d - %H:%M")), "rates": rates}

    with open("prices.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("\nprices.json ساخته شد.")


if __name__ == "__main__":
    main()
