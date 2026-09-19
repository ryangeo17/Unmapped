"""Agent loop tests with a stubbed model: no key, no network, no cost.

Covers the glue that sits between a model and the planner — the part that
breaks silently. A real call is tests/live_gemini.py.

Skipped unless google-genai is installed (it lives in .venv here).
"""
import os
import sys
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)

try:
    from google.genai import types
    HAVE_SDK = True
except ImportError:
    HAVE_SDK = False


@unittest.skipUnless(HAVE_SDK, "google-genai not installed")
class TestAgentLoop(unittest.TestCase):
    def setUp(self):
        from planner import gemini_agent
        self.agent = gemini_agent

    def _client(self, scripted):
        """A stand-in whose responses are scripted in advance."""
        agent = self

        class FakeModels:
            def __init__(self):
                self.calls = []

            def generate_content(self, model, contents, config):
                self.calls.append(contents)
                return scripted.pop(0)

        class FakeClient:
            def __init__(self):
                self.models = FakeModels()

        del agent
        return FakeClient()

    @staticmethod
    def _call(name, args):
        part = types.Part(function_call=types.FunctionCall(name=name, args=args))
        return types.GenerateContentResponse(
            candidates=[types.Candidate(
                content=types.Content(role="model", parts=[part]))])

    @staticmethod
    def _text(text):
        return types.GenerateContentResponse(
            candidates=[types.Candidate(
                content=types.Content(role="model",
                                      parts=[types.Part(text=text)]))])

    def test_declarations_are_accepted_by_the_sdk(self):
        tools = self.agent.tools()
        names = {fd.name for fd in tools[0].function_declarations}
        self.assertEqual(names, {"plan_route", "list_places"})

    def test_system_prompt_carries_the_skill_rules(self):
        prompt = self.agent.system_prompt()
        self.assertIn("never report the route as step-free", prompt)
        self.assertIn("never write coordinates yourself", prompt.lower()
                      .replace("never write coordinates yourself",
                               "never write coordinates yourself"))

    def test_a_function_call_reaches_the_planner_and_comes_back(self):
        client = self._client([
            self._call("plan_route", {"origin": "Malone Hall",
                                      "destination": "Clark Hall"}),
            self._text("It is about 122 m across Decker Quad."),
        ])
        answer, routes = self.agent.ask("how do I get to Clark?", client=client)
        self.assertEqual(len(routes), 1)
        self.assertEqual(routes[0]["status"], "ok")
        self.assertEqual(routes[0]["destination"]["resolved"], "Clark Hall")
        self.assertIn("122", answer)

    @staticmethod
    def _responses(contents):
        """The tool results actually handed back, not their repr — repr elides
        nested structures and makes any assertion on it meaningless."""
        out = []
        for content in contents:
            for part in content.parts or []:
                if getattr(part, "function_response", None):
                    out.append(part.function_response.response["result"])
        return out

    def test_geometry_is_withheld_from_the_model(self):
        """Hundreds of coordinates would waste context and tempt the model to
        quote them; the frontend gets them instead."""
        client = self._client([
            self._call("plan_route", {"origin": "Malone Hall",
                                      "destination": "Clark Hall"}),
            self._text("done"),
        ])
        _, routes = self.agent.ask("q", client=client)
        [sent] = self._responses(client.models.calls[-1])
        self.assertNotIn("geometry", sent)
        # but the caller still gets it, for the map
        self.assertIn("geometry", routes[0])

    def test_warnings_do_reach_the_model(self):
        client = self._client([
            self._call("plan_route", {"origin": "Malone Hall",
                                      "destination": "Clark Hall"}),
            self._text("done"),
        ])
        self.agent.ask("q", client=client)
        [sent] = self._responses(client.models.calls[-1])
        self.assertTrue(any("open lawn" in w for w in sent["warnings"]),
                        sent["warnings"])
        self.assertIn("stepsBesideShortcut", sent["summary"])

    def test_ambiguity_is_handed_to_the_model_to_resolve(self):
        client = self._client([
            self._call("plan_route", {"origin": "Malone Hall",
                                      "destination": "the garage"}),
            self._text("Which garage did you mean?"),
        ])
        answer, routes = self.agent.ask("to the garage", client=client)
        self.assertEqual(routes, [], "an ambiguous result is not a route")
        [sent] = self._responses(client.models.calls[-1])
        self.assertEqual(sent["status"], "ambiguous")
        self.assertIn("San Martin Garage", sent["candidates"])
        self.assertIn("Which garage", answer)

    def test_the_loop_is_bounded(self):
        """A model that only ever calls tools must not spin forever."""
        forever = [self._call("list_places", {}) for _ in range(20)]
        client = self._client(forever)
        answer, _ = self.agent.ask("q", client=client)
        self.assertIn("Could not settle", answer)
        self.assertLessEqual(len(client.models.calls), 8)


if __name__ == "__main__":
    unittest.main()
