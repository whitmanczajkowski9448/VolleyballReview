NCAA_CHALLENGE_CATEGORIES = [
    "",
    "Ball in / out",
    "Ball contact / touch",
    "Net fault / antenna",
    "Service foot fault",
    "Back-row attack",
    "Libero front-zone set / illegal attack",
    "Center-line fault",
    "Other",
]

TOUCH_CONTEXTS = [
    "",
    "IN/OUT",
    "BRA/BRB/RO",
    "2 or 4 HITS",
]

ORIGINAL_DECISIONS = {
    "Ball in / out": [
        "",
        "Ball in",
        "Ball out",
        "Successful pancake",
        "Unsuccessful pancake",
    ],
    "Ball contact / touch": [
        "",
        "Touch",
        "No touch",
    ],
    "Net fault / antenna": [
        "",
        "Net fault",
        "No net fault",
        "Antenna fault",
        "No antenna fault",
    ],
    "Service foot fault": [
        "",
        "Foot fault",
        "No foot fault",
    ],
    "Back-row attack": [
        "",
        "Back-row attack",
        "Not a back-row attack",
    ],
    "Libero front-zone set / illegal attack": [
        "",
        "Libero in the front zone",
        "Libero not in the front zone",
        "Illegal attack",
        "Legal attack",
    ],
    "Center-line fault": [
        "",
        "Center-line fault",
        "No center-line fault",
    ],
    "Other": [
        "",
        "Fault",
        "No fault",
    ],
    "": [""],
}

CRS_OUTCOMES = [
    "",
    "Original outcome confirmed",
    "Original outcome reversed",
    "Original outcome stands",
    "Mechanical or video failure",
]

PLAY_CATEGORIES = [
    "",
    "Ball in / out",
    "Touch / no touch",
    "Pancake / floor contact",
    "Caught / thrown ball",
    "Double contact / successive contacts",
    "Four hits",
    "Assisted hit",
    "Back-row attack",
    "Libero front-zone set / illegal attack",
    "Illegal attack of serve",
    "Illegal block — back-row / Libero",
    "Blocking the serve",
    "Reaching over / illegal contact over opponent court",
    "Blocking interference / premature block",
    "Net fault",
    "Antenna fault",
    "Center-line fault",
    "Interference at / under net",
    "Service foot fault",
    "Illegal service",
    "Service screen",
    "Position fault / overlap",
    "Rotation fault / wrong server (out of rotation)",
    "Ball outside antenna / crossing space",
    "Ball under net",
    "Illegal play from nonplaying area",
    "Illegal Libero replacement",
    "Illegal substitution / excessive team entry",
    "Lineup / roster / scoring issue",
    "Delay / procedural issue",
    "Misconduct / sanction",
    "Inadvertent whistle / replay",
    "Simultaneous / double fault",
    "Other",
]

PLAY_TYPES = [
    "Challenge",
    "POI",
    "Fault",
]
