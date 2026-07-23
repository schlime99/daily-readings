#!/usr/bin/env python3
"""
Daily Catholic Readings — website builder
==========================================

Each morning this:
  1. Fetches the day's Catholic Mass readings from the USCCB site.
  2. Asks Claude for a reflection tracing the first reading against the Gospel.
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
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup
import anthropic

import site_builder

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
MODEL = "claude-sonnet-4-6"
LOCAL_TZ = ZoneInfo("America/Denver")

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
SYSTEM_PROMPT = """You write a daily reflection on the Catholic Mass readings for a small family website. Someone opens this over coffee. Write for that person.

Return ONLY a valid JSON object — no preamble, no code fences — with these keys:

"liturgical_day" — short plain-text name for the day. A feast or memorial gets the saint's name ("Saint Mary Magdalene"). An ordinary weekday gets the weekday and week ("Tuesday of the Sixteenth Week in Ordinary Time"). No markdown.

"rank" — the liturgical rank if there is one: "Feast", "Memorial", "Optional memorial", "Solemnity", "Sunday". Use null for ordinary weekdays.

"color" — the liturgical color as one of exactly: "green", "purple", "red", "white", "rose". Ordinary Time is green. Lent and Advent are purple. Martyrs, Pentecost, and Passion days are red. Feasts of the Lord, of Mary, of non-martyr saints, Christmas and Easter seasons are white. Gaudete and Laetare Sundays are rose.

"citations" — array of strings, one per reading, in order, each formatted like "Song of Songs 3:1-4b" or "Psalm 63:2-9". Include the psalm. Include the second reading on Sundays and solemnities.

"epigraph" — ONE sentence, under 110 characters, that names the heart of the day. This sits alone under the title in italics, so it must be able to stand by itself. Concrete, not abstract. "Searching in the dark for a beloved who cannot be found" — not "a reflection on love and loss."

"reflection" — the reflection itself, in markdown.

HOW TO WRITE THE REFLECTION

Start somewhere specific. A detail in the text, a difficulty, an image, a question a reader would actually have. Never open by announcing what you are about to do.

Give each reading its own treatment before you connect them. Set the first reading in its context — where it falls in the book, what is happening around it, what the imagery meant to the people who first heard it. Then the Gospel, more briefly. Then trace where the two meet and where one opens the other. That movement — first reading, Gospel, the connection between them — is the shape of the piece, and a reader should be able to find each part. Within that shape, write freely.

Write the way a good homilist talks: plainly, concretely, unhurried. Short sentences next to long ones. Say the difficult thing rather than smoothing it over — when a text is strange or harsh, sit with that instead of rushing to the comfortable reading. Trust the reader.

The tradition's well-worn readings are yours to draw on when they genuinely illuminate the text — the Song of Songs read as the soul and Christ, Mary Magdalene as apostle to the apostles, Jonah as a sign of the resurrection. Use them as the common inheritance they are.

BE HONEST ABOUT PAIRING. On Ordinary Time weekdays the first reading runs on its own cycle and often has nothing to do with the Gospel. When that is the case, say so plainly and take each on its own terms. A candid "these two are simply on separate tracks today" is better than a manufactured connection. This matters more than having a tidy thread.

DO NOT
- Do not attribute anything to a named Church Father, theologian, pope, or saint. No "as Augustine says," no "Aquinas notes." You cannot verify the quotation and a wrong attribution is worse than none. Draw on the tradition's readings without putting words in anyone's mouth.
- Do not cite Catechism paragraph numbers, council documents by number, or encyclicals by name.
- Do not do Greek or Hebrew word studies.
- Do not reproduce long stretches of the scripture text. Refer and paraphrase.
- Do not use these constructions: "the thread tying them together," "at its core," "invites us to," "reminds us that," "in today's readings we see," "serves as a powerful reminder," "speaks to."
- Do not end paragraphs on a tidy summarizing sentence. Let them end where the thought ends.

FORM.
Around 600-800 words. Mark each section with a bold label that names the reading it treats, followed by its citation — "**The first reading — Micah 7:14-20**", "**The Gospel — Matthew 12:46-50**", "**The psalm — Psalm 85**". The section connecting them gets a label naming what connects them, no citation. A reader should always know which text is under discussion without scrolling back up.

End with a section headed exactly **To carry today** — one or two sentences. This is the hardest part of the piece and the most likely to go wrong.

Make it specific to *this* day's texts, not something that could close any reflection. Prefer a question that has some friction in it: one a reader might not want to answer, or that turns the reading back on them in an uncomfortable way. If the day's readings resist a neat application, say something honest about that instead of forcing one.

Avoid: rhetorical questions with obvious answers. Second-person exhortation ("let us remember," "may we learn"). Anything that could be printed on a greeting card. Anything that resolves the difficulty the reflection just raised — if the text is hard, let it stay hard.

"Where am I still looking in the dark for someone already standing beside me?" works because it is concrete and slightly accusing. "May we always trust in God's mercy" does not."""


def generate_reflection(readings_text: str, date: datetime.date) -> dict:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    user_content = (
        f"Today is {date.strftime('%A, %B %d, %Y')}.\n\n"
        f"Here are today's Mass readings, scraped from the USCCB site. Identify "
        f"the first reading, responsorial psalm, second reading if there is one, "
        f"and Gospel:\n\n{readings_text}"
    )

    message = client.messages.create(
        model=MODEL,
        max_tokens=5000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )

    raw = "".join(b.text for b in message.content if b.type == "text").strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw).strip()

    try:
        data = json.loads(raw)
        if not data.get("reflection"):
            raise ValueError("response had no 'reflection'")
    except (json.JSONDecodeError, ValueError) as e:
        # Don't lose the day's reflection over a formatting problem.
        print(f"Warning: could not parse JSON ({e}); using raw text.")
        return {"reflection": raw}

    # Guard against a color value the stylesheet doesn't know.
    if data.get("color") not in site_builder.SEASON_COLORS:
        data["color"] = site_builder.DEFAULT_COLOR

    return data


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    today = datetime.datetime.now(LOCAL_TZ).date()

    print(f"Fetching readings for {today}...")
    try:
        readings = fetch_readings(today)
    except Exception as e:
        sys.exit(f"Could not fetch readings: {e}")

    if len(readings) < 100:
        sys.exit("Fetched readings text looks too short - the USCCB page layout "
                 "may have changed. Check the selector in fetch_readings().")

    print("Generating reflection...")
    r = generate_reflection(readings, today)

    print("Building site...")
    page = site_builder.build_site(
        today,
        r["reflection"],
        liturgical_day=r.get("liturgical_day"),
        rank=r.get("rank"),
        epigraph=r.get("epigraph"),
        citations=r.get("citations"),
        color=r.get("color"),
    )
    print(f"Done. Wrote docs/{page}")


if __name__ == "__main__":
    main()
