#!/usr/bin/env python3
"""Gemini calling the planner as a tool.

    pip install google-genai
    export GEMINI_API_KEY=...
    python3 -m planner.gemini_agent "quickest way from Malone to the garage?"

The campus data never goes to the model. It gets the tool declarations and, on
demand, the place index: names only, about 120 of them.
"""
import os
import sys

from google import genai
from google.genai import types

from .tools import call, declarations

HERE = os.path.dirname(os.path.abspath(__file__))
# Overridable, because model ids get retired: gemini-2.5-flash started
# returning 404 with "no longer available to new users".
MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")


def system_prompt():
    """SKILL.md is the contract, so the model reads the same document a human
    integrator would rather than a paraphrase of it that can drift."""
    with open(os.path.join(HERE, "SKILL.md")) as fh:
        skill = fh.read()
    return (
        "You help people get around the JHU Homewood campus. Follow the tool "
        "contract below exactly.\n\n" + skill + "\n\n"
        "Answer in two or three sentences: the time and distance, which door "
        "the route arrives at, and anything in `warnings`. The map is drawn "
        "from the tool's geometry, so do not describe turn-by-turn directions "
        "the geometry does not support."
    )


def tools():
    return [types.Tool(function_declarations=declarations())]


def ask(question, model=MODEL, client=None):
    """Returns (answer_text, routes) — routes are the raw planner results, to
    be handed to the frontend untouched.

    `client` is injectable so the loop can be tested without a key or a
    network call; see tests/test_agent.py.
    """
    client = client or genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    config = types.GenerateContentConfig(
        system_instruction=system_prompt(),
        tools=tools(),
    )
    contents = [types.Content(role="user", parts=[types.Part(text=question)])]
    routes = []

    for _ in range(6):                       # bounded: ambiguity may need 2 hops
        response = client.models.generate_content(
            model=model, contents=contents, config=config)
        candidate = response.candidates[0]
        calls = [p.function_call for p in candidate.content.parts if p.function_call]
        if not calls:
            return response.text, routes

        contents.append(candidate.content)
        replies = []
        for fc in calls:
            args = dict(fc.args or {})
            result = call(fc.name, args)
            if fc.name == "plan_route" and result.get("status") == "ok":
                routes.append(result)
            # Geometry is for the frontend, not for the model: sending hundreds
            # of coordinates back wastes context and tempts it to quote them.
            trimmed = {k: v for k, v in result.items() if k != "geometry"}
            replies.append(types.Part.from_function_response(
                name=fc.name, response={"result": trimmed}))
        contents.append(types.Content(role="user", parts=replies))

    return "Could not settle on a route.", routes


def main():
    question = " ".join(sys.argv[1:]) or "How do I walk from Malone Hall to Clark Hall?"
    answer, routes = ask(question)
    print(answer)
    for route in routes:
        print("\n%s -> %s  %.1f min, %.0f m, %d points"
              % (route["origin"]["arrival"], route["destination"]["arrival"],
                 route["summary"]["minutes"], route["summary"]["metres"],
                 len(route["geometry"]["coordinates"])))


if __name__ == "__main__":
    main()
