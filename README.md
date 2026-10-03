# VORNEX JARVIS

> **A real-time AI desktop assistant by VORNEX — built to see, understand, act, and verify.**

JARVIS is the AI desktop assistant created by **VORNEX**.

It is designed to work with your computer as a real assistant — not simply answer questions, but understand what you want, interact with your desktop, perform multi-step tasks, and verify important results.

The idea is simple:

**You tell JARVIS what you want. JARVIS handles the computer work.**

---

## ✨ What is JARVIS?

JARVIS is a live AI assistant for your computer.

It can:

- 👁️ Understand the current desktop
- 🖱️ Interact with applications
- ⌨️ Type and control the keyboard
- 🪟 Work with Windows applications
- 📂 Work with files and folders
- 🌐 Search and use the web
- 💬 Send supported messages
- ▶️ Work with supported media
- 🛠️ Assist with development tasks
- 🌦️ Get weather information
- ✈️ Search for flights
- 🎮 Handle supported game and update tasks
- 🖥️ Monitor system health
- 🔄 Recover from certain runtime and connection problems
- 🧠 Use useful context across tasks
- 🔐 Ask for confirmation before sensitive actions
- ✅ Verify important actions instead of simply assuming they worked

JARVIS is designed around **general desktop interaction**.

That means ordinary computer tasks should not require a separate custom script for every application.

If an application exposes normal desktop controls, JARVIS can interact with it through its general computer-control system.

---

# 🚀 Quick Start

## Requirements

You need:

- Windows 10 or Windows 11
- Python 3.11 or newer
- A Gemini API key
- A working microphone and audio output

---

## 1. Download JARVIS

Clone the repository:

```bash
git clone https://github.com/VORNEX/JARVIS-VORNEX.git
cd JARVIS-VORNEX
````

---

## 2. Install

Install the required dependencies:

```bash
pip install -r requirements.txt
```

---

## 3. Start JARVIS

Run:

```bash
python main.py
```

On the first launch, JARVIS opens its setup screen.

The setup guides you through the initial configuration.

After that, you normally do not need to configure everything again.

---

# 🔑 Gemini API Keys

JARVIS uses Gemini for its AI reasoning.

You can configure up to **three Gemini API keys**.

Existing keys are automatically loaded when available and displayed securely as masked fields.

You do **not** need to enter your saved keys every time JARVIS starts.

From the setup screen, you can:

* Replace a key
* Add another key
* Clear a key
* Keep your existing keys

Your API key configuration stays on your computer and is excluded from Git.

---

# 🖥️ Operating System

During setup, select your operating system.

The current primary desktop experience is designed for Windows.

Once selected, the operating system is saved locally so you do not need to select it every time.

---

# 🎙️ Talk to JARVIS Naturally

You do not need to know how JARVIS works internally.

You do not need to select tools.

You do not need to write scripts for normal tasks.

Just tell JARVIS what you want.

For example:

> Open Notepad and write "VORNEX JARVIS is online."

> Open Chrome and search for today's weather.

> Find the file I downloaded yesterday.

> Open YouTube.

> Type this message into Telegram.

> Open Windows Settings and turn on Bluetooth.

> Find the latest information about this topic.

> Check whether my computer is running normally.

JARVIS decides how to perform the task.

---

# 🧠 General Desktop Intelligence

One of the main goals of JARVIS is to make computer control **general instead of application-specific**.

JARVIS can:

1. Observe the current application
2. Understand available controls
3. Decide what needs to happen
4. Perform the required action
5. Check the result
6. Continue when more steps are needed
7. Stop when it cannot verify success

This allows the same desktop-control system to work across many applications.

Examples include:

* Notepad
* File Explorer
* Windows Settings
* Web browsers
* Messaging applications
* Other standard Windows desktop applications

Specialized integrations can still exist when they provide useful capabilities, but normal desktop interaction does not depend on having a custom integration for every application.

---

# 🔐 Safety

JARVIS includes multiple safety mechanisms.

Sensitive or potentially destructive actions can require user confirmation.

Important actions can also be verified after execution.

JARVIS is designed not to treat an action as successful simply because a command was sent.

The project also includes protections around:

* API credentials
* Remote access
* Sensitive execution
* Self-modification
* Runtime recovery
* Action verification

---

# 📱 Remote Dashboard

JARVIS includes a remote dashboard for supported remote-control workflows.

When the dashboard is available, JARVIS displays the required local network information.

A compatible device on the same network can use the dashboard for supported remote interactions.

Remote access is protected by authentication and does not expose your Gemini API keys.

---

# ⚙️ Automatic Recovery

JARVIS includes runtime monitoring and controlled recovery.

It can detect certain problems involving:

* Network connections
* Runtime failures
* Resource issues
* Tool failures

For supported situations, JARVIS can diagnose the problem and attempt recovery automatically.

The goal is to reduce the need for manually restarting or repairing the assistant.

---

# 🧪 Reliability

JARVIS is developed with both offline regression testing and real desktop testing.

The project tests important areas such as:

* Action discovery
* Core imports
* Desktop control
* Windows UI Automation
* Action verification
* Runtime recovery
* Reconnection
* Configuration
* Security-sensitive execution
* Dashboard authentication
* Credential handling
* Self-patch validation
* Code integrity

Real Windows applications are also used during testing to verify that JARVIS can actually interact with a live desktop environment.

---

# 🛠️ For Developers

Normal users should not need to modify the project.

The project is internally organized into components responsible for:

* AI communication
* Desktop interaction
* Windows UI automation
* Actions
* Runtime events
* Diagnostics
* Recovery
* Dashboard
* Configuration
* Safety and validation

Developers can extend JARVIS when needed, while the normal user experience remains focused on simply telling JARVIS what to do.

---

# 📁 Project Structure

A simplified view:

```text
JARVIS-VORNEX/
│
├── main.py
├── ui.py
├── requirements.txt
├── README.md
│
├── core/
│   ├── desktop_agent.py
│   ├── window_agent.py
│   ├── gemini.py
│   ├── live.py
│   ├── screen_eye.py
│   ├── event_bus.py
│   ├── diagnostic_controller.py
│   ├── decision_controller.py
│   ├── controlled_executor.py
│   └── ...
│
├── actions/
│   ├── desktop_agent.py
│   ├── ui_click.py
│   ├── browser_control.py
│   ├── file_controller.py
│   ├── web_search.py
│   ├── send_message.py
│   └── ...
│
├── dashboard/
│
└── config/
    └── api_keys.json
```

---

# 🔒 Privacy & Credentials

Your Gemini API keys should never be committed to Git.

JARVIS stores local API configuration separately from the source code.

The local configuration file:

```text
config/api_keys.json
```

is intentionally excluded from Git.

Never publish your API keys in:

* Git repositories
* Issues
* Pull requests
* Screenshots
* Videos
* README files

---

# 🆘 If Something Goes Wrong

For normal use, the first step is simply to restart JARVIS:

```bash
python main.py
```

If the setup screen appears again, follow the setup instructions.

Normal users should generally not need to manually edit configuration files.

---

# 🌐 Language

This README is written in **English first** for international users.

A complete Persian guide is included below.

---

# 🇮🇷 راهنمای فارسی

## JARVIS چیست؟

**JARVIS دستیار هوش مصنوعی دسکتاپ ساخته‌شده توسط VORNEX است.**

JARVIS برای این طراحی شده که مثل یک دستیار واقعی با کامپیوتر شما کار کند.

یعنی فقط جواب سؤال نمی‌دهد؛ می‌تواند محیط دسکتاپ را بررسی کند، با برنامه‌ها کار کند، کارهای چندمرحله‌ای انجام دهد و نتیجه کارهای مهم را بررسی کند.

ایده اصلی ساده است:

**شما کاری را که می‌خواهید می‌گویید؛ JARVIS مراحل انجام آن را مدیریت می‌کند.**

---

## ✨ JARVIS چه کارهایی می‌تواند انجام دهد؟

JARVIS می‌تواند:

* 👁️ محیط دسکتاپ را بررسی کند
* 🖱️ با برنامه‌ها کار کند
* ⌨️ تایپ و کنترل کیبورد انجام دهد
* 🪟 با برنامه‌های Windows کار کند
* 📂 فایل‌ها و پوشه‌ها را مدیریت کند
* 🌐 در وب جستجو کند
* 💬 از سرویس‌های پیام‌رسان پشتیبانی‌شده استفاده کند
* ▶️ کارهای مربوط به رسانه را انجام دهد
* 🛠️ در کارهای برنامه‌نویسی کمک کند
* 🌦️ اطلاعات آب‌وهوا بگیرد
* ✈️ پروازها را جستجو کند
* 🎮 بعضی کارهای مربوط به بازی و آپدیت را انجام دهد
* 🖥️ وضعیت سیستم را بررسی کند
* 🔄 در بعضی خطاها recovery انجام دهد
* 🧠 از context مفید در کارها استفاده کند
* 🔐 قبل از بعضی عملیات حساس تأیید بگیرد
* ✅ نتیجه بعضی کارها را بررسی کند

---

# 🚀 نصب و شروع کار

## پیش‌نیازها

نیاز دارید:

* Windows 10 یا Windows 11
* Python 3.11 یا جدیدتر
* یک Gemini API Key
* میکروفون و خروجی صدا

---

## ۱. دریافت JARVIS

```bash
git clone https://github.com/VORNEX/JARVIS-VORNEX.git
cd JARVIS-VORNEX
```

---

## ۲. نصب وابستگی‌ها

```bash
pip install -r requirements.txt
```

---

## ۳. اجرای JARVIS

```bash
python main.py
```

در اولین اجرا، صفحه Setup باز می‌شود.

در Setup تنظیمات اولیه را انجام می‌دهید و بعد از آن معمولاً دیگر نیازی به انجام دوباره این مراحل نیست.

---

# 🔑 کلیدهای Gemini

JARVIS برای بخش هوش مصنوعی خود از Gemini استفاده می‌کند.

امکان وارد کردن حداکثر **۳ کلید Gemini** وجود دارد.

اگر کلیدها قبلاً ذخیره شده باشند، JARVIS آنها را خودش پیدا می‌کند و در Setup به صورت مخفی و نقطه‌نقطه نمایش می‌دهد.

بنابراین لازم نیست هر بار کلیدها را دوباره وارد کنید.

در Setup می‌توانید:

* کلید را عوض کنید
* کلید جدید اضافه کنید
* کلید را پاک کنید
* کلیدهای قبلی را نگه دارید

کلیدها روی سیستم شما نگهداری می‌شوند و وارد Git نمی‌شوند.

---

# 🖥️ انتخاب سیستم‌عامل

در Setup سیستم‌عامل خود را انتخاب کنید.

تجربه اصلی فعلی JARVIS برای Windows طراحی شده است.

بعد از انتخاب، این تنظیم ذخیره می‌شود و لازم نیست هر بار دوباره انتخاب شود.

---

# 🎙️ استفاده از JARVIS

برای استفاده از JARVIS لازم نیست بدانید داخل سیستم چه ابزارهایی وجود دارد.

لازم نیست دستورهای فنی بنویسید.

لازم نیست برای هر برنامه اسکریپت بسازید.

فقط کاری را که می‌خواهید بگویید.

مثلاً:

> Notepad رو باز کن و بنویس VORNEX JARVIS is online.

یا:

> Chrome رو باز کن و آب‌وهوای امروز رو پیدا کن.

یا:

> فایلی که دیروز دانلود کردم رو پیدا کن.

یا:

> YouTube رو باز کن.

یا:

> این پیام رو داخل Telegram بنویس.

یا:

> Settings رو باز کن و Bluetooth رو روشن کن.

JARVIS خودش تصمیم می‌گیرد برای انجام کار چه مراحلی لازم است.

---

# 🧠 کنترل عمومی کامپیوتر

یکی از اهداف اصلی JARVIS این است که برای هر برنامه به یک اسکریپت جداگانه نیاز نداشته باشد.

JARVIS می‌تواند:

1. برنامه فعلی را بررسی کند
2. کنترل‌های قابل استفاده را پیدا کند
3. تصمیم بگیرد چه کاری باید انجام شود
4. آن کار را انجام دهد
5. نتیجه را بررسی کند
6. در صورت نیاز مرحله بعدی را انجام دهد
7. اگر موفقیت قابل تأیید نباشد، وانمود نکند که کار انجام شده است

به همین دلیل سیستم کنترل دسکتاپ می‌تواند برای برنامه‌های مختلف استفاده شود.

---

# 🔐 امنیت

JARVIS برای عملیات حساس از مکانیزم‌های امنیتی مختلف استفاده می‌کند.

در بعضی عملیات حساس یا خطرناک، قبل از اجرا از کاربر تأیید گرفته می‌شود.

همچنین بعضی عملیات بعد از اجرا بررسی می‌شوند تا سیستم صرفاً به خاطر ارسال یک دستور، آن را موفق فرض نکند.

---

# 📱 کنترل از راه دور

JARVIS دارای Dashboard برای بعضی قابلیت‌های کنترل از راه دور است.

در صورت فعال بودن Dashboard، اطلاعات لازم برای اتصال در خود برنامه نمایش داده می‌شود.

دسترسی Remote نیز دارای احراز هویت است.

---

# 🔄 بازیابی خودکار

JARVIS دارای سیستم monitoring و recovery است.

در بعضی مشکلات مربوط به:

* اتصال
* Runtime
* منابع سیستم
* ابزارها

سیستم می‌تواند مشکل را تشخیص دهد و در صورت امکان recovery انجام دهد.

هدف این است که برای مشکلات معمول، کاربر مجبور نباشد دائماً برنامه را دستی restart یا تعمیر کند.

---

# 🛠️ آیا برای استفاده از JARVIS نیاز به کار فنی است؟

**خیر.**

برای استفاده معمول فقط کافی است:

1. Python و وابستگی‌ها را نصب کنید.
2. JARVIS را اجرا کنید.
3. در Setup کلید Gemini و سیستم‌عامل را تنظیم کنید.
4. بعد با JARVIS به زبان طبیعی کار کنید.

کارهای فنی بیشتر مربوط به توسعه خود پروژه است، نه استفاده روزمره.

---

# 💡 فلسفه JARVIS

هدف JARVIS این نیست که کاربر مجبور باشد بداند:

* کدام ابزار را باید انتخاب کند
* کدام دستور را باید اجرا کند
* برای کدام برنامه باید اسکریپت بنویسد
* هر کار چند مرحله دارد

هدف این است که کاربر **نتیجه موردنظرش را بگوید**.

مثلاً:

> «Notepad رو باز کن و این متن رو داخلش بنویس.»

یا:

> «Chrome رو باز کن و آخرین اطلاعات این موضوع رو پیدا کن.»

و JARVIS خودش مراحل لازم را مدیریت کند.

---

# ⭐ VORNEX × JARVIS

**VORNEX** سازنده و توسعه‌دهنده JARVIS است.

**JARVIS** دستیار هوش مصنوعی دسکتاپ VORNEX است.

> **JARVIS — See. Understand. Act. Verify.**

### Built by VORNEX.
