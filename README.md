<div align="center">

# JARVIS

### A voice-first desktop assistant for Windows

Talk to your computer. It listens, understands, and does the work - inside the
apps you already use.

by **VORNEX**

[![Python](https://img.shields.io/badge/python-3.12%2B-3776AB.svg)](#)
[![License](https://img.shields.io/badge/license-VORNEX-blue.svg)](LICENSE)

**English** &nbsp;·&nbsp; [فارسی](#persian)

</div>

---

<a id="english"></a>

## What JARVIS is

JARVIS is a desktop assistant you simply talk to. Speak in Persian or English and
it works inside real applications - opening chats, writing messages, typing into
documents, searching the web - by reading each app's actual controls instead of
guessing screen coordinates.

It is built by **VORNEX**.

## Highlights

| Feature | What it means |
| --- | --- |
| **Voice-first** | Wake word ("Hey Jarvis") or push-to-talk, with live conversation. |
| **Works in any app** | One engine reads any window's controls and acts only on what it can see and verify. |
| **One rule for messengers** | Sending works the same in Telegram, WhatsApp and more. Adding an app takes one line. |
| **Safe by design** | Anything irreversible - send, delete, buy - stops for your on-screen confirmation. It never messages the wrong chat. |
| **Remembers you** | Preferences and history persist across sessions and restarts. |
| **Extends itself** | When a capability is missing it offers to build the tool, then uses it immediately - no restart. |
| **Repairs itself** | If a tool fails it can rewrite and reload it, rolling back when the fix does not work. |
| **Phone control** | A built-in dashboard lets you drive JARVIS from your phone. |

## Quick start

```bash
git clone https://github.com/VORNEX-01/JARVIS-VORNEX.git
cd JARVIS-VORNEX
pip install -r requirements.txt
```

1. Put your Gemini API key in `config/api_keys.json`:

```json
{ "gemini_api_key": "YOUR_KEY", "gemini_api_keys": ["YOUR_KEY"] }
```

2. Run it:

```bash
python main.py
```

3. Say **"Hey Jarvis"** and ask.

## Adding a new app

Open `core/apps.py` and add one line:

```python
PROFILES = {
    "telegram": {"exe": ("telegram.exe",)},
    "myapp":    {"exe": ("myapp.exe",)},
}
```

The engine handles the rest.

## Built-in tools

18 tools are auto-discovered from `actions/`. Highlights: `desktop_agent`
(operates any app), `send_message`, `open_app`, `web_search`, `weather_report`,
`reminder`, `file_controller`, `computer_settings`, and `make_tool` + `call_tool`
for self-extension.

## Requirements

- Windows 10 / 11
- Python 3.12+
- A Gemini API key
- A microphone

<p align="center">
  <a href="https://instagram.com/vornex_web">Instagram</a> ·
  <a href="https://t.me/VORNEX_01">Telegram</a>
</p>

<p align="center">Made by VORNEX</p>

---


<a id="persian"></a>

<div dir="rtl" align="center">

[English](#english) &nbsp;·&nbsp; **فارسی**

</div>

<div dir="rtl">

## جارویس چیست؟

جارویس یک دستیارِ کامپیوتری است که تسلط کامل برروی سیستم دارد. درخواستت را فارسی یا
انگلیسی می‌گویی و او داخلِ برنامه‌های واقعی کار می‌کند — باز کردنِ گفت‌وگو،
نوشتنِ پیام، تایپ در سند، جست‌وجوی وب — و این کار را با خواندنِ کنترل‌های
واقعیِ همان پنجره انجام می‌دهد، نه با حدس‌زدنِ مختصاتِ صفحه.

این نرم‌افزار ساختهٔ **ورنکس** است.

## ویژگی‌ها

| ویژگی | یعنی چه |
| --- | --- |
| **صدامحور** | با کلمهٔ بیدارباش («هی جارویس») یا گفتنِ دستی، با گفت‌وگوی زنده. |
| **روی هر برنامه‌ای** | یک موتور، کنترل‌های هر پنجره را می‌خواند و فقط روی چیزی عمل می‌کند که ببیند و تأیید کند. |
| **یک قاعده برای پیام‌رسان‌ها** | ارسال در تلگرام، واتساپ و بیشتر یکسان است. افزودنِ یک برنامه یک خط است. |
| **ایمن به‌طور پیش‌فرض** | هر کارِ برگشت‌ناپذیر — ارسال، حذف، خرید — پشتِ تأییدِ روی صفحهٔ تو می‌ایستد و هرگز به گفت‌وگوی اشتباه پیام نمی‌دهد. |
| **تو را یادش می‌ماند** | ترجیح‌ها و تاریخچه بینِ نشست‌ها و بعد از ری‌استارت باقی می‌مانند. |
| **خودش را می‌سازد** | وقتی قابلیتی نبود، پیشنهاد می‌دهد ابزارش را بسازد و همان لحظه استفاده می‌کند — بدونِ ری‌استارت. |
| **خودش را ترمیم می‌کند** | اگر ابزاری خراب شود، خودش بازنویسی و دوباره بارگذاری می‌کند و در صورتِ شکست برمی‌گردد. |
| **کنترل از موبایل** | یک داشبوردِ داخلی می‌گذارد جارویس را از گوشی هم برانی. |

## شروع سریع

```bash
git clone https://github.com/VORNEX-01/JARVIS-VORNEX.git
cd JARVIS-VORNEX
pip install -r requirements.txt
```

۱. کلیدِ Gemini را در `config/api_keys.json` بگذار:

```json
{ "gemini_api_key": "YOUR_KEY", "gemini_api_keys": ["YOUR_KEY"] }
```

۲. اجرا کن:

```bash
python main.py
```

۳. بگو «هی جارویس» و درخواستت را بگو.

## افزودنِ یک برنامهٔ جدید

فایلِ `core/apps.py` را باز کن و یک خط اضافه کن:

```python
PROFILES = {
    "telegram": {"exe": ("telegram.exe",)},
    "myapp":    {"exe": ("myapp.exe",)},
}
```

بقیه‌اش با موتور است.

## ابزارهای داخلی

۱۸ ابزار به‌صورتِ خودکار از `actions/` پیدا می‌شوند. مهم‌ترین‌ها:
`desktop_agent` (کار در هر برنامه)، `send_message`، `open_app`، `web_search`،
`weather_report`، `reminder`، `file_controller`، `computer_settings`، و
`make_tool` و `call_tool` برای خودگستری.

## نیازها

- ویندوز ۱۰ یا ۱۱
- پایتون ۳٫۱۲ یا بالاتر
- کلیدِ Gemini
- یک میکروفون

</div>

---

<p align="center">
  <a href="https://instagram.com/vornex_web">Instagram</a> ·
  <a href="https://t.me/VORNEX_01">Telegram</a>
</p>

<p align="center" dir="rtl">ساخته شده توسط ورنکس</p>

