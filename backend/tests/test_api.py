def login(client):
    response = client.post("/api/admin/login", json={"password": "test-admin-password"})
    assert response.status_code == 200
    return response.json()["token"]


def create_shortcut(client):
    response = client.post(
        "/api/submissions",
        data={
            "name": "Library garden cut-through",
            "description": "A short paved connection observed between Gilman and MSE.",
            "from_node": "gilman",
            "to_node": "mse",
            "distance_m": "35",
            "surface": "paved",
            "roughness": "0.05",
            "slope": "0.01",
            "stairs": "false",
            "curb": "false",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_health_landmarks_graph_and_hazard(client):
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["nodes"] >= 8
    assert client.get("/api/landmarks").json()[0]["node_id"]
    overlay = client.get("/api/graph/overlay").json()
    assert len(overlay["nodes"]) >= 8
    assert "e-quad-homewood-closed" in {edge["id"] for edge in overlay["edges"]}
    assert any(edge.get("source") == "jhu_indoors" or str(edge["id"]).startswith("jhu-") for edge in overlay["edges"]) or len(overlay["edges"]) >= 13
    hazard = client.get("/api/hazards/hazard-brick-roughness")
    assert hazard.status_code == 200
    assert hazard.json()["kind"] == "roughness"


def test_walking_uses_stairs_but_wheelchair_avoids_them(client):
    walking = client.post(
        "/api/routes", json={"start": "Gilman Hall", "end": "MSE Library", "mode": "walking"}
    )
    assert walking.status_code == 200, walking.text
    assert "e-quad-mse-stairs" in walking.json()["edge_ids"]
    assert walking.json()["verified_stats"]["stairs_count"] == 1

    wheelchair = client.post(
        "/api/routes", json={"start": "gilman", "end": "mse", "mode": "wheelchair"}
    )
    assert wheelchair.status_code == 200, wheelchair.text
    assert "e-quad-mse-stairs" not in wheelchair.json()["edge_ids"]
    assert wheelchair.json()["verified_stats"]["stairs_count"] == 0
    assert len(wheelchair.json()["geometry"]) >= 2


def test_avoid_edge_recalculates_and_closed_edge_is_never_used(client):
    normal = client.post(
        "/api/routes", json={"start": "gilman", "end": "mse", "mode": "walking"}
    ).json()
    rerouted = client.post(
        "/api/routes/recalculate",
        json={
            "start": "gilman",
            "end": "mse",
            "mode": "walking",
            "previous_edge_ids": normal["edge_ids"],
            "avoid_previous_route": True,
        },
    )
    assert rerouted.status_code == 200, rerouted.text
    assert not set(normal["edge_ids"]) & set(rerouted.json()["edge_ids"])

    museum = client.post(
        "/api/routes", json={"start": "quad", "end": "homewood", "mode": "walking"}
    )
    assert museum.status_code == 200
    assert "e-quad-homewood-closed" not in museum.json()["edge_ids"]


def test_scooter_avoids_rough_gravel_and_night_changes_weighting(client):
    walking = client.post(
        "/api/routes", json={"start": "rec", "end": "malone", "mode": "walking"}
    ).json()
    scooter = client.post(
        "/api/routes", json={"start": "rec", "end": "malone", "mode": "scooter"}
    ).json()
    assert "e-rec-malone" in walking["edge_ids"]
    assert "e-rec-malone" not in scooter["edge_ids"]
    assert "e-mse-malone-ramp" in scooter["edge_ids"]

    day = client.post(
        "/api/routes", json={"start": "gilman", "end": "homewood", "mode": "walking"}
    ).json()
    night = client.post(
        "/api/routes",
        json={"start": "gilman", "end": "homewood", "mode": "walking", "nighttime": True},
    ).json()
    assert night["scores"]["cost"] >= day["scores"]["cost"]
    assert any("night" in item.lower() for item in night["explanation"])


def test_unverified_segments_are_routable_and_disclosed(client):
    route = client.post(
        "/api/routes", json={"start": "gilman", "end": "mse", "mode": "wheelchair"}
    )
    assert route.status_code == 200
    stats = route.json()["verified_stats"]
    assert stats["unverified_segments"] > 0
    assert stats["verified_percent"] < 100
    assert any("unverified" in item.lower() for item in route.json()["explanation"])


def test_jhu_fallback_connects_landmarks_and_relaxes_only_unverified_segments(client):
    walking = client.post(
        "/api/routes", json={"start": "Latrobe Hall", "end": "Maryland Hall", "mode": "walking"}
    )
    assert walking.status_code == 200, walking.text
    assert walking.json()["verified_stats"]["unverified_segments"] > 0

    wheelchair = client.post(
        "/api/routes",
        json={"start": "2731 N Charles St", "end": "MSE Library", "mode": "wheelchair"},
    )
    assert wheelchair.status_code == 200, wheelchair.text
    assert any(
        "may not meet" in item for item in wheelchair.json()["explanation"]
    )


def test_admin_temporary_closure_forces_recomputation(client):
    token = login(client)
    headers = {"Authorization": f"Bearer {token}"}
    normal = client.post(
        "/api/routes", json={"start": "gilman", "end": "mse", "mode": "wheelchair"}
    ).json()
    target = "e-rec-mse" if "e-rec-mse" in normal["edge_ids"] else normal["edge_ids"][0]
    closed = client.patch(
        f"/api/admin/edges/{target}",
        json={"closed": True},
        headers=headers,
    )
    assert closed.status_code == 200
    rerouted = client.post(
        "/api/routes", json={"start": "gilman", "end": "mse", "mode": "wheelchair"}
    ).json()
    assert target not in rerouted["edge_ids"]


def test_admin_auth_rejects_bad_credentials_and_protects_mutations(client):
    assert client.post("/api/admin/login", json={"password": "wrong"}).status_code == 401
    submission = create_shortcut(client)
    client.cookies.clear()
    assert client.post(
        f"/api/admin/submissions/{submission['id']}/approve", json={}
    ).status_code == 401


def test_complete_submission_robot_and_publish_lifecycle(client):
    submission = create_shortcut(client)
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

    graph_before = client.get("/api/graph").json()
    assert f"shortcut-{submission['id']}" not in {edge["id"] for edge in graph_before["edges"]}
    assert client.post(
        f"/api/admin/robot-jobs/{job_id}/transition",
        json={"status": "inspecting"},
        headers=headers,
    ).status_code == 409

    first = client.post(
        f"/api/admin/robot-jobs/{job_id}/transition",
        json={"status": "dispatched"},
        headers=headers,
    )
    assert first.status_code == 200
    second = client.post(
        f"/api/admin/robot-jobs/{job_id}/transition",
        json={"status": "inspecting"},
        headers=headers,
    )
    assert second.status_code == 200
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

    route = client.post(
        "/api/routes", json={"start": "gilman", "end": "mse", "mode": "wheelchair"}
    )
    assert route.status_code == 200
    assert route.json()["edge_ids"] == [f"shortcut-{submission['id']}"]
    assert route.json()["verified_stats"]["distance_m"] == 31

    logout = client.post("/api/admin/logout", headers=headers)
    assert logout.status_code == 200
    assert client.get("/api/admin/submissions", headers=headers).status_code == 401


def test_upload_validation_and_route_request_validation(client):
    invalid_image = client.post(
        "/api/submissions",
        data={
            "name": "A candidate path",
            "description": "Description long enough",
            "from_node": "gilman",
            "to_node": "mse",
            "distance_m": "20",
        },
        files={"image": ("proof.txt", b"not an image", "text/plain")},
    )
    assert invalid_image.status_code == 415
    assert client.post(
        "/api/routes", json={"start": "gilman", "end": "mse", "mode": "car"}
    ).status_code == 422
