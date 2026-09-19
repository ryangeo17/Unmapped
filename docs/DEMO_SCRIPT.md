# UnMapped judge demo

Use **Gilman Hall → MSE Library** for the walking/wheelchair comparison,
**O'Connor Recreation Center → Malone Hall** for scooter roughness, and
**Gilman Hall → Homewood Museum** for the day/night comparison.

1. Compute a walking route and point out the fast stairs/grass segment.
2. Switch to Wheelchair. The API recomputes the graph path and uses ramps and
   curb cuts instead.
3. Compute Recreation Center → Malone as Walking, then switch to Mobility
   Scooter and show that the rough gravel segment is avoided.
4. Compute Gilman → Homewood Museum and toggle Night. The selected path shifts
   to the longer, well-lit route.
5. Compute Gilman → Levering, open the uneven-brick caution marker, inspect its
   robot evidence, then choose **Avoid this obstacle** to recompute while
   excluding that segment.
6. Start Demo GPS. Show progress, current directions, and the approaching-hazard
   notice; pause and reset it.
7. In Admin, activate the temporary Recreation Center–MSE closure and recompute
   to show the edge is impassable.
8. Choose **Suggest a better route**, click several map points, add a reason, and
   submit. Copy the reference ID.
9. Open `/admin`, sign in with the `ADMIN_PASSWORD`, approve the submission,
   create and start its robot job, simulate a successful result, and publish it.
10. Recompute the public route. The shortcut is eligible only after publication.

Call out that surveyed and unsurveyed segments have different line styles and
that every route is recomputed by the FastAPI backend—not selected from a list
of complete routes.
