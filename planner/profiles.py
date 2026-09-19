"""Routing profiles.

Each profile is a hard filter plus a weight on walktime. Grading cannot be a
hard filter: keeping only FullyCompliant segments splits the network into 165
components, the largest holding 276 of 1746 nodes, so most building pairs come
back with no route. That is an artifact of the filter, not a fact about campus.
"""

GRADE = "ihcd2021routesurveycode"

PROFILES = {
    "walk": {
        "label": "Walking",
        "description": "Shortest walk on the official network. Stairs allowed.",
        "blocks": [],
        "shortcuts": False,
        "entrances": "any",
        "partialWeight": 1.0,
    },
    "walk_smart": {
        "label": "Walking (shortcuts)",
        "description": (
            "Walking, allowed to cut across open lawns and to finish at any "
            "entrance including a car park lift. Not wheelchair-safe."
        ),
        "blocks": [],
        "shortcuts": True,
        "entrances": "any",
        "partialWeight": 1.0,
    },
    "step_free": {
        "label": "Partially accessible",
        "description": "No stairs, no segments graded as having travel hazards.",
        "blocks": ["stairs", "noncompliant"],
        "shortcuts": False,
        "entrances": "step_free",
        "partialWeight": 1.5,
    },
    "accessible": {
        "label": "Fully accessible",
        "description": (
            "No stairs, no hazards, and strongly prefers fully compliant "
            "surface even when that means a longer line."
        ),
        "blocks": ["stairs", "noncompliant"],
        "shortcuts": False,
        "entrances": "step_free",
        "partialWeight": 8.0,
    },
}

DEFAULT_PROFILE = "walk_smart"

# Every profile may finish at any qualifying door: more doors can only shorten
# the route, and picking one arbitrary door makes the numbers depend on the
# order the entryway file happens to be in. "step_free" profiles keep only
# doors graded accessible, plus lifts, which are step-free by nature.


def allows(profile, props):
    blocks = profile["blocks"]
    if "stairs" in blocks and props.get("pathway_type") == 2:
        return False
    if "noncompliant" in blocks and props.get(GRADE) == "NonCompliant":
        return False
    return True


def weight(profile, props):
    if props.get(GRADE) == "FullyCompliant" or props.get("shortcut"):
        return 1.0
    return profile["partialWeight"]
