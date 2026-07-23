#!/usr/bin/env python3
"""
Daily Catholic Readings — website builder
==========================================

Each morning this:
  1. Fetches the day's Catholic Mass readings from the USCCB site.
  2. Asks Claude for an in-depth reflection tracing the Old Testament
     reading in relation to the Gospel.
  3. Writes it into the website in docs/, which the GitHub workflow
     commits and GitHub Pages publishes.

Requirements:
    pip install anthropic requests beautifulsoup4

Environment variables:
    Required:
        ANTHROPIC_API_KEY    your Anthropic API key
"""

import os
import re
import sys
import json
import datetime

import requests
from bs4 import BeautifulSoup
import anthropic

import site_builder

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
MODEL = "claude-sonnet-4-6"

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

if not ANTHROPIC_API_KEY:
    sys.exit("Missing required environment variable: ANTHROPIC_API_KEY")


# ---------------------------------------------------------------------------
# 1. Fetch today's readings
# ---------------------------------------------------------------------------
def fetch_readings(date: datetime.date) -> str:
    """Pull the day's readings from the USCCB daily-reading page."""
    url = f"https://bible.usccb.org/bible/readings/{date.strftime('%m%d%y')}.cfm"
    headers = {"User-Agent": "Mozilla/5.0 (daily-readings-script)"}

    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    blocks = soup.find_all(class_="innerblock")
    parts = [b.get_text(separator="\n", strip=True) for b in blocks]
    text = "\n\n".join(p for p in parts if p).strip()

    if not text:
        text = soup.get_text(separator="\n", strip=True)
    return text


# ---------------------------------------------------------------------------
# 2. Generate the reflection
# ---------------------------------------------------------------------------
BREAKDOWN_SYSTEM_PROMPT = """You are a knowledgeable, warm Catholic scripture guide writing a daily reflection.

Given the day's Mass readings, produce an in-depth breakdown tracing the Old Testament (First) reading in relation to the Gospel, following the theological threads that connect them.

Respond with ONLY a valid JSON object, no preamble and no markdown code fences, with exactly two keys: "liturgical_day" and "reflection".

"liturgical_day" — a short plain-text label for the day, e.g. "Feast of Saint Mary Magdalene" or "Tuesday of the Sixteenth Week in Ordinary Time". No markdown.

"reflection" — the full reflection as markdown text. It should:

- Open with a compact list of the day's readings by citation — the liturgical day, First Reading, Responsorial Psalm (with its response line), and Gospel — each on its own line, before any commentary.
- If the day carries a memorial, feast, or solemnity, note it and briefly connect the saint or occasion to the readings where there is a genuine link. If there is no natural connection, or the day is an ordinary weekday, skip this entirely rather than forcing it.
- Set the First Reading in its own scriptural and historical context: where it falls in the book, what is happening around it, and what the imagery means.
- Do the same, more briefly, for the Gospel.
- Trace the connections between them — shared images, themes, covenant logic, how one illuminates or fulfills the other. This is the heart of the piece.
- On Sundays and solemnities there is also a Second Reading, usually from an epistle. Include it and note how it relates to the others, while keeping the First Reading-Gospel thread as the primary focus.
- End with a section whose heading is exactly "To carry today", containing a single question or line to sit with. Keep it to one or two sentences.

IMPORTANT - honesty about pairing: On weekdays in Ordinary Time, the First Reading follows its own semicontinuous cycle and is often NOT chosen to match the Gospel. Where the two readings are not thematically paired, say so plainly and treat each on its own terms rather than manufacturing a connection. A candid "these two simply run on separate tracks today" is far better than a strained link.

Also avoid: Greek or Hebrew word studies, and citing specific Catechism paragraph numbers or council documents by number. Refer to such sources by name only if relevant.

Style: warm, accessible prose - substantive but free of academic jargon. Target about 600 words; do not exceed 850. Use short bold headers (**like this**) to organize sections. Do NOT reproduce the full scripture text verbatim; refer to and paraphrase it."""


def generate_reflection(readings_text: str, date: datetime.date) -> dict:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    user_content = (
        f"Today is {date.strftime('%A, %B %d, %Y')}.\n\n"
        f"Here are today's Mass readings (scraped from the USCCB site - identify "
        f"the First Reading, Responsorial Psalm, Second Reading if present, and "
        f"Gospel from this text):\n\n{readings_text}"
    )

    message = client.messages.create(
        model=MODEL,
        max_tokens=2500,
        system=BREAKDOWN_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )

    raw = "".join(b.text for b in message.content if b.type == "text").strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw).strip()

    try:
        data = json.loads(raw)
        if not data.get("reflection"):
            raise ValueError("response had no 'reflection'")
        data.setdefault("liturgical_day", None)
        return data
    except (json.JSONDecodeError, ValueError) as e:
        # Don't lose the day's reflection over a formatting problem.
        print(f"Warning: could not parse JSON ({e}); using raw text.")
        return {"reflection": raw, "liturgical_day": None}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    today = datetime.date.today()

    print(f"Fetching readings for {today}...")
    try:
        readings = fetch_readings(today)
    except Exception as e:
        sys.exit(f"Could not fetch readings: {e}")

    if len(readings) < 100:
        sys.exit("Fetched readings text looks too short - the USCCB page layout "
                 "may have changed. Check the selector in fetch_readings().")

    print("Generating reflection...")
    result = generate_reflection(readings, today)

    print("Building site...")
    page = site_builder.build_site(
        today,
        result["reflection"],
        liturgical_day=result.get("liturgical_day"),
    )
    print(f"Done. Wrote docs/{page}")


if __name__ == "__main__":
    main()
