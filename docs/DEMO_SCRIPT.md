# UnMapped judge demo

Routes are computed over JHU's own campus survey — 3,635 nodes and 4,903
segments — not a hand-made demo graph, and not selected from a list of
complete paths. Say that early; the line following real pavement is the first
thing a judge notices.

Use **Malone Hall → Clark Hall** for the shortcut and the steps,
**Malone Hall → San Martin Garage** for the lift, and **Gilman Hall → Brody
Learning Commons** for a second shortcut over Keyser Quad.

1. Compute Malone → Clark with **Smarter planner: On**. 122 m. Turn the switch
   **Off** and recompute: 149 m and three steps. The difference is one 80 m
   diagonal across Decker Quad, which the official network routes around
   because people cut across it and surveys do not.
2. Switch to **Wheelchair** on the same trip. The steps are gone; so are the
   lawn shortcuts, because a line inferred from the basemap is not an
   accessibility claim. Point out that the switch reaches walking only.
3. Compute Malone → **San Martin Garage**. The route ends at *San Martin
   Garage Elevator EL2*, with a lift badge. The survey records no entrance for
   that building at all — aiming at the building centre instead walks you
   169 m further round the block, which is what the panel shows when you turn
   the switch off.
4. Open **Campus** in the header. The pathway network appears coloured by
   JHU's 2021 accessibility grade — green fully compliant, amber partial, red
   "may have travel hazards" — with entrances blue where they are step-free
   and grey where they are not. Zoom past 17 around Decker Quad and the paving,
   stairs and ramps decoded from the campus basemap tiles come in.
5. Point at the **Not surveyed** safety tile and the line saying 100% of the
   route has no slope, surface, roughness, lighting or security reading. That
   is deliberate: the columns are null, not defaulted. A default of zero slope
   and full safety would make every unsurveyed segment look ideal, which is
   exactly the person this app exists for being misled. Filling those in is
   what the robot is for.
6. Try **Alumni Memorial Residence 1**. It fails, and says why: the AMR 1
   Replacement closure is in the way. The closures come from the university's
   own construction polygons.
7. Type **the garage** as a destination. Four garages match, so the API
   answers with the candidates instead of guessing.
8. Start Demo GPS. Show progress, current directions, and pause and reset.
9. Choose **Suggest a better route**, click several map points, add a reason,
   and submit. Copy the reference ID.
10. Open `/admin`, sign in with the `ADMIN_PASSWORD`, approve the submission,
    create and start its robot job, simulate a successful result, and publish
    it. Recompute the public route: the shortcut is eligible only after
    publication, and it is the only verified segment on the map, because the
    robot measured it and JHU's survey is not this project's robot.

Note for whoever runs this: every imported segment is `verified: false` by
design. That is not missing work; it is the honest starting state, and it is
what makes step 10 mean something.
