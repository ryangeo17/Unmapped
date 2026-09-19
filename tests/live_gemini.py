#!/usr/bin/env python3
"""Live end-to-end test: a real Gemini call driving the real planner.

    .venv/bin/python tests/live_gemini.py

Left out of the normal suite because it needs a key, costs money and can fail
for reasons that have nothing to do with this repo. Run it when the agent glue
changes.

The key is read from GEMINI_API_KEY, or from a .env file at the repo root.
Never pass it on the command line — it ends up in your shell history.

What this proves that the offline tests cannot: that the model picks the tool
rather than answering from memory, that a real function call round-trips, that
it asks instead of guessing on an ambiguous name, and that the geometry it
reports back is the planner's and not invented.
"""
import json
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)


def load_key():
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if key:
        return key, "environment"
    path = os.path.join(ROOT, ".env")
    if os.path.exists(path):
        with open(path) as fh:
            for line in fh:
                m = re.match(r"\s*(?:export\s+)?(GEMINI_API_KEY|GOOGLE_API_KEY)\s*=\s*(.+)",
                             line)
                if m:
                    return m.group(2).strip().strip("'\""), ".env"
    return None, None


FAILURES = []


def usable(key, model):
    """Model ids get retired. Say which ones work rather than throwing a 404
    stack at whoever runs this next."""
    from google import genai
    client = genai.Client(api_key=key)
    try:
        client.models.get(model="models/%s" % model)
        return True
    except Exception as exc:
        print("model %r is not usable: %s\n" % (model, str(exc)[:160]))
        try:
            names = [m.name.replace("models/", "") for m in client.models.list()
                     if "generateContent" in (m.supported_actions or [])]
        except Exception:
            names = []
        flash = [n for n in names if "flash" in n and "thinking" not in n]
        print("try one of these, via GEMINI_MODEL=<id> or planner/gemini_agent.py:")
        for name in (flash or names)[:12]:
            print("   ", name)
        return False


def check(name, ok, detail=""):
    print("  %s %s%s" % ("ok  " if ok else "FAIL", name,
                         (" — %s" % detail) if detail else ""))
    if not ok:
        FAILURES.append(name)


def main():
    key, source = load_key()
    if not key:
        print(__doc__)
        print("No key found. Put it in .env at the repo root:\n")
        print("    echo 'GEMINI_API_KEY=your-key-here' >> .env\n")
        print(".env is gitignored. Get a key at https://aistudio.google.com/apikey")
        return 2
    os.environ["GEMINI_API_KEY"] = key
    print("using key from %s" % source)

    from planner import gemini_agent
    from planner.gemini_agent import ask
    print("model: %s\n" % gemini_agent.MODEL)

    if not usable(key, gemini_agent.MODEL):
        return 2

    print("1. a plain request should call the tool, not answer from memory")
    answer, routes = ask("How do I walk from Malone Hall to Clark Hall?")
    check("the tool was called", len(routes) == 1, "%d routes" % len(routes))
    if routes:
        route = routes[0]
        check("planner geometry came back",
              len(route["geometry"]["coordinates"]) > 5,
              "%d points" % len(route["geometry"]["coordinates"]))
        check("destination is Clark Hall",
              route["destination"]["resolved"] == "Clark Hall",
              route["destination"]["resolved"])
        # The model is told to report the tool's numbers, not re-derive them.
        minutes = route["summary"]["minutes"]
        check("the answer quotes the tool's time",
              str(minutes) in answer or str(round(minutes)) in answer,
              "expected %s in: %s" % (minutes, answer[:120]))
        check("the answer mentions the lawn crossing",
              "lawn" in answer.lower() or "decker" in answer.lower(),
              answer[:120])
    print("   answer: %s\n" % answer.strip()[:300])

    print("2. an ambiguous name should be asked about, not guessed")
    answer2, routes2 = ask("How do I get from Malone Hall to the garage?")
    asked = any(w in answer2.lower() for w in ("which", "four", "several", "?"))
    check("the model asked rather than picking one", asked, answer2[:140])
    named = sum(g in answer2 for g in
                ("San Martin", "West Gate", "South Garage", "STSCI"))
    check("it offered the candidates", named >= 2, "%d named" % named)
    print("   answer: %s\n" % answer2.strip()[:300])

    print("3. a mobility question must be declined, not answered from this tool")
    answer3, _ = ask("I use a wheelchair. Is the Malone to Clark route OK for me?")
    hedged = any(w in answer3.lower() for w in
                 ("not", "cannot", "can't", "does not", "doesn't", "only"))
    check("the answer does not claim accessibility", hedged, answer3[:140])
    print("   answer: %s\n" % answer3.strip()[:300])

    print("%s" % ("all checks passed" if not FAILURES
                  else "%d failed: %s" % (len(FAILURES), ", ".join(FAILURES))))
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
