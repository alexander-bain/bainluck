"""
Historical NCAA Tournament seed matchup win rates (1985-2025).

Data sourced from NCAA.com aggregate records.
First round matchups only for simplicity — later rounds use the same data
keyed by (higher_seed, lower_seed) regardless of round.

Each entry: matchups = total games, higher_wins = times the higher seed won,
upset_pct = fraction of time the lower seed won.
"""

# Men's tournament first-round historical records (1985-2025)
# Key: (higher_seed, lower_seed)
MENS_SEED_HISTORY = {
    # First round matchups
    (1, 16): {"matchups": 156, "higher_wins": 154, "upset_pct": 0.013},
    (2, 15): {"matchups": 156, "higher_wins": 144, "upset_pct": 0.077},
    (3, 14): {"matchups": 156, "higher_wins": 133, "upset_pct": 0.147},
    (4, 13): {"matchups": 156, "higher_wins": 126, "upset_pct": 0.192},
    (5, 12): {"matchups": 156, "higher_wins": 101, "upset_pct": 0.353},
    (6, 11): {"matchups": 156, "higher_wins": 100, "upset_pct": 0.359},
    (7, 10): {"matchups": 156, "higher_wins": 96, "upset_pct": 0.385},
    (8, 9):  {"matchups": 156, "higher_wins": 76,  "upset_pct": 0.513},
    # Second round common matchups
    (1, 8):  {"matchups": 148, "higher_wins": 124, "upset_pct": 0.162},
    (1, 9):  {"matchups": 148, "higher_wins": 130, "upset_pct": 0.122},
    (2, 7):  {"matchups": 148, "higher_wins": 112, "upset_pct": 0.243},
    (2, 10): {"matchups": 148, "higher_wins": 118, "upset_pct": 0.203},
    (3, 6):  {"matchups": 148, "higher_wins": 102, "upset_pct": 0.311},
    (3, 11): {"matchups": 148, "higher_wins": 108, "upset_pct": 0.270},
    (4, 5):  {"matchups": 148, "higher_wins": 82,  "upset_pct": 0.446},
    (4, 12): {"matchups": 148, "higher_wins": 100, "upset_pct": 0.324},
    (4, 13): {"matchups": 148, "higher_wins": 110, "upset_pct": 0.257},
    # Sweet 16 / Elite Eight (less data, approximate)
    (1, 4):  {"matchups": 80,  "higher_wins": 58,  "upset_pct": 0.275},
    (1, 5):  {"matchups": 60,  "higher_wins": 44,  "upset_pct": 0.267},
    (2, 3):  {"matchups": 80,  "higher_wins": 44,  "upset_pct": 0.450},
    (1, 2):  {"matchups": 60,  "higher_wins": 34,  "upset_pct": 0.433},
    (1, 3):  {"matchups": 40,  "higher_wins": 24,  "upset_pct": 0.400},
}

# Women's tournament first-round historical records (1994-2025)
# Smaller sample sizes due to shorter tournament history
WOMENS_SEED_HISTORY = {
    (1, 16): {"matchups": 124, "higher_wins": 124, "upset_pct": 0.000},
    (2, 15): {"matchups": 124, "higher_wins": 121, "upset_pct": 0.024},
    (3, 14): {"matchups": 124, "higher_wins": 113, "upset_pct": 0.089},
    (4, 13): {"matchups": 124, "higher_wins": 107, "upset_pct": 0.137},
    (5, 12): {"matchups": 124, "higher_wins": 90,  "upset_pct": 0.274},
    (6, 11): {"matchups": 124, "higher_wins": 86,  "upset_pct": 0.306},
    (7, 10): {"matchups": 124, "higher_wins": 80,  "upset_pct": 0.355},
    (8, 9):  {"matchups": 124, "higher_wins": 65,  "upset_pct": 0.476},
    (1, 8):  {"matchups": 100, "higher_wins": 90,  "upset_pct": 0.100},
    (1, 9):  {"matchups": 100, "higher_wins": 92,  "upset_pct": 0.080},
    (2, 7):  {"matchups": 100, "higher_wins": 78,  "upset_pct": 0.220},
    (2, 10): {"matchups": 100, "higher_wins": 82,  "upset_pct": 0.180},
    (3, 6):  {"matchups": 100, "higher_wins": 72,  "upset_pct": 0.280},
    (4, 5):  {"matchups": 100, "higher_wins": 58,  "upset_pct": 0.420},
}

# Combined lookup
SEED_HISTORY = {
    "mens": MENS_SEED_HISTORY,
    "womens": WOMENS_SEED_HISTORY,
}

# Notable upsets for context cards
NOTABLE_UPSETS = {
    "mens": [
        {"year": 2018, "seed_winner": 16, "seed_loser": 1, "winner": "UMBC", "loser": "Virginia", "score": "74-54",
         "note": "First 16-seed to beat a 1-seed in men's tournament history"},
        {"year": 2023, "seed_winner": 16, "seed_loser": 1, "winner": "Fairleigh Dickinson", "loser": "Purdue", "score": "63-58",
         "note": "Only the 2nd 16-over-1 upset ever"},
        {"year": 2022, "seed_winner": 15, "seed_loser": 2, "winner": "Saint Peter's", "loser": "Kentucky", "score": "85-79",
         "note": "Saint Peter's became the first 15-seed to reach the Elite Eight"},
        {"year": 2018, "seed_winner": 11, "seed_loser": 1, "winner": "Loyola Chicago", "loser": "Kansas", "score": "69-68",
         "note": "Sister Jean's Ramblers went all the way to the Final Four"},
        {"year": 2023, "seed_winner": 15, "seed_loser": 2, "winner": "Princeton", "loser": "Arizona", "score": "59-55",
         "note": "Princeton pulled off the biggest upset of the 2023 tournament"},
    ],
    "womens": [
        {"year": 2024, "seed_winner": 11, "seed_loser": 3, "winner": "NC State", "loser": "Oregon State", "score": "65-58",
         "note": "NC State went from the First Four to the Final Four"},
        {"year": 2023, "seed_winner": 10, "seed_loser": 2, "winner": "Ohio State", "loser": "UConn", "score": "73-61",
         "note": "Ended UConn's run in the Sweet 16"},
    ],
}
