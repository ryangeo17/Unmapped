"""The three routes offered for a trip.

Walking is the smart one: it may cut across open lawn and finish at any door,
including a car-park lift. The two accessible profiles never take a shortcut —
nothing in this data describes the surface, kerb or slope of a line drawn
across grass — and only use doors the survey marks as step-free.

Grading cannot be a hard filter. Keeping only FullyCompliant segments splits
the network into 165 components, the largest holding 276 of 1746 nodes, so
most building pairs come back with no route at all. That is an artifact of the
filter, not a fact about campus, so `accessible` weights instead of blocks.
"""

GRADE = "ihcd2021routesurveycode"

PROFILES = {
    "walk": {
        "label": "Walking",
        "smartLabel": "Walking (smarter)",
        "description": "Fastest walk. May use steps.",
        "blocks": [],
        "partialWeight": 1.0,
        "stepFreeDoors": False,
    },
    "step_free": {
        "label": "Partially accessible",
        "description": "No steps, and no segments graded as having travel hazards.",
        "blocks": ["stairs", "noncompliant"],
        "partialWeight": 1.5,
        "stepFreeDoors": True,
    },
    "accessible": {
        "label": "Fully accessible",
        "description": ("No steps, no hazards, and prefers fully compliant "
                        "surface even when that means a longer route."),
        "blocks": ["stairs", "noncompliant"],
        "partialWeight": 8.0,
        "stepFreeDoors": True,
    },
}

ORDER = ["walk", "step_free", "accessible"]
DEFAULT = "walk"

# Only walking may leave the paved network. Shortcut edges are inferred from
# geometry, not surveyed, so they have no place in an accessibility answer.
SHORTCUT_PROFILES = {"walk"}


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
