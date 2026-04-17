#!/usr/bin/env python3
"""
Seed WrestleMania 42 match card with Polymarket data.

Run after migration: heroku run python scripts/seed_wrestlemania.py -a bainluck
"""

import asyncio
import os
import sys

# Add parent dir to path so we can import app modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from app.models.wrestlemania import (
    WrestlemaniaMatch,
    WrestlemaniaOutcome,
    WrestlemaniaOddsSnapshot,
)
from app.services.database import get_session, init_db
from app.services.wikipedia_images import resolve_wrestler_image


# Night 1: Saturday April 19, 2026 — kickoff ~7 PM ET (23:00 UTC)
# Night 2: Sunday April 20, 2026 — kickoff ~7 PM ET (23:00 UTC)
N1_BASE = datetime(2026, 4, 19, 23, 0, tzinfo=timezone.utc)
N2_BASE = datetime(2026, 4, 20, 23, 0, tzinfo=timezone.utc)

CARD = [
    # ── Night 1 ──────────────────────────────────────────────────────────
    {
        "match_order": 1,
        "night": 1,
        "title": "6-Man Tag Team Match",
        "match_type": "Tag Team",
        "lock_time": N1_BASE,
        "storyline": "Social media meets the squared circle. Logan Paul recruited Austin Theory and YouTube megastar IShowSpeed to form a celebrity super-team, drawing the ire of locker room veterans. The Usos reunited with LA Knight to defend WWE's honor against the influencer invasion.",
        "polymarket_event_id": None,
        "polymarket_condition_id": None,
        "outcomes": [
            {"name": "Logan Paul, Austin Theory & IShowSpeed", "probability": 0.45, "case_text": "Logan Paul has proven he belongs in WWE — his athleticism is undeniable. With Speed's unpredictability and Theory's ring IQ, this team has the star power AND the surprise factor to pull off the upset."},
            {"name": "The Usos & LA Knight", "probability": 0.55, "case_text": "The Usos are the greatest tag team in WWE history, and LA Knight is the most over babyface in the company. Experience and crowd energy win wars. The influencers are out of their depth."},
        ],
    },
    {
        "match_order": 2,
        "night": 1,
        "title": "Unsanctioned Match",
        "match_type": "Unsanctioned Match",
        "lock_time": N1_BASE + timedelta(minutes=35),
        "storyline": "This blood feud has been building for months. Jacob Fatu, the Samoan Werewolf and newest enforcer of The Bloodline, has terrorized Drew McIntyre at every turn. McIntyre demanded an unsanctioned match — no rules, no disqualifications, no mercy. Both men want to end the other's career.",
        "polymarket_event_id": "383604",
        "polymarket_condition_id": "0x25ebccd18a3ce91b006d872deb1b292f06850e88948614fcb012cc08fb1be192",
        "outcomes": [
            {
                "name": "Jacob Fatu",
                "probability": 0.80,
                "polymarket_token_id": "111028755811490773116865028102730591804569725662924467654642095416151800367444",
                "case_text": "Fatu is a wrecking ball — the most destructive force in WWE today. In an unsanctioned match with no rules, his savage fighting style gives him a massive advantage. He's younger, faster, and has The Bloodline in his corner.",
            },
            {
                "name": "Drew McIntyre",
                "probability": 0.20,
                "polymarket_token_id": "107980495622891106855224759915492762825236553258992800118580206759204601516834",
                "case_text": "McIntyre CHOSE this stipulation. He's a WrestleMania veteran who thrives in chaos. The Scottish Warrior has been training for exactly this kind of war, and his rage could be the ultimate weapon.",
            },
        ],
    },
    {
        "match_order": 3,
        "night": 1,
        "title": "Women's World Championship",
        "match_type": "Singles",
        "lock_time": N1_BASE + timedelta(minutes=70),
        "storyline": "Royal Rumble winner Liv Morgan earned her shot at Stephanie Vaquer's Women's World Championship. Vaquer has been a dominant champion, bringing a hard-hitting lucha libre style to Raw. Morgan is looking to add the one title that has eluded her — the Women's World Championship on the grandest stage.",
        "polymarket_event_id": "383588",
        "polymarket_condition_id": "0x4fae19b2c4387da74c0386d9f944f88951bb1b8f8a9af0276c6863d2f4377840",
        "outcomes": [
            {
                "name": "Stephanie Vaquer",
                "probability": 0.245,
                "polymarket_token_id": "102941462113733245274713560981170835427682947223638655142715767240229851989555",
                "case_text": "Vaquer is one of the best technical wrestlers on the planet, man or woman. She's beaten everyone put in front of her and has championship experience from multiple promotions. The Rumble winner doesn't always win at Mania.",
            },
            {
                "name": "Liv Morgan",
                "probability": 0.755,
                "polymarket_token_id": "1207183602239844841606141464064199906008405689592982004996198083291989060387",
                "case_text": "Liv won the Royal Rumble — and in WWE, that's destiny calling. She has the crowd behind her, the momentum, and a WrestleMania moment waiting to happen. This is her coronation.",
            },
        ],
    },
    {
        "match_order": 4,
        "night": 1,
        "title": "Women's Intercontinental Championship",
        "match_type": "Singles",
        "lock_time": N1_BASE + timedelta(minutes=105),
        "storyline": "AJ Lee's shocking return to WWE led to her capturing the inaugural Women's Intercontinental Championship. Now former champion Becky Lynch wants it back. Lynch, 'The Man,' has been on a tear, claiming Lee's championship reign is built on nostalgia, not merit. Lee has fired back that she never lost a step.",
        "polymarket_event_id": "383596",
        "polymarket_condition_id": "0xd006b7e9da3fdc83d2f7d6a1bef72d8390e8019abc658e4c999ffaef982543d8",
        "outcomes": [
            {
                "name": "AJ Lee",
                "probability": 0.29,
                "polymarket_token_id": "44423726440867583632410801220412847719088932460390961127703179056759363858653",
                "case_text": "AJ Lee is a three-time Divas Champion who returned with something to prove. She's motivated, sharp, and this title means everything to her. Defending at WrestleMania would cement her comeback as legendary.",
            },
            {
                "name": "Becky Lynch",
                "probability": 0.71,
                "polymarket_token_id": "30333017548979626026312427893327143572191355964547168485848387003384811178523",
                "case_text": "Becky Lynch is 'The Man' for a reason — she's the most decorated women's champion of her generation. She knows how to win the big one, and WrestleMania is where she shines brightest.",
            },
        ],
    },
    {
        "match_order": 5,
        "night": 1,
        "title": "Women's Tag Team Championship — Fatal Four-Way",
        "match_type": "Fatal Four-Way Tag",
        "lock_time": N1_BASE + timedelta(minutes=140),
        "storyline": "Four teams, one title, total chaos. Champions Nia Jax and Lash Legend have dominated through sheer size and power. Charlotte Flair returned from injury and paired with Alexa Bliss. Fan favorites Bayley and Lyra Valkyria bring technical excellence. And the Bella Twins are back for one more run at tag team gold.",
        "polymarket_event_id": None,
        "polymarket_condition_id": None,
        "outcomes": [
            {"name": "Nia Jax & Lash Legend", "probability": 0.30, "case_text": "Size matters. Jax and Legend are the most physically imposing team in the match. In a Fatal Four-Way, their power advantage becomes even more dangerous — they can absorb punishment from multiple teams."},
            {"name": "Charlotte Flair & Alexa Bliss", "probability": 0.30, "case_text": "Charlotte Flair is a 14-time champion. Bliss is a former tag team champion. Together they combine big-match experience with versatility. Charlotte has never lost at WrestleMania in a title match."},
            {"name": "Bayley & Lyra Valkyria", "probability": 0.20, "case_text": "Bayley is Mr. WrestleMania... wait, Ms. WrestleMania. She's the most consistent performer on the roster, and Valkyria's athletic style complements her perfectly."},
            {"name": "Nikki & Brie Bella", "probability": 0.20, "case_text": "Twin Magic. The Bellas invented women's tag team wrestling and are back to prove the originals are still the best. Never count out the hometown (okay, honorary hometown) heroes."},
        ],
    },
    {
        "match_order": 6,
        "night": 1,
        "title": "Seth Rollins vs. Gunther",
        "match_type": "Singles",
        "lock_time": N1_BASE + timedelta(minutes=175),
        "storyline": "Two of the best in-ring performers in the world collide with nothing but pride on the line — and that makes it even more personal. Gunther, the Ring General, has called Rollins overrated for months. Rollins, the Visionary and architect of WrestleMania moments, isn't about to let the Austrian powerhouse steal his spotlight.",
        "polymarket_event_id": "383595",
        "polymarket_condition_id": "0x163505cd662c3ceeac71ae81d02fda3ce26b0a4e802b19a0a38295648225bfd7",
        "outcomes": [
            {
                "name": "Seth Rollins",
                "probability": 0.22,
                "polymarket_token_id": "91733802748667082144635999764036765220104523501235022531762773737665422108282",
                "case_text": "Rollins lives for WrestleMania. He cashed in at WrestleMania 31, he's main-evented multiple times, and he's the ultimate big-game performer. The Visionary always has a plan.",
            },
            {
                "name": "Gunther",
                "probability": 0.78,
                "polymarket_token_id": "24412895017417899542794387468456928554859271394995217482043027039561156051196",
                "case_text": "Gunther held the Intercontinental Championship for a record-breaking 666 days. His chest chops can KO a horse. The Ring General is on the verge of becoming the most dominant force in WWE, and this is his proving ground.",
            },
        ],
    },
    {
        "match_order": 7,
        "night": 1,
        "title": "Undisputed WWE Championship",
        "match_type": "Singles (Main Event)",
        "lock_time": N1_BASE + timedelta(minutes=210),
        "storyline": "The Night 1 main event. Randy Orton, with Pat McAfee revealed as his secret manipulator, challenges Cody Rhodes for the Undisputed WWE Championship. The twist: if Orton loses, McAfee must leave the wrestling business forever. Rhodes finished his story at WrestleMania 40 — now he must defend it against a 14-time world champion with everything on the line.",
        "polymarket_event_id": "383579",
        "polymarket_condition_id": "0x8285682f630a9d5bf323694a4ba6c08adc1308074ff1474c11185af555741f4c",
        "outcomes": [
            {
                "name": "Cody Rhodes",
                "probability": 0.35,
                "polymarket_token_id": "18321766592032191559408105079961124742393138193315344613470116240355449145350",
                "case_text": "Cody finished the story. He beat Roman Reigns. He IS the Undisputed WWE Champion. And Cody doesn't lose at WrestleMania. The American Nightmare's reign defines this era.",
            },
            {
                "name": "Randy Orton",
                "probability": 0.65,
                "polymarket_token_id": "64384802360973668208210066369018014785737395911828417993930360772832896686192",
                "case_text": "Orton is the most naturally talented wrestler in WWE history. 14 world titles. The RKO can come from anywhere. With McAfee's career also on the line, the Viper has extra motivation — and Orton with motivation is the most dangerous man alive.",
            },
        ],
    },
    # ── Night 2 ──────────────────────────────────────────────────────────
    {
        "match_order": 1,
        "night": 2,
        "title": "Oba Femi vs. Brock Lesnar",
        "match_type": "Singles",
        "lock_time": N2_BASE,
        "storyline": "The passing of the torch — or is it? Brock Lesnar, the Beast Incarnate, returns to face the man WWE is positioning as the next unstoppable monster: Oba Femi. Femi has been undefeated for months, destroying everyone in his path. Lesnar took notice and demanded this match to prove there's only one beast in WWE.",
        "polymarket_event_id": "383637",
        "polymarket_condition_id": "0x049daab323948b91f25143bb973abb594f8ce090c88e06d2ecca24eff8930d6f",
        "outcomes": [
            {
                "name": "Oba Femi",
                "probability": 0.705,
                "polymarket_token_id": "83122136042791581801500558927523004897149369908837784285611712150783645630875",
                "case_text": "Femi is the future. He's bigger, younger, and hungrier than Lesnar. WWE has invested heavily in building him as an unstoppable force — having him lose to a part-timer at WrestleMania would undercut months of booking.",
            },
            {
                "name": "Brock Lesnar",
                "probability": 0.295,
                "polymarket_token_id": "85552196328806771073631700098458380119976376640530896685828223309156687610584",
                "case_text": "It's Brock Lesnar. The man who conquered The Undertaker's streak. The man who squashed John Cena. You don't bet against the Beast at WrestleMania. He may be part-time, but he's full-time dangerous.",
            },
        ],
    },
    {
        "match_order": 2,
        "night": 2,
        "title": "Intercontinental Championship — Ladder Match",
        "match_type": "Ladder Match",
        "lock_time": N2_BASE + timedelta(minutes=35),
        "storyline": "Six men, six ladders, one title hanging above the ring. Penta defends the Intercontinental Championship against five challengers in what promises to be the most acrobatic, high-flying match of the weekend. This is the WrestleMania show-stealer.",
        "polymarket_event_id": None,
        "polymarket_condition_id": None,
        "outcomes": [
            {"name": "Penta", "probability": 0.25, "case_text": "The defending champion has the experience edge — he's been in ladder matches in multiple promotions. His lucha libre athleticism makes him the best climber in the match."},
            {"name": "Je'Von Evans", "probability": 0.10, "case_text": "At just 20 years old, Evans is the young gun with everything to prove. A surprise win would be the feel-good moment of the night and launch a new star."},
            {"name": "Dragon Lee", "probability": 0.10, "case_text": "Dragon Lee brings the lucha libre pedigree and aerial mastery. In a ladder match, his high-flying style could be the X-factor."},
            {"name": "JD McDonagh", "probability": 0.10, "case_text": "McDonagh is the wildcard — technically brilliant and willing to take insane risks. His daredevil style was made for ladder matches."},
            {"name": "Rusev", "probability": 0.10, "case_text": "The Bulgarian Brute brings raw power to a match of high-flyers. While others climb, Rusev destroys. Sometimes the biggest man wins the ladder match by being the last one standing."},
            {"name": "Rey Mysterio", "probability": 0.35, "case_text": "Rey Mysterio is a living legend. The master of the 619 has won everything in wrestling and a WrestleMania IC title win would add to his Hall of Fame legacy. The crowd will be ALL behind him."},
        ],
    },
    {
        "match_order": 3,
        "night": 2,
        "title": "WWE Women's Championship",
        "match_type": "Singles",
        "lock_time": N2_BASE + timedelta(minutes=70),
        "storyline": "Jade Cargill's undefeated aura meets the most dominant woman in modern WWE history. Rhea Ripley, 'Mami,' has been obsessed with capturing the one championship she hasn't held — Cargill's WWE Women's title. This is a clash of titans.",
        "polymarket_event_id": "383613",
        "polymarket_condition_id": "0x7209abfe965ba05e3f2185da5e06ac3d59c00676810bc7e22bb969d6d3fae84d",
        "outcomes": [
            {
                "name": "Jade Cargill",
                "probability": 0.33,
                "polymarket_token_id": "87702388382473965119420852737134193617928085124765132230109866744701410135985",
                "case_text": "Jade is a physical specimen — powerful, fast, and still building her legacy. She's worked hard to become champion and won't give it up easily. Her athleticism could be the difference-maker.",
            },
            {
                "name": "Rhea Ripley",
                "probability": 0.67,
                "polymarket_token_id": "78820944718936064525988355999764454306084583416121586637305278172869376381936",
                "case_text": "Rhea Ripley is the most over women's wrestler on the roster. She's a former Royal Rumble winner, multi-time champion, and the crowd goes nuclear for her. WrestleMania is Mami's playground.",
            },
        ],
    },
    {
        "match_order": 4,
        "night": 2,
        "title": "United States Championship",
        "match_type": "Singles",
        "lock_time": N2_BASE + timedelta(minutes=105),
        "storyline": "Sami Zayn, the ultimate underdog turned champion, defends the United States Championship against NXT's hottest call-up, Trick Williams. Zayn earned the title through years of perseverance; Williams wants to fast-track to the top. Two crowd favorites collide.",
        "polymarket_event_id": "383622",
        "polymarket_condition_id": "0xa446b1db90214d3966af1d028d8938783903df4ce28e93acbf40c773f183c5af",
        "outcomes": [
            {
                "name": "Sami Zayn",
                "probability": 0.31,
                "polymarket_token_id": "24386118775202418500745681113876559238097436813921678416721697932820514382242",
                "case_text": "Sami Zayn is one of the most beloved wrestlers alive. His heart, his passion, his ability to connect with the crowd — it's unmatched. Defending the US title at WrestleMania would be the capstone of a storybook career.",
            },
            {
                "name": "Trick Williams",
                "probability": 0.69,
                "polymarket_token_id": "2409333344473809534885602517130717020693114553449651804579216953771627542479",
                "case_text": "Trick Williams is the future. He dominated NXT and is ready for the main roster spotlight. WWE loves coronating new stars at WrestleMania, and Trick has the charisma to be a franchise player. Whoop that Trick!",
            },
        ],
    },
    {
        "match_order": 5,
        "night": 2,
        "title": "\"The Demon\" Finn Bálor vs. Dominik Mysterio",
        "match_type": "Singles",
        "lock_time": N2_BASE + timedelta(minutes=140),
        "storyline": "The Judgment Day imploded. Finn Bálor, the leader, was betrayed by his protégé Dominik Mysterio, who sided with Rhea Ripley and turned on the man who gave him everything. Bálor has unleashed 'The Demon' persona for the first time in years — a sign that this is deeply personal.",
        "polymarket_event_id": "383621",
        "polymarket_condition_id": "0x4b9631d01282a7301e73ed3bf14d5e79f4d97289d0254b143327865ca5b38702",
        "outcomes": [
            {
                "name": "Finn Bálor",
                "probability": 0.775,
                "polymarket_token_id": "20630797099525097713302888994264506753673261724610388465151146626710445587934",
                "case_text": "When Finn Bálor becomes The Demon, he's nearly unbeatable. He's bringing out his ultimate form for the biggest stage — that's a statement. And The Demon has a WrestleMania win to his name already.",
            },
            {
                "name": "Dominik Mysterio",
                "probability": 0.225,
                "polymarket_token_id": "102244159092550863329287941634242766675472187765175952727990571314807546819492",
                "case_text": "Dirty Dom is the most hated heel in WWE. He thrives on cheating, shortcuts, and outside interference. With Rhea Ripley in his corner, anything can happen. The Demon has been beaten before.",
            },
        ],
    },
    {
        "match_order": 6,
        "night": 2,
        "title": "World Heavyweight Championship",
        "match_type": "Singles (Main Event)",
        "lock_time": N2_BASE + timedelta(minutes=210),
        "storyline": "THE main event of WrestleMania 42. CM Punk, the World Heavyweight Champion, versus Royal Rumble winner Roman Reigns. Reigns held the championship for 1,316 days before losing to Cody Rhodes. Now he wants to climb back to the top — but Punk has gotten under the skin of the entire Samoan family. Will Reigns truly go at it alone, or will The Bloodline interfere?",
        "polymarket_event_id": "383612",
        "polymarket_condition_id": "0x5bb1e5aa709f06a6ec2a5c5640f9ff31b5d0a178e388117a3fe03cbafa130b8c",
        "outcomes": [
            {
                "name": "CM Punk",
                "probability": 0.31,
                "polymarket_token_id": "105081178342558693124676488252017146114735308031710550032660267772363476849384",
                "case_text": "CM Punk is the Best in the World — his words, but also the truth. He came back from a decade away, won the World Heavyweight Championship, and has been the most compelling character in all of wrestling. Retaining at WrestleMania would be the exclamation point on the greatest comeback in history.",
            },
            {
                "name": "Roman Reigns",
                "probability": 0.69,
                "polymarket_token_id": "100282044889652769222268382631236833922274407780764173842306096889420350629625",
                "case_text": "Roman Reigns is the Tribal Chief, the Head of the Table, the most dominant champion of this generation. He held the title for over three years. The Royal Rumble win proves he's back on a mission. When Roman Reigns wants something, he takes it. Acknowledge him.",
            },
        ],
    },
]


async def seed():
    await init_db()
    async with get_session() as session:
        # Check if already seeded
        existing = await session.execute(select(WrestlemaniaMatch).limit(1))
        if existing.scalar_one_or_none():
            print("Already seeded — skipping")
            return

        for match_data in CARD:
            match = WrestlemaniaMatch(
                match_order=match_data["match_order"],
                night=match_data["night"],
                title=match_data["title"],
                match_type=match_data["match_type"],
                participants=[o["name"] for o in match_data["outcomes"]],
                lock_time=match_data["lock_time"],
                storyline=match_data.get("storyline"),
                polymarket_event_id=match_data.get("polymarket_event_id"),
                polymarket_condition_id=match_data.get("polymarket_condition_id"),
            )
            session.add(match)
            await session.flush()

            for out_data in match_data["outcomes"]:
                prob = out_data["probability"]
                decimal_odds = round(1.0 / prob, 3) if prob > 0.01 else 100.0
                outcome = WrestlemaniaOutcome(
                    match_id=match.id,
                    name=out_data["name"],
                    polymarket_token_id=out_data.get("polymarket_token_id"),
                    case_text=out_data.get("case_text"),
                    probability=prob,
                    decimal_odds=decimal_odds,
                )
                session.add(outcome)
                await session.flush()

                session.add(
                    WrestlemaniaOddsSnapshot(
                        outcome_id=outcome.id,
                        probability=prob,
                        source="seed",
                    )
                )

            print(f"  ✓ Night {match_data['night']}, Match {match_data['match_order']}: {match_data['title']}")

        await session.commit()
        print(f"\nSeeded {len(CARD)} matches")

        # Fetch Wikipedia images
        print("\nFetching wrestler images from Wikipedia...")
        outcomes_result = await session.execute(select(WrestlemaniaOutcome))
        outcomes = outcomes_result.scalars().all()
        found = 0
        failed = []
        for outcome in outcomes:
            # Skip team names
            if "&" in outcome.name or "," in outcome.name:
                continue
            url = await resolve_wrestler_image(outcome.name)
            if url:
                outcome.wikipedia_image_url = url
                found += 1
                print(f"  ✓ {outcome.name}")
            else:
                failed.append(outcome.name)
                print(f"  ✗ {outcome.name} — no image found")

        await session.commit()
        print(f"\nImages: {found} found, {len(failed)} failed")
        if failed:
            print("Failed:", ", ".join(failed))


if __name__ == "__main__":
    asyncio.run(seed())
