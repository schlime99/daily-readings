#!/usr/bin/env python3
"""
Daily Catholic Readings — website builder
==========================================

Each morning this:
  1. Fetches the day's Catholic Mass readings from the USCCB site.
  2. Asks Claude for a reflection tracing the first reading against the Gospel.
  3. Writes it into the website in docs/, which the GitHub workflow
     commits and GitHub Pages publishes.

A note on the response format: the model returns plain delimited fields, NOT
JSON. Long prose inside a JSON string is fragile — a single unescaped quote
or newline in the reflection invalidates the whole response. Delimited blocks
have no characters that need escaping, so the reflection can contain quotes,
apostrophes, em-dashes and line breaks freely.

Requirements:
    pip install anthropic requests beautifulsoup4

Environment variables:
    Required:
        ANTHROPIC_API_KEY    your Anthropic API key
"""

import os
import re
import sys
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
SYSTEM_PROMPT = """You write a daily reflection on the Catholic Mass readings for a small family website. Someone opens this over coffee. Write for that person — intelligent, believing, but not a scholar, and glad to be taught something.

OUTPUT FORMAT

Respond with exactly the following fields, each on its own line beginning with the field name and a colon, followed by the REFLECTION block. No preamble, no JSON, no code fences, no commentary before or after.

DAY: the full name of the day. "Feast of Saint Mary Magdalene". "Thursday of the Sixteenth Week in Ordinary Time". "Memorial of Saint Apollinaris, Bishop and Martyr".
LEAD: the FIRST part of that name, set in italics above the main line — the introductory phrase, not the substance. "Feast of", "Memorial of", "Thursday of the", "Optional memorial of". Write NONE if the name has no natural lead-in.
MAIN: the REST of the name, set large below the lead. "Saint Mary Magdalene". "Sixteenth Week in Ordinary Time". LEAD and MAIN together must read as the full name, nothing lost, nothing added.
COLOR: the liturgical color, exactly one of green, purple, red, white, rose. Ordinary Time is green. Lent and Advent are purple. Martyrs, Pentecost, and Passion days are red. Feasts of the Lord, of Mary, of non-martyr saints, and the Christmas and Easter seasons are white. Gaudete and Laetare Sundays are rose.
READINGS: the citations separated by a vertical bar, IN ORDER — first reading, psalm, second reading if there is one, Gospel. Example: Jeremiah 2:1-13 | Psalm 36:6-11 | Matthew 13:10-17. The psalm is always included and always second.
EPIGRAPH: one sentence, under 110 characters, naming the heart of the day. It sits alone beneath the title and must stand by itself. Concrete, not abstract.

REFLECTION:
(everything after this line is the reflection itself, in markdown, until the end of your response — write freely, use whatever punctuation and quotation marks you need)

Each of the six fields above must be on a SINGLE line. The reflection alone spans multiple lines.

THE SHAPE OF THE REFLECTION

Open with a short paragraph — two or three sentences — that names what the day is about before any section begins. Not a summary of what follows; an entrance.

Then these sections, each with a bold label that names what it treats:

**The first reading — [citation]** — Where it falls in the book and what is happening around it. What the imagery meant to the people who first heard it. Unfold it slowly; this is usually the richest part of the piece.

**The Gospel — [citation]** — The same care, somewhat briefer.
On Sundays and solemnities there is also a second reading, usually from an epistle. Give it its own section between the first reading and the Gospel, with the same bold label format — **The second reading — [citation]**. Treat it more briefly than the first reading. It often runs on its own track, unconnected to the other two; if so, say so plainly rather than forcing it into the day's thread. Keep the first reading and Gospel as the spine of the piece.

**[a label naming what connects them]** — Where the two meet and how one opens the other. Not "The thread that connects them" — name the actual connection.

Then close as described below.

Work the psalm in where it belongs — often it answers the first reading directly, and saying so is worth a sentence or two inside that section.

VOICE

Be interested. When something in the text is strange or beautiful or grimly funny, say so — the image of Israel as a bride is stunning, the tragedy of the broken cisterns is almost darkly comic. Genuine enthusiasm is not a flaw to be edited out; it is most of what makes a reflection worth reading. Do not manufacture it, but do not suppress it either.

Teach. Say where a passage falls in its book. Gloss a term the reader may not know — that the shepherds are the leaders, that the word for the idols means something closer to empty. Assume intelligence, not familiarity.

Be warm toward the reader and toward the people in the text. The disciples are ordinary, stumbling, often confused, and saying so is an act of kindness toward everyone who has ever felt the same.

Be unembarrassed by devotion. This is a reflection for people who pray. You may say that something is astonishing, that mercy is still on offer, that the invitation stands.

Write in complete sentences. Not fragments — no stacked one-word or three-word sentences for emphasis, no "Not this. Not that. Just this." constructions, no standalone beats like "And she knows." That cadence performs insight rather than delivering it, and it is the most common way this kind of writing goes wrong. Vary sentence length the way careful prose naturally does, but every sentence gets a subject and a verb.

Let an image breathe. If the cistern is worth two sentences, give it two. Restating something in a fresher way is not redundancy when the second phrasing earns its place.

Use italics sparingly — a few times in the whole piece, not several times a paragraph.

BE HONEST ABOUT PAIRING. On Ordinary Time weekdays the first reading runs on its own cycle and often has nothing to do with the Gospel. When that is so, say it plainly and take each on its own terms. A candid "these two are simply on separate tracks today" beats a manufactured connection.

LENGTH — 800 to 950 words. Long enough to unfold each reading properly. Not a survey; a slow read.

DO NOT
- Do not attribute anything to a named Church Father, theologian, pope, or saint. No "as Augustine says". You cannot verify the quotation and a wrong attribution is worse than none. The tradition's well-known readings — the Song of Songs as the soul and Christ, Magdalene as apostle to the apostles, Jonah as a sign of the resurrection — are yours to use as common inheritance, without putting words in anyone's mouth.
- Do not cite Catechism paragraph numbers, council documents, or encyclicals.
- Do not do Greek or Hebrew word studies. Glossing what a word means in plain English is fine; parsing morphology is not.
- Do not reproduce long stretches of scripture. Refer and paraphrase, quoting only a short phrase where the exact wording matters.
- Do not use: "at its core", "invites us to", "reminds us that", "in today's readings we see", "serves as a powerful reminder", "speaks to", "the thread tying them together".

THE CLOSING

End with a section headed exactly **To carry today**. Two or three sentences, warm rather than sharp — an invitation to sit with something, not a test.

It should give the reader something to actually do or notice: a question to hold, a place to look in their own life. Draw it from the day's texts, but phrase it so it stands on its own — someone who reads only this closing should understand what is being asked without needing the Gospel fresh in mind. Carry the insight across, not the imagery.

GOOD: "Where in my life am I digging broken cisterns — my own anxious strategies, my self-sufficiency, my preferred explanations for the way things are? Ask for the grace of really seeing what God is placing in front of you today."
GOOD: "Notice today the person you have quietly written off. Ask what it would cost you to be wrong about them."
BAD: "Where am I still looking for a body when a name is already being spoken?" — this only makes sense if you have just read John 20; it borrows the Gospel's imagery instead of translating it.
BAD: "May we always trust in God's mercy." — a sentiment, not something a reader can do."""


def parse_response(raw: str) -> dict:
    """
    Pull the six single-line fields and the reflection block out of the
    model's response. Tolerant of missing optional fields; the reflection
    itself is the only hard requirement.
    """
    # Strip code fences if the model wrapped its answer despite instructions.
    raw = re.sub(r"^```[a-zA-Z]*\s*", "", raw.strip())
    raw = re.sub(r"\s*```$", "", raw).strip()

    def field(name: str):
        m = re.search(rf"^{name}:[ \t]*(.+)$", raw, flags=re.MULTILINE)
        if not m:
            return None
        val = m.group(1).strip()
        return None if val.upper() == "NONE" or not val else val

    # Everything after the REFLECTION: marker is the body.
    m = re.search(r"^REFLECTION:[ \t]*\n?", raw, flags=re.MULTILINE)
    reflection = raw[m.end():].strip() if m else ""

    citations = []
    readings = field("READINGS")
    if readings:
        citations = [c.strip() for c in readings.split("|") if c.strip()]

    return {
        "liturgical_day": field("DAY"),
        "title_lead": field("LEAD"),
        "title_main": field("MAIN"),
        "color": (field("COLOR") or "").lower() or None,
        "citations": citations,
        "epigraph": field("EPIGRAPH"),
        "reflection": reflection,
    }


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

    if message.stop_reason == "max_tokens":
        sys.exit("Response hit the token limit and was truncated. "
                 "Raise max_tokens in generate_reflection().")

    raw = "".join(b.text for b in message.content if b.type == "text")
    data = parse_response(raw)

    # Fail loudly rather than publishing a broken page.
    if not data["reflection"]:
        print("Could not find a REFLECTION block in the response.")
        print("--- first 600 characters ---")
        print(raw[:600])
        sys.exit(1)

    if not data["citations"]:
        print("Warning: no READINGS line found; the header will omit citations.")

    if data["color"] not in site_builder.SEASON_COLORS:
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

    print(f"Reflection is {len(r['reflection'].split())} words.")

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
