# Unmapped — Design

## What we're building

A campus map for Johns Hopkins (Homewood) that finds the best route for **how you're actually getting around**, not just the shortest one:

- **Walking**: includes off-road paths and shortcuts that regular map apps don't show.
- **Wheelchair**: step-free routes that avoid stairs and curbs without curb cuts, and prefer ramps.
- **Skateboard / bike**: trades off speed against hills and rough surfaces.

A robot drives around campus collecting camera and sensor data. **Gemini** turns that data into an accessibility map, then reasons over it to choose and explain a route for each user. The more the robot maps, the less it needs to verify routes in person.

## How it fits together

```
          ┌──────────────┐   POST observations    ┌──────────────────────────────┐
          │    Robot     │ ─────────────────────► │           Backend            │
          │ camera, GPS, │ ◄───────────────────── │           (FastAPI)          │
          │ IMU          │   GET verification     │                              │
          └──────────────┘   tasks                │  • Campus graph (OSM + ours) │
                                                  │  • Pathfinder (per-mode cost)│
          ┌──────────────┐   REST / JSON          │  • Gemini vision (labeling)  │
          │   Frontend   │ ◄────────────────────► │  • Gemini agent (routing)    │
          │  map + UI    │                        └──────────────┬───────────────┘
          └──────────────┘                                       │
                                                                 ▼
                                                  ┌──────────────────────────────┐
                                                  │  Supabase                    │
                                                  │  Postgres: observations,     │
                                                  │  edge tags, tasks            │
                                                  │  Storage: robot images       │
                                                  └──────────────────────────────┘
```

The **backend is the hub**. The robot and the frontend never talk to each other directly; each one talks only to the backend's API.

## Core idea: a campus graph with tagged edges

- Campus walkways are modeled as a **graph** built from OpenStreetMap, plus shortcut paths we add by hand.
- Each edge (path segment) carries **tags**: stairs, ramp, slope, surface/roughness, curb cut, and so on. Each tag has a **confidence** score.
- Routing runs a normal pathfinder (A*) with a **different cost function per mode**. For example, stairs are impassable for a wheelchair, and slope is penalized heavily for a skateboard.
- The route geometry always comes from the graph. Gemini decides and explains, but never draws the path itself.

## Where Gemini is used

1. **Perception.** The robot uploads camera frames, and Gemini vision labels them (stairs, surface, ramp, obstacles) as structured output. Those labels become tags on the nearest edge.
2. **Routing agent.** The user describes their situation in plain language ("on a skateboard, hate hills"). Gemini turns that into routing preferences, calls the pathfinder as a tool, compares the candidate routes, and explains its choice.
3. **Verification.** For low-confidence segments along a route, Gemini checks the available images. Segments that are still uncertain become tasks for the robot.
4. *(Stretch)* **User hazard reports.** A student uploads a photo, and Gemini classifies it and updates the map.

## The verification loop

```
robot observes ─► Gemini labels ─► edge confidence goes up
       ▲                                     │
       └── low-confidence edges become ◄─────┘
           robot tasks
```

Over time, most edges reach high confidence and the robot is only needed for new or changed areas.

## Technologies

| Part | Tech |
|---|---|
| Backend | Python, FastAPI, OSMnx + NetworkX (graph/routing), `google-genai` (Gemini) |
| Database | Supabase Postgres (PostGIS if we need spatial queries) |
| Image storage | Supabase Storage |
| Frontend | React + TypeScript web app with MapLibre GL (see `claude/frontend_design.md`) |
| Robot | ROS, plus an uploader node that sends observations to the backend over HTTP |
| Elevation | USGS elevation data for baseline slope before the robot has covered an area |
| Hosting | Backend on a single always-on instance (Railway / Render / GCP VM). Use a laptop + Cloudflare Tunnel or ngrok during development. |

## Interfaces (high level)

The exact request/response shapes will live in the backend's API docs (FastAPI `/docs`). We lock these down first so everyone can work in parallel against mock data.

**Frontend ↔ Backend**
- Search places on campus
- Request a route (start, end, mode, optional free-text preferences) and get back the route, alternatives, per-segment tags and Gemini's explanation
- Get the tagged map edges (for overlays like "show stairs")
- Get recent robot observations (live feed panel)

**Robot ↔ Backend**
- Upload an observation: image, GPS, heading, timestamp, optional IMU data
- Fetch verification tasks (places to go look at) and mark them complete

The robot runs ROS, but the backend doesn't depend on it. An **uploader node** on the robot subscribes to the camera, GPS and IMU topics and sends observations to the backend over plain HTTP. This keeps the two stacks decoupled: the robot team owns everything ROS-side, and the backend only sees HTTP requests.

The uploader should buffer observations locally and retry, because campus Wi-Fi is unreliable. The robot should also record runs as rosbags so we can replay them through the backend for the demo.

## Team split

| Who | Owns | First milestone |
|---|---|---|
| **Backend** (1 person) | API, campus graph, routing, Gemini integration, Supabase | Mock API endpoints live at a public URL |
| **Frontend** (Ryan) | Map, search, mode picker, route + explanation display, overlays | Map showing a mock route from the backend |
| **Robot** (2 people) | Driving/data collection, perception capture, uploader, task following | One image + GPS successfully posted to the backend |

**First integration goal:** one photo from the robot shows up as a labelled segment on the frontend map.

## MVP scope

- **Area:** a small demo zone on Homewood campus that includes at least one staircase with a nearby ramp and a noticeable hill, so each mode visibly picks a different route.
- **Must have:** the three travel modes, the Gemini-labelled robot data on the map, Gemini-explained routes, and a working frontend.
- **Nice to have:** a live robot feed, the automated verification-task loop, user hazard reports.
- **Demo safety net:** a pre-recorded robot run we can replay through the backend if the live robot fails.
