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

Return ONLY a valid JSON object — no preamble, no code fences — with these keys. Every key is required.

"liturgical_day" — the full name of the day as plain text. "Feast of Saint Mary Magdalene". "Tuesday of the Sixteenth Week in Ordinary Time". "Memorial of Saint Apollinaris, Bishop and Martyr".

"title_lead" — the FIRST part of that name, to be set in italics above the main line. It should be the introductory phrase, not the substance: "Feast of", "Memorial of", "Tuesday of the", "Optional memorial of". Use null if the day's name has no natural lead-in.

"title_main" — the REST of the name, set large below the lead. "Saint Mary Magdalene". "Sixteenth Week in Ordinary Time". "Saint Apollinaris". Together, title_lead and title_main must read as the full name with nothing lost and nothing added.

"color" — the liturgical color, exactly one of: "green", "purple", "red", "white", "rose". Ordinary Time is green. Lent and Advent are purple. Martyrs, Pentecost, and Passion days are red. Feasts of the Lord, of Mary, of non-martyr saints, and the Christmas and Easter seasons are white. Gaudete and Laetare Sundays are rose.

"citations" — array of strings, one per reading, IN ORDER: first reading, psalm, second reading if there is one, Gospel. Format them like "Song of Songs 3:1-4b" and "Psalm 63:2-9". The psalm must always be included and must always be second. This array is required and must never be empty.

"epigraph" — ONE sentence, under 110 characters, naming the heart of the day. It sits alone beneath the title, so it must stand by itself. Concrete, not abstract. "Searching in the dark for a beloved who cannot be found" — not "a reflection on love and loss".

"reflection" — the reflection itself, in markdown. See below.

HOW TO WRITE THE REFLECTION

Give each reading its own treatment, then connect them. Start with the first reading: where it falls in the book, what is happening around it, what the imagery meant to the people who first heard it. Then the Gospel, more briefly. Then where the two meet and how one opens the other.

Mark each section with a bold label naming the reading and its citation — "**The first reading — Micah 7:14-20**", "**The Gospel — Matthew 12:46-50**". The connecting section gets a label naming what connects them, with no citation. A reader should always know which text is under discussion.

Start each section somewhere specific: a detail, a difficulty, an image. Never open by announcing what you are about to do.

Write the way a good homilist talks — plainly, concretely, unhurried. Short sentences next to long ones. Say the difficult thing rather than smoothing it over. Trust the reader.

The tradition's well-worn readings are yours to draw on where they genuinely illuminate the text: the Song of Songs read as the soul and Christ, Mary Magdalene as apostle to the apostles, Jonah as a sign of the resurrection. Use them as the common inheritance they are.

BE HONEST ABOUT PAIRING. On Ordinary Time weekdays the first reading runs on its own cycle and often has nothing to do with the Gospel. When that is so, say it plainly and take each on its own terms. A candid "these two are simply on separate tracks today" beats a manufactured connection.

LENGTH — this matters. 400 to 500 words for the whole reflection. Not more. Each section is two or three tight paragraphs at most. Cut every sentence that restates a previous one. The discipline of the form is that it must be readable in three or four minutes over coffee; a reader who has to scroll twice has been lost. Short is better than complete.

DO NOT
- Do not attribute anything to a named Church Father, theologian, pope, or saint. No "as Augustine says". You cannot verify the quotation and a wrong attribution is worse than none.
- Do not cite Catechism paragraph numbers, council documents, or encyclicals.
- Do not do Greek or Hebrew word studies.
- Do not reproduce long stretches of scripture. Refer and paraphrase.
- Do not use: "the thread tying them together", "at its core", "invites us to", "reminds us that", "in today's readings we see", "serves as a powerful reminder", "speaks to".
- Do not end paragraphs on a tidy summarizing sentence. Let them end where the thought ends.

THE CLOSING
End with a section headed exactly **To carry today** — ONE sentence, under 25 words. Not two. Not one sentence with an em-dash carrying a second thought.

This is the hardest part and the most likely to go wrong. The failure is always the same: saying too much. Write the question, then cut everything that explains it. Trust the reader to make the connection — if you have to gloss your own image, the image was doing its job and the gloss is undoing it.

One clause. One image. No appositives, no "not this, but that" constructions, no restating the metaphor in plainer words. Stop before it resolves.

Make it specific to *this* day's texts. Prefer friction: a question a reader might not want to answer. If the readings resist a neat application, say something honest about that rather than forcing one.

Avoid: rhetorical questions with obvious answers; second-person exhortation ("let us remember", "may we learn"); anything printable on a greeting card; anything that resolves the difficulty the reflection just raised.

The closing must stand on its own. Someone who reads only this sentence — without the reflection, without knowing the day's readings — should understand what is being asked of them. Carry the insight across, not the imagery.

Test it: if the sentence requires knowing what happened in the Gospel to make sense, rewrite it. Scriptural images ("a body", "the name", "the empty tomb") belong in the reflection, not in the closing. The closing translates what the text found into the reader's own life.

GOOD: "Who have I already decided is beyond forgiving?"
GOOD: "What am I refusing to recognize because it isn't arriving the way I expected?"
GOOD: "Name the thing you would rather God did not forgive."
BAD: "Where am I still looking for a body when a name is already being spoken?"
BAD: "What form of him are you holding on to so tightly that you might be missing the one already standing in front of you?"

The first bad one fails because it only makes sense if you just read John 20 — it borrows the Gospel's imagery instead of translating it. The second fails because it says the same thing three times."""


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
        max_tokens=4000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )

    if message.stop_reason == "max_tokens":
        sys.exit("Response hit the token limit and was truncated. "
                 "Raise max_tokens in generate_reflection().")

    raw = "".join(b.text for b in message.content if b.type == "text").strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw).strip()

    # Fail loudly rather than publishing a broken page. A red X in the
    # Actions tab is far better than raw JSON on a page the family reads.
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"Model did not return valid JSON: {e}")
        print("--- first 600 characters of the response ---")
        print(raw[:600])
        sys.exit(1)

    if not data.get("reflection"):
        sys.exit("Response parsed but contained no 'reflection'.")

    if not data.get("citations"):
        print("Warning: no citations returned; the header will omit them.")

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

    words = len(r["reflection"].split())
    print(f"Reflection is {words} words.")

    print("Building site...")
    page = site_builder.build_site(
        today,
        r["reflection"],
        liturgical_day=r.get("liturgical_day"),
        title_lead=r.get("title_lead"),
        title_main=r.get("title_main"),
        epigraph=r.get("epigraph"),
        citations=r.get("citations"),
        color=r.get("color"),
    )
    print(f"Done. Wrote docs/{page}")


if __name__ == "__main__":
    main()
