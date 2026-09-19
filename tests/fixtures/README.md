# Golden fixtures

Regression baselines, not application data. The frontend asks the planner
service for routes between whatever the user typed; these exist so a change in
the planner shows up as a diff in review.

    python3 scripts/route_examples.py

Two trips, both switch positions:

| | Smarter | Plain |
|---|---|---|
| Malone → Clark | 1.8 min, 122 m, 80 m across Decker Quad | 1.9 min, 149 m, 3 steps |
| Malone → San Martin Garage | 8.2 min, 648 m, ends at the lift | 10.4 min, 816 m, 48 steps, ends at the building centre |
