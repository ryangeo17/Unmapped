# Golden fixtures

Regression baselines, not application data. The frontend asks the planner
service for routes between whatever the user typed; these exist so a change in
the planner shows up as a diff in review.

    python3 scripts/route_examples.py

Two trips, three profiles, both switch positions:

| trip | profile | smarter | plain |
|---|---|---|---|
| Malone → Clark | walk | 1.8 min, 122 m, 80 m over Decker Quad | 1.9 min, 149 m, 3 steps |
| | step_free | 2.3 min, 181 m | same |
| | accessible | 2.3 min, 181 m | same |
| Malone → Garage | walk | 8.2 min, 648 m, ends at the lift | 10.4 min, 816 m, 48 steps, building centre |
| | step_free | 8.2 min, 648 m | same |
| | accessible | 8.8 min, 692 m | same |

The switch only reaches walking, so the accessible rows are identical in both
columns — which one of the tests asserts.
