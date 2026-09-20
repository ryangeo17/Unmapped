"""API tests against the real Homewood graph.

These were written against a synthetic eight-node demo graph and pinned its
edge ids. The graph is now JHU's own survey — 3,635 nodes and 4,903 edges —
so the ids are gone, but every test's *intent* is preserved and the fixtures
it needs are discovered from the graph rather than hard-coded.
"""


def login(client):
    response = client.post("/api/admin/login", json={"password": "test-admin-password"})
    assert response.status_code == 200
    return response.json()["token"]


def route(client, start, end, **kwargs):
    payload = {"start": start, "end": end, "mode": "walking"}
    payload.update(kwargs)
    response = client.post("/api/routes", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def create_shortcut(client, from_node=None, to_node=None, **overrides):
    """A submitted cut-through between two real nodes.

    Defaults to the two ends of a known route so the published edge has
    somewhere useful to shorten.
    """
    if from_node is None:
        walk = route(client, "Malone Hall", "Clark Hall")
        from_node, to_node = walk["node_ids"][0], walk["node_ids"][-1]
    data = {
        "name": "Courtyard cut-through",
        "description": "A short paved connection observed between the two doors.",
        "from_node": from_node,
        "to_node": to_node,
        "distance_m": "35",
        "surface": "paved",
        "roughness": "0.05",
        "slope": "0.01",
        "stairs": "false",
        "curb": "false",
    }
    data.update(overrides)
    response = client.post("/api/submissions", data=data)
    assert response.status_code == 201, response.text
    return response.json()


def test_health_landmarks_and_graph(client):
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["nodes"] == 3635

    landmarks = client.get("/api/landmarks").json()
    assert len(landmarks) == 116
    assert all(item["node_id"] and item["latitude"] and item["longitude"] for item in landmarks)
    # Their original seven names must keep resolving: saved links use them and
    # the demo script says them out loud.
    names = {item["name"] for item in landmarks}
    for legacy in ("Gilman Hall", "MSE Library", "Malone Hall", "Homewood Museum"):
        assert legacy in names, legacy

    overlay = client.get("/api/graph/overlay").json()
    assert len(overlay["nodes"]) == 3635
    # Construction closures stay visible on the map even though nothing routes
    # over them.
    assert any(edge["closed"] for edge in overlay["edges"])


def test_unmeasured_attributes_are_null_not_optimistic(client):
    """The point of the whole import: nobody has surveyed slope, surface,
    roughness, lighting or security here, and a default would read as good."""
    overlay = client.get("/api/graph/overlay").json()
    surveyed = [e for e in overlay["edges"] if e["kind"] != "shortcut"]
    assert surveyed
    assert all(e["slope"] is None for e in surveyed)
    assert all(e["safety"] is None for e in surveyed)
    assert all(e["lit"] is None for e in surveyed)
    assert all(e["surface"] is None for e in surveyed)
    # And it is disclosed rather than buried.
    walk = route(client, "Malone Hall", "Clark Hall")
    assert walk["verified_stats"]["unknown_attribute_m"] > 0
    assert any("no slope" in line for line in walk["explanation"])


def test_walking_uses_steps_but_wheelchair_avoids_them(client):
    walking = route(client, "Malone Hall", "Clark Hall", smarter=False)
    assert walking["verified_stats"]["stairs_count"] >= 1
    assert walking["verified_stats"]["riser_count"] >= 1

    wheelchair = route(client, "Malone Hall", "Clark Hall", mode="wheelchair")
    assert wheelchair["verified_stats"]["stairs_count"] == 0
    assert wheelchair["verified_stats"]["riser_count"] == 0
    assert wheelchair["verified_stats"]["distance_m"] > walking["verified_stats"]["distance_m"]
    # [longitude, latitude], GeoJSON order.
    first = wheelchair["geometry"][0]
    assert -77 < first[0] < -76 and 39 < first[1] < 40


def test_the_smarter_switch_only_reaches_walking(client):
    on = route(client, "Malone Hall", "Clark Hall", smarter=True)
    off = route(client, "Malone Hall", "Clark Hall", smarter=False)
    assert on["verified_stats"]["shortcut_m"] > 0
    assert "Decker Quad" in on["verified_stats"]["shortcut_spaces"]
    assert off["verified_stats"]["shortcut_m"] == 0
    assert on["verified_stats"]["distance_m"] < off["verified_stats"]["distance_m"]
    assert any("open lawn" in line for line in on["explanation"])

    # A lawn diagonal is inferred from the basemap, not surveyed, so it must
    # never appear in an accessibility answer however the switch is set.
    for mode in ("wheelchair", "scooter"):
        chair_on = route(client, "Malone Hall", "Clark Hall", mode=mode, smarter=True)
        chair_off = route(client, "Malone Hall", "Clark Hall", mode=mode, smarter=False)
        assert chair_on["verified_stats"]["shortcut_m"] == 0, mode
        assert chair_on["geometry"] == chair_off["geometry"], mode


def test_a_place_is_reached_by_its_nearest_door(client):
    """San Martin Garage has no entrance in the survey, only a lift. Aiming at
    the building centre instead walks you the long way round the block."""
    walk = route(client, "Malone Hall", "San Martin Garage")
    assert walk["end_door"]["kind"] == "lift"
    assert "Elevator" in walk["end_door"]["label"]

    clark = route(client, "Malone Hall", "Clark Hall")
    assert clark["end_door"]["kind"] == "entrance"
    assert clark["end_door"]["label"].startswith("Clark Hall")


def test_an_ambiguous_name_offers_candidates_instead_of_guessing(client):
    response = client.post(
        "/api/routes", json={"start": "Malone Hall", "end": "the garage", "mode": "walking"}
    )
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert "San Martin Garage" in detail["candidates"]
    assert len(detail["candidates"]) > 1

    assert client.post(
        "/api/routes", json={"start": "Malone Hall", "end": "xyzzy", "mode": "walking"}
    ).status_code == 404


def test_avoid_edge_recalculates_and_closed_edges_are_never_used(client):
    normal = route(client, "Malone Hall", "Clark Hall")
    rerouted = client.post(
        "/api/routes/recalculate",
        json={
            "start": "Malone Hall",
            "end": "Clark Hall",
            "mode": "walking",
            "previous_edge_ids": normal["edge_ids"],
            "avoid_previous_route": True,
        },
    )
    assert rerouted.status_code == 200, rerouted.text
    assert not set(normal["edge_ids"]) & set(rerouted.json()["edge_ids"])

    overlay = client.get("/api/graph/overlay").json()
    closed = {edge["id"] for edge in overlay["edges"] if edge["closed"]}
    assert closed, "the construction polygons should close some segments"
    assert not closed & set(normal["edge_ids"])


def test_unverified_segments_are_routable_and_disclosed(client):
    """JHU's survey is not this project's robot, so every imported segment is
    unverified. Unverified must stay routable, and must be said out loud."""
    walk = route(client, "Malone Hall", "Clark Hall", mode="wheelchair")
    stats = walk["verified_stats"]
    assert stats["unverified_segments"] > 0
    assert stats["verified_segments"] == 0
    assert stats["verified_percent"] == 0
    assert any("Unverified" in line for line in walk["explanation"])


def test_the_official_grade_shapes_the_wheelchair_route(client):
    """Grade cannot be a gate — keeping only fully compliant segments leaves
    16% of the network reachable — so it is weighted, and the wheelchair route
    should come out at least as compliant as the walking one."""
    walking = route(client, "Malone Hall", "San Martin Garage", smarter=False)
    chair = route(client, "Malone Hall", "San Martin Garage", mode="wheelchair")
    assert chair["verified_stats"]["fully_compliant_percent"] is not None
    assert (chair["verified_stats"]["fully_compliant_percent"]
            >= walking["verified_stats"]["fully_compliant_percent"])


def test_admin_temporary_closure_forces_recomputation(client):
    token = login(client)
    headers = {"Authorization": f"Bearer {token}"}
    normal = route(client, "Malone Hall", "Clark Hall")
    victim = normal["edge_ids"][len(normal["edge_ids"]) // 2]

    closed = client.patch(f"/api/admin/edges/{victim}", json={"closed": True}, headers=headers)
    assert closed.status_code == 200
    rerouted = route(client, "Malone Hall", "Clark Hall")
    assert victim not in rerouted["edge_ids"]


def test_admin_auth_rejects_bad_credentials_and_protects_mutations(client):
    assert client.post("/api/admin/login", json={"password": "wrong"}).status_code == 401
    submission = create_shortcut(client)
    client.cookies.clear()
    assert client.post(
        f"/api/admin/submissions/{submission['id']}/approve", json={}
    ).status_code == 401


def test_complete_submission_robot_and_publish_lifecycle(client):
    before = route(client, "Malone Hall", "Clark Hall")
    submission = create_shortcut(
        client, before["node_ids"][0], before["node_ids"][-1], distance_m="31"
    )
    status = client.get(f"/api/submissions/status/{submission['tracking_code']}")
    assert status.status_code == 200
    assert status.json()["status"] == "pending"

    token = login(client)
    headers = {"Authorization": f"Bearer {token}"}
    assert client.post(
        f"/api/admin/submissions/{submission['id']}/publish", headers=headers
    ).status_code == 409

    approval = client.post(
        f"/api/admin/submissions/{submission['id']}/approve",
        json={"note": "Looks plausible"},
        headers=headers,
    )
    assert approval.status_code == 200, approval.text
    job_id = approval.json()["robot_job_id"]

    edge_id = f"shortcut-{submission['id']}"
    graph_before = client.get("/api/graph").json()
    assert edge_id not in {edge["id"] for edge in graph_before["edges"]}
    assert client.post(
        f"/api/admin/robot-jobs/{job_id}/transition",
        json={"status": "inspecting"},
        headers=headers,
    ).status_code == 409

    for step in ("dispatched", "inspecting"):
        assert client.post(
            f"/api/admin/robot-jobs/{job_id}/transition",
            json={"status": step},
            headers=headers,
        ).status_code == 200
    result = client.post(
        f"/api/admin/robot-jobs/{job_id}/simulate-result",
        json={"success": True, "distance_m": 31, "surface": "paved", "roughness": 0.02},
        headers=headers,
    )
    assert result.status_code == 200
    assert result.json()["submission"]["status"] == "verified"

    published = client.post(
        f"/api/admin/submissions/{submission['id']}/publish", headers=headers
    )
    assert published.status_code == 200, published.text
    assert published.json()["routing_active"] is True

    after = route(client, "Malone Hall", "Clark Hall")
    assert after["edge_ids"] == [edge_id]
    assert after["verified_stats"]["distance_m"] == 31
    # The robot measured this one, so it is the only verified metre on it.
    assert after["verified_stats"]["verified_percent"] == 100

    logout = client.post("/api/admin/logout", headers=headers)
    assert logout.status_code == 200
    assert client.get("/api/admin/submissions", headers=headers).status_code == 401


def test_upload_validation_and_route_request_validation(client):
    walk = route(client, "Malone Hall", "Clark Hall")
    invalid_image = client.post(
        "/api/submissions",
        data={
            "name": "A candidate path",
            "description": "Description long enough",
            "from_node": walk["node_ids"][0],
            "to_node": walk["node_ids"][-1],
            "distance_m": "20",
        },
        files={"image": ("proof.txt", b"not an image", "text/plain")},
    )
    assert invalid_image.status_code == 415
    assert client.post(
        "/api/routes", json={"start": "Malone Hall", "end": "Clark Hall", "mode": "car"}
    ).status_code == 422
