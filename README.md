<div align="center">

# VORNEX JARVIS

### SEE · UNDERSTAND · ACT · VERIFY

**A desktop assistant built by VORNEX.**

[![Windows](https://img.shields.io/badge/Windows-10%2F11-0078D4?style=flat-square&logo=windows&logoColor=white)](#)
[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?style=flat-square&logo=python&logoColor=white)](#)
[![Gemini](https://img.shields.io/badge/Gemini-Powered-4285F4?style=flat-square&logo=google&logoColor=white)](#)
[![License](https://img.shields.io/badge/License-see%20LICENSE-555555?style=flat-square)](LICENSE)

<br>

**[ English ](#english) · [ فارسی ](#فارسی)**

</div>

---

<a id="english"></a>

<div dir="ltr">

## JARVIS

JARVIS is the desktop assistant created by **VORNEX**.

It is built to work with your computer directly — opening applications, navigating interfaces, handling files, using the web, carrying out multi-step tasks, and checking whether important actions actually succeeded.

The idea is simple:

> **Tell JARVIS what you need. Let it handle the computer.**

---

## What it can do

| Area | Capabilities |
|---|---|
| Desktop | Control applications, windows, keyboard and mouse |
| Files | Find, read, organize and work with files |
| Web | Search the web and work with supported web tasks |
| Communication | Work with supported messaging workflows |
| Media | Open and interact with supported media services |
| System | Monitor system health and handle supported recovery |
| Development | Assist with coding and development workflows |
| Memory | Maintain useful context and learned information |
| Remote | Provide an authenticated remote dashboard |
| Safety | Confirm sensitive actions and verify important results |

JARVIS is designed around **general desktop interaction**.

Normal computer tasks do not depend on having a separate custom script for every application. When an application exposes standard desktop controls, JARVIS can work with those controls through its general interaction system.

---

## How it works

JARVIS follows a simple loop:

**Observe → Understand → Act → Verify**

It can inspect the current desktop, determine what needs to happen, perform the required interaction, and verify the result before treating the task as complete.

If success cannot be established, JARVIS is designed to stop rather than simply claim that the task worked.

---

## Quick Start

### Requirements

- Windows 10 or Windows 11
- Python 3.11+
- Gemini API key
- Microphone and audio output

### Install

```bash
git clone https://github.com/VORNEX-01/JARVIS-VORNEX.git
cd JARVIS-VORNEX
pip install -r requirements.txt
python main.py
````

On first launch, the setup screen guides you through the initial configuration.

Existing Gemini keys are loaded automatically when available and displayed as masked fields.

---

## Setup

The setup screen handles the essentials:

* Gemini API keys
* Operating system selection

Up to three Gemini API keys can be configured.

Existing keys do not need to be entered again. They can be replaced, added, or cleared from the setup screen.

Local credentials are kept outside Git.

---

## Desktop Control

JARVIS does not require a separate integration for every application.

Its desktop-control system can inspect application interfaces, identify available controls, perform interactions, and verify the resulting state.

This allows the same general interaction layer to work across applications such as:

* Notepad
* File Explorer
* Windows Settings
* Web browsers
* Messaging applications
* Other standard Windows desktop applications

Specialized integrations can still be used where they provide capabilities beyond ordinary desktop interaction.

---

## Remote Dashboard

JARVIS includes an authenticated dashboard for supported remote workflows.

When available, the application provides the information required to connect from a compatible device on the local network.

Remote access is protected by authentication and does not expose Gemini API credentials.

---

## Reliability & Recovery

JARVIS includes runtime monitoring, diagnostics and controlled recovery for supported situations.

The project also uses automated regression checks and real Windows desktop testing across areas such as:

* Desktop interaction
* Windows UI Automation
* Action discovery
* Result verification
* Runtime recovery
* Reconnection
* Configuration
* Credential handling
* Dashboard authentication
* Self-modification safeguards

---

## Project Structure

```text
JARVIS-VORNEX/
│
├── actions/       Application and task actions
├── core/          Runtime, desktop control and system logic
├── dashboard/     Remote dashboard
├── memory/        Memory and persistent application data
├── config/        Local configuration and application assets
├── tools/         Development and diagnostic utilities
│
├── main.py        Application entry point
├── ui.py          Main user interface
├── setup.py       Installation / setup support
└── requirements.txt
```

Local runtime state, credentials and machine-specific files are intentionally excluded from the repository.

---

## Privacy & Credentials

API keys and personal runtime data are stored locally.

Never commit credentials or private configuration to Git.

The repository ignores local files such as:

```text
config/api_keys.json
config/certs/
memory/long_term.json
.jarvis/
```

See [LICENSE](LICENSE) and [NOTICE](NOTICE) for project information.

---

## VORNEX

**VORNEX** is the maker and developer of JARVIS.

JARVIS is the desktop assistant.

### JARVIS

**See. Understand. Act. Verify.**

</div>

---

<a id="فارسی"></a>

<div dir="rtl">

# فارسی

## JARVIS

JARVIS دستیار دسکتاپ ساخته‌شده توسط **VORNEX** است.

JARVIS برای کار مستقیم با کامپیوتر طراحی شده؛ از باز کردن برنامه‌ها و کار با رابط‌ها گرفته تا مدیریت فایل‌ها، جستجو در وب، انجام کارهای چندمرحله‌ای و بررسی نتیجه عملیات مهم.

ایده ساده است:

> **کاری که می‌خواهید را بگویید؛ JARVIS انجام کار با کامپیوتر را مدیریت می‌کند.**

---

## قابلیت‌ها

| حوزه     | قابلیت‌ها                                          |
| -------- | -------------------------------------------------- |
| دسکتاپ   | کنترل برنامه‌ها، پنجره‌ها، کیبورد و ماوس           |
| فایل‌ها  | پیدا کردن و کار با فایل‌ها و پوشه‌ها               |
| وب       | جستجو و انجام کارهای پشتیبانی‌شده در وب            |
| ارتباطات | انجام بعضی فرایندهای پیام‌رسانی                    |
| رسانه    | کار با سرویس‌های رسانه‌ای پشتیبانی‌شده             |
| سیستم    | بررسی وضعیت سیستم و recovery در شرایط پشتیبانی‌شده |
| توسعه    | کمک در کارهای برنامه‌نویسی                         |
| حافظه    | نگهداری context و اطلاعات مفید                     |
| Remote   | داشبورد کنترل از راه دور احراز هویت‌شده            |
| امنیت    | تأیید عملیات حساس و بررسی نتیجه کار                |

JARVIS بر پایه **کنترل عمومی دسکتاپ** طراحی شده است.

برای کارهای معمول کامپیوتری لازم نیست برای هر برنامه یک اسکریپت جداگانه نوشته شود. اگر برنامه کنترل‌های استاندارد دسکتاپ را در اختیار بگذارد، JARVIS می‌تواند از سیستم عمومی تعامل با دسکتاپ استفاده کند.

---

## روش کار

چرخه اصلی JARVIS ساده است:

**مشاهده → درک → اجرا → بررسی**

JARVIS می‌تواند محیط فعلی را بررسی کند، تشخیص دهد چه کاری لازم است، آن را انجام دهد و نتیجه را بررسی کند.

اگر موفقیت قابل تأیید نباشد، سیستم نباید صرفاً فرض کند که کار انجام شده است.

---

## شروع سریع

### پیش‌نیازها

* Windows 10 یا Windows 11
* Python 3.11 یا جدیدتر
* Gemini API Key
* میکروفون و خروجی صدا

### نصب

```bash
git clone https://github.com/VORNEX-01/JARVIS-VORNEX.git
cd JARVIS-VORNEX
pip install -r requirements.txt
python main.py
```

در اولین اجرا، صفحه Setup تنظیمات اولیه را نمایش می‌دهد.

اگر کلیدهای Gemini قبلاً ذخیره شده باشند، به صورت خودکار پیدا می‌شوند و در Setup به شکل مخفی نمایش داده می‌شوند.

---

## Setup

در صفحه Setup تنظیمات اصلی انجام می‌شود:

* کلیدهای Gemini
* انتخاب سیستم‌عامل

امکان استفاده از حداکثر سه کلید Gemini وجود دارد.

کلیدهای قبلی لازم نیست دوباره وارد شوند و می‌توان آنها را جایگزین، اضافه یا حذف کرد.

اطلاعات حساس به صورت محلی نگهداری می‌شوند و وارد Git نمی‌شوند.

---

## کنترل دسکتاپ

JARVIS برای هر برنامه به یک integration جداگانه وابسته نیست.

سیستم کنترل دسکتاپ می‌تواند رابط برنامه را بررسی کند، کنترل‌های قابل استفاده را پیدا کند، عملیات لازم را انجام دهد و نتیجه را بررسی کند.

این سیستم می‌تواند برای برنامه‌هایی مانند:

* Notepad
* File Explorer
* Windows Settings
* مرورگرها
* برنامه‌های پیام‌رسان
* سایر برنامه‌های استاندارد Windows

استفاده شود.

در مواردی که یک integration اختصاصی قابلیت بیشتری ارائه دهد، می‌توان از آن نیز استفاده کرد.

---

## Remote Dashboard

JARVIS دارای Dashboard احراز هویت‌شده برای بعضی قابلیت‌های Remote است.

در صورت فعال بودن، اطلاعات لازم برای اتصال از یک دستگاه سازگار روی شبکه محلی در اختیار کاربر قرار می‌گیرد.

اطلاعات Gemini از طریق Remote Dashboard در اختیار دستگاه دیگر قرار نمی‌گیرد.

---

## پایداری و Recovery

JARVIS دارای monitoring، تشخیص خطا و recovery کنترل‌شده برای شرایط پشتیبانی‌شده است.

پروژه همچنین با تست‌های regression و تست واقعی روی محیط Windows بررسی می‌شود.

---

## ساختار پروژه

```text
JARVIS-VORNEX/
│
├── actions/       عملیات و قابلیت‌ها
├── core/          هسته، کنترل دسکتاپ و منطق سیستم
├── dashboard/     داشبورد Remote
├── memory/        حافظه و داده‌های برنامه
├── config/        تنظیمات محلی و assetها
├── tools/         ابزارهای توسعه و بررسی
│
├── main.py        نقطه شروع برنامه
├── ui.py          رابط اصلی
├── setup.py       پشتیبانی Setup
└── requirements.txt
```

اطلاعات شخصی، credentialها و داده‌های runtime به صورت محلی نگهداری می‌شوند و جزو repository نیستند.

---

## حریم خصوصی و اطلاعات حساس

کلیدهای API و اطلاعات شخصی برنامه روی سیستم محلی نگهداری می‌شوند.

هرگز اطلاعات حساس را وارد Git نکنید.

نمونه فایل‌های محلی:

```text
config/api_keys.json
config/certs/
memory/long_term.json
.jarvis/
```

برای اطلاعات پروژه به [LICENSE](LICENSE) و [NOTICE](NOTICE) مراجعه کنید.

---

## VORNEX

**VORNEX** سازنده و توسعه‌دهنده JARVIS است.

**JARVIS** دستیار دسکتاپ VORNEX است.

### JARVIS

**See. Understand. Act. Verify.**

</div>

---

<div align="center">

**Built by VORNEX**

</div>
