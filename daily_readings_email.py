#!/usr/bin/env python3
"""
Daily Catholic Readings — OT/NT Breakdown Emailer
==================================================

Fetches the day's Catholic Mass readings, asks Claude to write an in-depth
breakdown tracing the Old Testament reading in relation to the New Testament
(Gospel) reading, and emails it to you via Gmail.

Run it once a day (see the SETUP section at the bottom of this file, or the
chat message that came with it, for how to schedule it).

Requirements:
    pip install anthropic requests beautifulsoup4

Environment variables it reads (set these — see SETUP):
    ANTHROPIC_API_KEY   your Anthropic API key
    GMAIL_ADDRESS       the Gmail address to send FROM and TO
    GMAIL_APP_PASSWORD  a Gmail *App Password* (NOT your normal password)
"""

import os
import sys
import smtplib
import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import requests
from bs4 import BeautifulSoup
import anthropic

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
MODEL = "claude-sonnet-4-6"          # capable + inexpensive for this task
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
GMAIL_ADDRESS = os.environ.get("GMAIL_ADDRESS")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")


def _require_env():
    missing = [
        name for name, val in [
            ("ANTHROPIC_API_KEY", ANTHROPIC_API_KEY),
            ("GMAIL_ADDRESS", GMAIL_ADDRESS),
            ("GMAIL_APP_PASSWORD", GMAIL_APP_PASSWORD),
        ] if not val
    ]
    if missing:
        sys.exit(
            "Missing environment variable(s): " + ", ".join(missing) +
            "\nSee the SETUP notes at the bottom of this script."
        )


# ---------------------------------------------------------------------------
# 1. Fetch today's readings
# ---------------------------------------------------------------------------
def fetch_readings(date: datetime.date) -> str:
    """
    Pull the day's readings from the USCCB daily-reading page.
    Falls back gracefully if the layout can't be parsed — Claude can still
    work from whatever text we extract.
    """
    # USCCB uses MMDDYY in its readings URL, e.g. 072126 for July 21, 2026.
    url = f"https://bible.usccb.org/bible/readings/{date.strftime('%m%d%y')}.cfm"
    headers = {"User-Agent": "Mozilla/5.0 (daily-readings-script)"}

    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")

    # The readings live in blocks with class "innerblock"; grab their text.
    blocks = soup.find_all(class_="innerblock")
    text_parts = []
    for b in blocks:
        chunk = b.get_text(separator="\n", strip=True)
        if chunk:
            text_parts.append(chunk)

    readings_text = "\n\n".join(text_parts).strip()

    # Fallback: if parsing found nothing, use the whole page's visible text.
    if not readings_text:
        readings_text = soup.get_text(separator="\n", strip=True)

    return readings_text


# ---------------------------------------------------------------------------
# 2. Ask Claude for the OT/NT breakdown
# ---------------------------------------------------------------------------
BREAKDOWN_SYSTEM_PROMPT = """You are a knowledgeable, warm Catholic scripture guide writing a daily email reflection.

Given the day's Mass readings, write an IN-DEPTH breakdown that traces the Old Testament (First) reading in relation to the New Testament (Gospel) reading. Follow the theological threads that connect them.

Your breakdown should:
- Set the First Reading in its own scriptural and historical context (where it falls in the book, what's happening, the imagery and its meaning).
- Do the same, more briefly, for the Gospel.
- Then trace the deep connections between them — shared images, themes, covenant logic, how one illuminates or fulfills the other. This is the heart of the piece.
- Close with a single unifying thread stated plainly, and a brief note for prayer or reflection.

Use warm, accessible prose — substantive but not academic jargon. Aim for roughly 500-800 words. Use a few short bold headers to organize it. Do NOT reproduce the full scripture text verbatim; refer to and paraphrase it. Write the whole thing as the body of an email — no preamble like "here is your email," just the reflection itself, starting with the day and liturgical season if identifiable."""


def generate_breakdown(readings_text: str, date: datetime.date) -> str:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    user_content = (
        f"Today is {date.strftime('%A, %B %d, %Y')}.\n\n"
        f"Here are today's Mass readings (as scraped from the USCCB site — "
        f"identify the First Reading, Responsorial Psalm, and Gospel from this text):\n\n"
        f"{readings_text}"
    )

    message = client.messages.create(
        model=MODEL,
        max_tokens=2000,
        system=BREAKDOWN_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )

    # Concatenate any text blocks in the response.
    return "".join(
        block.text for block in message.content if block.type == "text"
    ).strip()


# ---------------------------------------------------------------------------
# 3. Email it via Gmail
# ---------------------------------------------------------------------------
def send_email(subject: str, body: str):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = GMAIL_ADDRESS
    msg["To"] = GMAIL_ADDRESS

    # Plain-text part + a lightly-formatted HTML part.
    msg.attach(MIMEText(body, "plain", "utf-8"))
    html_body = body.replace("\n", "<br>")
    msg.attach(MIMEText(f"<div style='font-family:Georgia,serif;font-size:16px;"
                        f"line-height:1.5;max-width:640px'>{html_body}</div>",
                        "html", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        server.send_message(msg)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    _require_env()
    today = datetime.date.today()

    print(f"Fetching readings for {today}...")
    try:
        readings = fetch_readings(today)
    except Exception as e:
        sys.exit(f"Could not fetch readings: {e}")

    if len(readings) < 100:
        sys.exit("Fetched readings text looks too short — the page layout may "
                 "have changed. Check the USCCB URL in fetch_readings().")

    print("Generating breakdown with Claude...")
    breakdown = generate_breakdown(readings, today)

    subject = f"Daily Readings — {today.strftime('%A, %B %-d')}: OT & Gospel breakdown"
    print("Sending email...")
    send_email(subject, breakdown)
    print("Done. Email sent to", GMAIL_ADDRESS)


if __name__ == "__main__":
    main()


# ===========================================================================
# SETUP (read this once)
# ===========================================================================
#
# 1. Install dependencies:
#        pip install anthropic requests beautifulsoup4
#
# 2. Get an Anthropic API key:
#        console.anthropic.com  ->  Settings  ->  API Keys  ->  Create Key
#        (cost is tiny: roughly a fraction of a cent per day with Sonnet)
#
# 3. Make a Gmail "App Password" (needed because Gmail blocks normal-password
#    logins from scripts):
#        - Turn on 2-Step Verification on your Google account.
#        - Go to  myaccount.google.com/apppasswords
#        - Create a password named e.g. "readings script" and copy the
#          16-character code it gives you.
#
# 4. Set the three environment variables. On Mac/Linux, add these to your
#    ~/.zshrc or ~/.bashrc (or paste before running):
#        export ANTHROPIC_API_KEY="sk-ant-..."
#        export GMAIL_ADDRESS="you@gmail.com"
#        export GMAIL_APP_PASSWORD="the16charcode"
#
#    On Windows (PowerShell):
#        setx ANTHROPIC_API_KEY "sk-ant-..."
#        setx GMAIL_ADDRESS "you@gmail.com"
#        setx GMAIL_APP_PASSWORD "the16charcode"
#
# 5. Test it manually first:
#        python daily_readings_email.py
#    You should get an email within a minute.
#
# 6. Schedule it to run every morning:
#
#    Mac/Linux (cron) — runs at 6:00 AM daily. Run `crontab -e` and add:
#        0 6 * * * cd /path/to/script && /usr/bin/python3 daily_readings_email.py
#    (Make sure the env vars are available to cron — easiest is to set them
#     at the top of the crontab, or hard-code them near the top of this file.)
#
#    Windows (Task Scheduler):
#        - Open Task Scheduler -> Create Basic Task
#        - Trigger: Daily, 6:00 AM
#        - Action: Start a program -> python.exe
#          Add arguments: C:\path\to\daily_readings_email.py
#
# ===========================================================================
