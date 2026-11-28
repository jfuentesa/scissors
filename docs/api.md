# Public API 1.0

Use `with Scissors(workspace) as app` for lock release. Namespaces scenes/meshes/materials/
textures/uv accept keyword arguments and return Result (`.id`, `["id"]`, `.as_dict()`).
Export helpers: app.export.glb/gltf/obj/stl/ply/dae/usdz/fbx. Helpers forward options to the registry.
app.call(name, **args) returns a dictionary,
raising ScissorsError; registry.execute(name,args) returns structured success/error envelopes.

```json
{"success":true,"operation":"mesh.create_cube","result":{"id":"obj_...","object_id":"obj_...","vertex_count":8,"face_count":12},"warnings":[]}
```

```json
{"success":false,"operation":"scene.preview","error":{"code":"INVALID_PARAMETER","message":"Invalid parameter background[0]: expected <= 1, received 16. 16 is greater than the maximum of 1","details":{"reason":"16 is greater than the maximum of 1","parameter":["background",0],"expected":"<= 1","received":16}}}
```

Validation errors name the failing field, the expected constraint and the received value.
The message carries all three, and `details.parameter`, `details.expected` and
`details.received` repeat them for code that needs structure. The path uses dotted keys
and integer indexes, for example `background[0]` or `rows.3.figure`. `details.reason`
repeats the violated constraint and also appears in the message, so
`str(ScissorsError)` is enough to read what failed.

registry.list_operations(category=None) gives compact metadata. describe_operation(name)
includes schemas/examples. register(Operation)/unregister(name) update the catalog with
collision checks. Default output schema is object; extensions can declare more specific
schemas. Local registered callables are trusted code; the registry is not a sandbox.

| Category | Operations |
| --- | --- |
| modeler | info |
| scene | create, list, get, inspect, delete, clear, save, load, export, preview, compare_reference |
| mesh | create, create_cube/sphere/cylinder/plane/cone/torus, delete, duplicate, translate, rotate, scale, mirror, array, distribute, data, inspect, stats, bounding_box, centroid, recalculate_normals, merge, subdivide, validate |
| material | create, list, get, update, assign |
| texture | create (checker alias), generate_checker, load, assign, project |
| uv | generate, inspect, unwrap |
| deform | local |
| sculpt | brush |
| operations | batch |
| plugins | list, describe, validate, enable, disable, reload |
| geometry backends | mesh.boolean (manifold3d), uv.generate method xatlas and uv.unwrap (xatlas), mesh.simplify/organic_union/remesh/repair_topology/repair_topology_data (VTK) |

`mesh.simplify` reduces faces by percentage and preserves UV by default.
It uses the VTK backend included in the standard installation. See parameters, results and limits in
[Mesh simplification](mesh-simplify.md).

`mesh.organic_union` and `mesh.remesh` use the included VTK backend.
`uv.unwrap` adds region cuts, density weights and distortion limits with included xatlas.
See [Anatomical modeling](anatomical-modeling.md) for all seven surface tools and their limits.
Python also exposes `app.deform` and `app.sculpt` keyword namespaces.

Query runtime schemas for exact parameters. Rotations use axis x/y/z and degrees about
world origin. Scale factors are positive, so use `mesh.mirror` for reflection.
Cylinder sections/height_segments control
circumference/vertical resolution. Explicit meshes need vertices Nx3 and triangle indices Mx3.
mesh.data independently pages vertices/faces/normals/UV, maximum 5000 each.

`mesh.mirror` reflects geometry across an axis-aligned plane (`axis`, `plane`) and reverses
face winding so normals stay outward. `duplicate=true` is the default: it keeps the source
and creates a new object, copying UV and optionally the material. UV is not flipped, so
text and asymmetric textures read mirrored on the result.

`scene.preview` draws a PNG with the fast preview backends; see the preview section below
for the renderer choice. Orbit cameras keep world +Z as screen up. Explicit
position/target/up cameras can roll. `azimuth_degrees` 0 looks along -Y, 90 along +X, 180 along +Y and 270
along -X; `elevation_degrees` 90 looks straight down and -90 straight up, where -Y
becomes screen up. `zoom` and `offset_x`/`offset_y` frame the subject. An optional
axis-aligned section uses `clip_axis`, `clip_position` (default: scene centre on that
axis) and `clip_keep`; the plane is tested in world coordinates, so it does not follow
the camera. `only_object_ids` and `exclude_object_ids` narrow the render to a
sub-assembly and framing follows that selection. `sample_textures` samples base-colour
textures so labels and screen pages are readable; alpha is not blended. `diagnostics`
reports the camera, backend, section and filters actually used.

`uv.generate` lists only installed methods in its `method` enum. If xatlas is absent,
the description identifies an incomplete installation and `x-unavailable-values` documents
that unavailable value. Requesting it returns `BACKEND_UNAVAILABLE` with the backend,
requirement, parameter path, requested value and `available_values`. Unknown methods
return `INVALID_PARAMETER`. Operations do not install dependencies automatically.
`mesh.boolean` stays registered even when manifold3d is missing and reports
`BACKEND_UNAVAILABLE`. A healthy standard installation includes every geometry backend.
Installation requires native backend packages on supported platforms.
All built-in geometry operations are included without feature selectors.

Materials must share their object's scene. PBR RGBA uses 0..1; checker RGBA uses integer
0..255. Texture slots: base_color, normal, metallic_roughness (glTF G roughness/B metallic).
Textured exports require UV. GLB is self-contained; glTF/OBJ return sidecar `files`.
glTF, GLB and static FBX export Y-up. Scene +Z becomes export +Y, and exported nodes
use readable, unique object names. OBJ and STL keep scene Z-up coordinates.
scene.load preserves IDs and replaces the matching scene; conflicting IDs/references fail.
Scene snapshots refer to textures in their workspace. Deleted scenes leave managed textures.

## Batches

```python
app.registry.execute("operations.batch", {"atomic": True, "operations": [
    {"operation": "mesh.translate", "arguments": {"object_id": cube.id, "x": 1}},
    {"operation": "mesh.rotate", "arguments": {"object_id": cube.id, "axis": "z", "angle_degrees": 45}},
]})
```

One failed atomic step rolls back all scene changes. Maximum 100 steps, no nested batches,
no filesystem/plugin lifecycle effects in atomic mode. Non-atomic mode returns each envelope
and success_count, retaining successful steps. No interpolation of earlier result IDs.

## Transactions

Every call with side effects snapshots the state and rewrites `state.json` before returning,
which makes scripted builds quadratic in object count. `app.transaction()` (or
`app.registry.transaction()`) groups many calls behind one rollback point and one state
write:

```python
with app.transaction():
    for index in range(200):
        app.meshes.create_cube(scene_id=scene.id, name=f"Panel {index}")
```

State and catalog are captured once on entry; any exception inside restores both and
discards every change, so a failed call must end the whole block rather than be swallowed.
The state file is written once on success. Nested transactions are rejected.

Stable errors: UNKNOWN_OPERATION, INVALID_PARAMETER, SCENE_NOT_FOUND, OBJECT_NOT_FOUND,
MATERIAL_NOT_FOUND, TEXTURE_NOT_FOUND, GEOMETRY_ERROR, RESOURCE_LIMIT, PERMISSION_DENIED,
WORKSPACE_BUSY, WORKSPACE_CLOSED, INCOMPATIBLE_FORMAT, BATCH_FAILED, OPERATION_COLLISION,
PLUGIN_INVALID, PLUGIN_NOT_FOUND, PLUGIN_COLLISION, PLUGIN_DEPENDENCY,
PLUGIN_FAILED, PLUGIN_STORE_BUSY, OPERATION_TIMEOUT, BACKEND_UNAVAILABLE,
UNSUPPORTED_OPERATION, INTERNAL_ERROR.

Settings caps counts, estimated geometry memory, file size, pixels and worker timeout.
`Settings.plugins_dir` selects the application plugin store, shared by workspaces. Its default
is `SCISSORS_PLUGINS_DIR` or `~/.scissors/plugins`. CLI `--plugins-dir` overrides this default.
`modeler.info` and `plugins.list` include the resolved `plugins_dir`. Enable/disable remains
per workspace; installation/uninstallation changes the shared store. Reopen other sessions
after package additions/removals. See [plugins](plugins.md) for storage and locking rules.
Estimates are not a hard OS ceiling for the main process. REST uses the same envelope;
missing GET resources return 404, malformed request 422, auth 401, host/origin 403, body 413.

## Python API

```python
from scissors import Scissors

with Scissors("workspaces/demo") as app:
    scene = app.scenes.create(name="Example")
    cube = app.meshes.create_cube(scene_id=scene.id, size=2)
    app.meshes.translate(object_id=cube.id, x=1)
    material = app.materials.create(scene_id=scene.id, name="Checker", roughness=0.6)
    texture = app.textures.generate_checker(width=256, height=256, cells=8)
    app.uv.generate(object_id=cube.id)
    app.textures.assign(material_id=material.id, texture_id=texture.id)
    app.materials.assign(object_id=cube.id, material_id=material.id)
    assert app.meshes.validate(object_id=cube.id, require_closed=True).valid
    print(app.export.glb(scene_id=scene.id, output="exports/example.glb").as_dict())
```

## HTTP API

```python
import httpx

response = httpx.post("http://127.0.0.1:8765/api/v1/operations/invoke",
    json={"name": "scene.create", "arguments": {"name": "REST example"}})
print(response.json())
```

GET `/api/v1/info`, `/operations`, `/operations/{name}`, `/plugins`, `/scenes`, `/scenes/{id}`
(all under `/api/v1`) inspect the same engine. Operation failures return `success=false`;
malformed request bodies receive 422. Bind defaults to loopback; other interfaces require
explicit `--host` and `SCISSORS_TOKEN`. Use a TLS proxy for network access.

## Native scene design

`scene.group(scene_id, object_ids, name)` creates an empty parent. `object.parent`
changes a parent without moving geometry. Parents must belong to the same scene.
Cycles are rejected. Group transforms move descendants once. Deleting a parent
reparents its direct children to its own parent. `scene.marker` records a world position.
Old state files load with `kind="mesh"`, no parent and no hidden flag.

`mesh.hide` hides an object and its descendants in previews and exports.
`mesh.show` clears only that object's flag. `mesh.hidden` reports effective visibility.
`mesh.pivot` sets a world rotation pivot. Existing default rotation remains about zero.
`mesh.place` sets absolute XYZ position, XYZ Euler rotation in degrees and positive scale.
`mesh.set_transform` sets an absolute affine 4x4 matrix. Both bake only the delta from
the recorded transform. `mesh.frame` reports the diagnostic local axes and pivot.

`scene.instance` creates an independent editable copy. GLB/glTF export shares matching
local geometry and materials, including copies placed with different transforms.
Editing one copy does not edit another. Group and marker nodes retain their hierarchy.
The exporter explicitly unbakes instance geometry before applying its node matrix once.

`uv.planar` accepts `u0,v0,u1,v1`, projection `axis`, `flip_u` and `flip_v`.
`uv.copy_from` requires matching indexed faces and vertex counts. `uv.flip_v` maps V to 1-V.
`scene.render_sheet` writes a labeled PNG and keeps each view PNG. Views accept
orbit angles or explicit world position/target/up cameras. Named head and stereo
view sets can expand into several cameras. The default sheet has six orbit views.

`scene.distance` and `mesh.intersect_test` accept `object_id`, `other_object_id` and
`tolerance`. Surface distance is separate from closed-solid penetration and overlap volume.
A contained solid can penetrate another while its surfaces remain separated.
Open meshes report only surface contact. `scene.collisions` filters by object IDs.
`mesh.self_intersect` reports nonadjacent triangle contacts, including coplanar contacts.
The default triangle-pair budget is 2,000,000. Configure `max_geometry_pairs` to change it.

`scene.digest` omits large geometry arrays. `scene.report` includes per-object validation.
`scene.query` uses world bounding boxes for point/radius or box selection.
`scene.budget` estimates triangles by material, mesh count, draw calls and RGBA texture bytes.
The texture estimate excludes mipmaps. Mesh count currently compares stored geometry.
`scene.orphans` reports unused scene materials and unused workspace textures.
Referenced materials and textures cannot be deleted. Texture deletion retains the file
so older saved scene snapshots can still use it.

`scene.edit(operations)` exposes atomic remote edits. It accepts up to 100 operations.
It validates each step but uses one rollback snapshot and one final state write.
Filesystem and plugin lifecycle operations are rejected. Nested edits are rejected.
`operations.schema(names)` retrieves several command schemas in one call.

## Profiles, curves and flat figures

`mesh.create_profile` accepts 2D `points`, optional `holes`, `plane` and `name`.
It normalizes contour orientation, rejects crossings and nested/touching/outside holes,
bridges holes and triangulates deterministically. Consecutive duplicate points produce warnings.
A profile is a normal planar mesh with UV. Hide or delete construction profiles before export.

`mesh.create_curve` creates a ribbon with positive `width`. It supports linear and
Catmull-Rom modes, `samples`, `closed` and the same planes. `mesh.extrude` extrudes the
profile or ribbon with distance, direction, taper, segments, caps and optional replacement.
Through holes retain side walls. Side UV runs along perimeter and extrusion distance.
`mesh.loft` supports profiles with holes, open or closed curve centerlines, caps,
a closed spine, and optional Catmull-Rom intermediate sections. Its default
`preserve_vertices=false` resamples by arc length and aligns section starts.
`preserve_vertices=true` retains each section's contour points without resampling,
rotation to a nearest start, or automatic winding reversal. It requires `resample=0`
and equal point counts for corresponding rings. Curves contribute centerline points,
not ribbon-edge vertices. Profile and curve inputs cannot be mixed.

`correspondence` is an optional list of section maps. Each map contains `object_id`,
the current `geometry_revision`, and `rings`. Each ring map has `source_ring`
(default 0), `start_index` (default 0 for closed rings), and `reverse` (default false).
Ring 0 is the outer contour. Every hole must appear exactly once after it.
Profiles with holes require explicit maps for every section. A simple one-ring
section can omit its map. Correspondence is only accepted in preserved mode.

```python
result = app.call("mesh.loft", object_ids=[lower_id, upper_id],
    preserve_vertices=True, correspondence=[{
        "object_id": upper_id, "geometry_revision": upper_revision,
        "rings": [{"source_ring": 0, "start_index": 2, "reverse": False}],
    }])
```

An input profile retains its stored boundary order when those indices still match
the actual boundary. Otherwise the operation derives boundary order from exact-position
topology. Returned section metadata identifies that choice and the exact source indices.
A closed ring starts at `start_index`, then advances or reverses cyclically while
keeping that start fixed. An open curve starts at its first point, or its last point
when reversed. Other starting points are invalid for open curves. Curve center-pair
metadata must still match the ribbon faces; stale layouts are rejected.

Preserved mode checks planarity within `max(largest_section_axis_extent, 1) * 1e-8`,
repeated points, edges of length at most `1e-12`, winding, and contour crossings.
Holes must have opposite winding to their outer contour and cannot touch, overlap,
nest, or cross it or another hole. Parallel section normals cannot oppose each other;
use explicit reversal. Source inputs remain unchanged. Invalid input rolls back the call.
Coplanar consecutive sections and coincident section centers are unsupported.

`closed` joins the last section to the first along the spine. Preserved mode requires
at least three sections for a closed spine. Caps apply only to closed contours on an
open spine. `smooth=true` adds four intervals per source segment and retains each
original section at layer `4 * section_index`.

Preserved results include `loft` metadata with closure, applied caps, layer and ring
counts, source revisions, source indices, logical geometry indices, and a
`render_vertex_to_geometry_vertex` map. Box UV splits render vertices per triangle;
the map refers to the mesh before that split. The result's `geometry_revision` binds
the map to the output mesh. Workspace persistence retains these diagnostics.

The bounded surface-contact check excludes triangle pairs sharing any exact position.
It reports its policy and status in `self_intersection_check`. Detected contacts fail
the operation. Pair or time limits produce `unresolved` and a warning, not a passed
check. This does not certify the absence of folds between adjacent triangles.
Geometry and UV-expanded vertex budgets are enforced before publishing the object.

`mesh.create_prism` and `mesh.create_pyramid` accept sides, radius, height, capped,
axis, pivot (`base` or `center`) and name. Faces are flat. `mesh.create_polygon`
and `mesh.create_star` create filled shapes with optional thickness.
`mesh.facet` splits triangle render vertices while retaining UV and material.
`mesh.figures` lists currently available native figure families.

Python supports positional calls. With exactly one scene, use
`app.meshes.create_prism(6, 0.1, 0.3)`. With multiple scenes, pass `scene_id` explicitly.
REST and MCP keep named JSON arguments and discoverable schemas.

## Repair

`mesh.boundaries(object_id)` returns closed boundary loops on topology welded by exact
position. Each loop has a `loop_index`, directed representative render `vertex_indices`,
and `edge_count`. The response includes `object_id` and `geometry_revision`.
Closed meshes return an empty `loops` list. Branched boundaries, inconsistent boundary
winding and non-manifold edges raise `GEOMETRY_ERROR`.

`mesh.bridge(first, second, name="Bridged mesh", replace=false, second_offset=null,
material_id=null, uv_policy="preserve")` joins one boundary from each of two meshes
in the same scene. Each selection contains `object_id`, `geometry_revision`, and
`loop_index` from `mesh.boundaries`. Stale selections raise `INVALID_PARAMETER`.
The operation creates a combined mesh with both source surfaces and an oriented
triangle strip. Contours may have different edge counts. Triangle placement follows
normalized boundary arc length without moving or resampling source vertices.
Source coordinates already include transforms; the new mesh has an identity transform.
Sources remain unless `replace=true`, which removes both sources after validation.
Only the selected boundaries are joined; other openings remain open.

The first loop starts at its reported first vertex. The second loop runs in reverse
source order and starts at the vertex nearest that anchor. `second_offset` overrides
this start with an index in the reversed second loop. The response reports the chosen
offset, `bridge_face_indices`, `source_object_ids`, and `source_vertex_offsets`.
Render seams, UV and vertex colors remain. Missing colors become opaque white.
Both meshes must have UV or both lack UV with `uv_policy="preserve"`; use
`uv_policy="discard"` to remove UV explicitly. The output uses one material.
Different source materials require an explicit scene `material_id` override.
Bridge triangles reuse boundary UV, which may stretch textures. Degenerate triangles,
inconsistent winding and non-manifold joins fail atomically. Self-intersections are
not ruled out; inspect the result with intersection queries and previews.

```python
first = app.call("mesh.boundaries", object_id=first_object_id)
second = app.call("mesh.boundaries", object_id=second_object_id)
joined = app.call(
    "mesh.bridge",
    first={"object_id": first["object_id"],
           "geometry_revision": first["geometry_revision"], "loop_index": 0},
    second={"object_id": second["object_id"],
            "geometry_revision": second["geometry_revision"], "loop_index": 0},
    replace=True,
)
```

`mesh.weld` merges coincident or nearby vertices and preserves UV seams by default.
`mesh.clean` removes degenerate/duplicate faces and unused vertices.
`mesh.flip` reverses winding, optionally restricted to a face selection.
`mesh.repair_winding` determines which faces must reverse to make selected edge
joins consistent. See [winding repair](#winding-repair) for scope and orientation rules.
`mesh.smooth` performs global Laplacian smoothing on
welded topology; boundaries stay fixed by default and volume can shrink.
`mesh.fill_holes(object_id, max_edges=64, selection=null, method="projected",
refinement=2, tangent_tolerance_degrees=20)` closes boundary loops with new patches.
A patch is a surface added inside an existing boundary. With no selection, the
operation fills every loop whose edge count is at most `max_edges` (3ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Å“512).
To keep windows or other openings, pass a `mesh.select_boundaries` result restricted
to the desired `loop_indices`. Stored boundary selections are also accepted.
Consumed fields are `object_id`, `geometry_revision`, and a nonempty unique
`loop_indices` list. Stale, foreign, empty or invalid selections fail with
`INVALID_PARAMETER`. A selected loop above `max_edges` fails explicitly; unselected
loops remain open. Without a selection, loops above the limit are skipped.

`method="projected"` triangulates a simple best-fit planar projection and lifts the
vertices back to the exact boundary. Nonplanar boundaries produce faceted patches.
This method adds no interior vertices and reuses boundary UV and colors.

`method="smooth"` fits a cubic height chart to neighboring surface positions and
boundary tangents. Refinement adds interior samples and interpolates boundary
residuals to keep the original boundary fixed. Interior edges subdivide consistently;
source boundary edges never split. `refinement` ranges from 1 to 4 and applies only
to smooth mode. Higher values increase patch detail and resource use.

Smooth mode measures the geometric angle between each new boundary triangle and
the adjacent existing triangle. Every such angle must be within
`tangent_tolerance_degrees` (greater than 0 and at most 90). Failure raises
`GEOMETRY_ERROR` with the loop index, achieved maximum and requested tolerance.
There is no automatic fallback to projected mode. The bound applies to the triangle
join; it is not a continuous-surface curvature certificate. A single-valued height
chart and a simple boundary projection are required. Sharp corners with vertical
collar faces can be unsuitable for smooth filling. Inspect self-intersections and
texture stretching; neither method certifies their absence.

Both modes preserve all source positions, triangles, UV, colors, material, object
ID and transform. Normals recompute. New smooth vertices interpolate boundary UV
and colors. Construction-specific topology metadata is cleared; older selections
and thickness certificates become stale when geometry changes. Mesh-size, working
memory, comparison, time and response-byte limits apply. Errors restore scene state.

Results include `filled_holes`, `filled_loop_indices`, `method`, `patch_face_indices`,
and `patches`. Each patch reports its source `loop_index`, new `face_indices` and
`max_join_angle_degrees`. The returned `selection` addresses all new faces with the
current geometry revision. Filling no eligible loops keeps the geometry unchanged.

```python
opening = app.call("mesh.select_boundaries", object_id=object_id, loop_indices=[1])
patch = app.call("mesh.fill_holes", object_id=object_id, selection=opening,
                 method="smooth", tangent_tolerance_degrees=15)
app.call("mesh.selection_save", name="Repaired panel", selection=patch["selection"])
```

`mesh.convex_hull` creates a separate hull using the included Manifold backend.
`mesh.collider` reduces that hull to `max_faces` or fails if conservation prevents it.
Convex colliders cover concave cavities. Sources remain in the scene.

## Native mechanical figures

`mesh.create_rounded_box(size, corner_radius=0, segments=4, edge_bevel=0, axis="z")`
creates a box centered across its base axes with its base at zero.
A zero corner radius and zero bevel produce eight vertices and twelve triangles.
Positive radii round vertical edges. Segments range from 1 to 16.
The radius must not exceed half the smaller base dimension.
Edge bevel chamfers the upper and lower edges and must be smaller than half every dimension.

`mesh.create_tube(points, radius, sides=8, caps=True, closed=False)` sweeps circular
sections along 2ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â¦ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã¢â‚¬Å“256 three-component points. Sides range from 3 to 32.
Parallel transport avoids arbitrary twist. Closed loops distribute frame mismatch.
Repeated points and abrupt reversals are rejected with a point index.

`mesh.create_louver(width, height, blade_count, blade_angle_degrees=30,
blade_thickness=0.004, frame_thickness=0.012, frame_depth=0.02, depth=0.01)`
creates closed blades and an optional frame. Frame thickness zero omits the frame.
Blades keep two percent clearance. Invalid blade dimensions are rejected.
At steep angles blades can extend beyond depth; the frame remains unchanged.

`mesh.create_switch_grid(columns, rows, spacing, base_width, base_height,
base_thickness=0.004, toggle_length=0.016, toggle_radius=0.0035,
toggle_angle_degrees=20)` creates a plate below Z=0 and closed twelve-sided toggles.
Rows and columns range from 1 to 12. Tilt ranges from -80 to 80 degrees about +X.
Toggles deliberately penetrate the plate at their base.

All four operations also accept scene_id and name. They need no plugin.
They respect configured geometry and memory budgets before allocating their arrays.

## Rounded bodies and sheet figures

`mesh.create_capsule(radius, height, segments=32)` uses total axial height, including
both hemispheres. Height must be at least twice the radius. Equality gives a sphere.
`mesh.create_dome(radius, height, segments=32, capped=True)` creates an elliptical dome
with the specified base radius and axial height. `mesh.create_hemisphere(radius)` uses
equal radius and height. Disabling caps leaves the base disk open.
These operations accept axis, pivot (`base` or `center`) and name.

`mesh.create_polyhedron(kind, radius=1)` supports tetrahedron, octahedron, dodecahedron
and icosahedron. Radius is the distance from the center to a vertex. Faces are flat.
The default pivot is center. The standard Manifold backend constructs its convex hull.

`mesh.create_plate(size, thickness, holes=[{"center": [x,y], "radius": r, "sides": 24}])`
uses two base dimensions. Circular holes must stay inside the plate and cannot touch or
overlap. It creates UV and accepts material_id from the same scene.
`mesh.create_wedge(size, taper=0)` uses three dimensions. Taper is the ratio of lower-end
height to upper-end height. Zero gives a triangular ramp; one gives a box.

`mesh.create_gear(teeth, radius, thickness, tooth_depth=None, bore_radius=0)` uses a
straight tooth outline. Radius is the tooth-tip radius. Default tooth depth is 15 percent
of radius. The bore must be smaller than the root radius.
`mesh.create_spring(radius, wire_radius, coils, height, segments=32, sides=8)` sweeps a
helix. Height is centerline axial travel, not the complete wire bounding-box height.
Segments means samples per coil. Wire diameter must be smaller than coil pitch.
Plate, wedge, gear and spring accept capped, axis, pivot and name.

`mesh.create_star(kind="cross"|"arrow"|"star")` groups these variants in one family.
For cross/arrow, inner_radius controls arm/shaft half-width and outer_radius controls extent.
Arrow points along +X in its initial XY plane. Thickness extrudes the filled outline.

`mesh.create_torus` defaults to a full circle. Add `arc` in degrees for a
partial torus and `capped=False` to leave its ends open. An odd positive integer `twist`
creates a (2, twist) torus knot. Knots need at least sixteen major sections per twist.
Their wire radius must be smaller than one third of the major radius.
The command accepts axis and pivot; the default pivot is the center.
The figure table lists the available variants of each family.

`mesh.split_normals(object_id, angle=30)` splits edges whose face angle exceeds the
threshold. UV seams remain separate render vertices but share smooth normals where
the angle allows it. Normal arrays persist and transform correctly under nonuniform scale.
Further geometry edits recompute normals; call split_normals again after editing.

### Arrays, placement and measurement

`mesh.delete(object_id)` removes one object. Pass `object_ids` to remove many in one call.
The batch validates every ID before deleting, runs inside one rollback point and rewrites
the state once, so it is far faster than one call per object. Children of a deleted object
are re-parented to its parent. Unknown IDs abort the whole batch and change nothing.

`mesh.duplicate` copies the complete subtree and remaps parent IDs. Copies have independent
editable arrays. Matching local geometry can share export meshes.
`mesh.distribute(scene_id, object_id, count, hole_radius, pattern="fibonacci", orient="normal")`
creates cutter cylinders over the target's bounding sphere. Each cutter passes through the
target center, so one axis drills two holes. `orient="normal"` aligns every cylinder with
the outward radius; `orient="z"` keeps the world Z axis. `length` defaults to 2.4 times the
target radius, and `sections` controls cylinder resolution. The result returns `object_ids`
and the 4x4 `matrices`, which match `trimesh.geometry.align_vectors` for the same axes.
Follow the distribution with `mesh.boolean`; `delete_inputs=true` consumes the cutters in
the same call.
`mesh.array(object_id, count=2, mode="linear", offset=[1,0,0])` includes the source in count.
For polar arrays use `mode="polar"`, axis, center and angle_degrees. A full 360-degree array
does not repeat its start angle. A partial arc includes both ends. Set rotate=false to keep
each copy's orientation. UV and material assignments are copied. Workspace memory limits
apply before allocating an array.

`mesh.mirror` accepts normal and point for arbitrary planes. Otherwise axis and plane retain
their existing meaning. It transforms the whole subtree, reverses winding and updates the
recorded matrix. By default it duplicates; duplicate=false changes the source.
`scene.symmetrize` mirrors selected unmatched meshes and markers across axis/plane.
Matching uses quantized world vertex positions and triangle counts, not semantic names or
material equivalence. It skips groups and existing counterparts. Asymmetric objects crossing
the center plane may overlap their copies. This operation does not cut or merge geometry.

`mesh.align(object_id, target_object_id, target_face)` places a source support plane against
the opposing target triangle. Use source_face to select a source triangle explicitly.
Otherwise axis/source_side choose the source normal. Rotation defaults to true.
`mesh.snap` uses the closest target surface point to point (or the source bounds center).
Rotation defaults to false. Both support gap in world units and move descendants once.
Targets must be meshes in the same scene and cannot be moving descendants.
Face indices refer to current triangles and may change after topology edits.

`deform.warp(object_id, bend=0, twist=0, taper=1, axis="z")` uses degrees for bend/twist.
Taper is the far-end scale. It deforms current world vertices about the chosen world axis.
It preserves UV, material and triangle connectivity. Sparse sections give coarse bends.
It rejects zero axial extent and bend radii that fold a cross-section. It recomputes normals;
reapply split_normals and inspect self-intersections after deformation.

`mesh.measure` is read-only. mode="distance" returns minimum triangle-feature distance
between face_a and face_b. object_id_b defaults to the source object.
mode="angle" returns the angle between outward triangle normals and the acute plane angle.
mode="diameter" fits a circle to explicit vertex_indices or a hole rim in the connected
planar region containing face_a. hole_index selects holes by decreasing enclosed area.
The exterior rim is excluded. Measurements use current world geometry, including transforms.
Nonplanar and noncircular rims are rejected using tolerance in world units.
Diameter is the fitted rim circle diameter, not an inscribed polygon diameter.

### Managed image editing and PBR channels

`texture.draw_text(text, position=[0,0], font_size=24)` creates an RGBA texture or draws
over texture_id. New canvases use width/height and background. Colors are four bytes.
The default font is Pillow's bundled font. font_path accepts workspace TTF/OTF files.
The result includes text_bounds and clipped. Font results depend on the selected font
and installed Pillow version. Text size, mask area, image pixels and file bytes are bounded.
`texture.compose(layers, width=256, height=256)` alpha-composites ordered layers.
Each layer has texture_id, position, optional size and opacity from zero to one.
Images outside the canvas are clipped. Position is measured from the top-left pixel.

`texture.resize(texture_id, size=[width,height])` uses Lanczos filtering.
`texture.crop(texture_id, rectangle=[left,top,right,bottom])` requires an internal rectangle.
`texture.rotate(texture_id, angle, expand=True)` uses counterclockwise degrees and transparent
padding. These commands create new managed PNGs. Sources and their references remain intact.
`texture.export(texture_id, output)` writes PNG, JPEG or WebP. JPEG flattens alpha over white.
Image writes are rejected in atomic scene edits and Python transactions.
Output paths must be unused. This also applies to generated checker textures and prevents
overwriting images referenced by older snapshots. Use a new path or omit output
to obtain a unique managed path.

`material.create` and `material.update` accept emissive as RGB factors from zero to one.
The default [0,0,0] disables emission. `texture.assign` accepts
slot="emissive" and slot="occlusion". Set a nonzero emissive factor to enable its texture.
glTF/GLB exports include emissiveFactor, emissiveTexture and occlusionTexture.
The preview uses the material base colour and, with sample_textures, its base-colour image.
The VTK backend interpolates normals; the painter shades each face flat.

`mesh.tangents(object_id)` returns normalized XYZ/handedness frames and marks the mesh for
glTF TANGENT export. It requires nondegenerate UV triangles and separated mirrored seams.
The method averages UV derivatives using triangle-corner angles. It is not MikkTSpace.
Tools requiring exact MikkTSpace must rebake their normal maps with a matching implementation.
Exports recompute frames from current local geometry and UV, avoiding stale cached arrays.
Normal-textured meshes receive tangents automatically during glTF/GLB export.
The exporter adjusts handedness for its 1-V conversion. Non-UV geometry must be unwrapped
before assigning normal maps. UV-less or invalid UV meshes fail with a geometry error.

`texture.atlas_pack(scene_id, object_ids=None, size=[2048,2048], padding=4, merge=True)`
packs selected textured or solid materials into aligned PBR atlases. By default it selects
visible meshes. Every selected mesh needs UV in [0,1] and a same-scene material.
Tiled UV must be baked first. Each material gets a tile at its largest channel resolution.
Smaller channels are upsampled; no source channel is downsampled. One-pixel and solid tiles
use at least two pixels per side. Normal vectors are normalized after resampling.
Padding repeats edge and corner pixels. It protects base-level filtering; deep mip levels
can still bleed across tiles. Rectangles use texel centers and preserve the V convention.
Packing uses deterministic shelf ordering for current material IDs, without rotation.
An atlas that does not fit raises RESOURCE_LIMIT instead of reducing resolution.

Materials with equal scalar PBR factors share a new material. All channel images use the
same rectangles, including flat-normal/white defaults for missing slots. Old materials and
source textures remain available. The shared registry rolls back UV/material changes.
The command writes new files and cannot join an atomic scene edit or transaction.
A late failure can leave unused new image files. Existing files are never overwritten.

With merge=true, compatible leaf meshes under the same parent and with the same visibility
combine into the first object's stable ID. World geometry, UV and normals are preserved.
Absorbed IDs disappear; object_mapping identifies the survivor. Objects with children or
incompatible material factors remain separate. Set merge=false to retain every object.
Sharing a material alone does not reduce draw calls; geometry consolidation does.
The result reports selected visible draw estimates before/after. scene.budget counts unique
meshes using glTF local geometry, UV, normal, tangent and material sharing rules.

### Physical texture density

`uv.generate` accepts either `object_id` or unique `object_ids` from one scene.
The multi-object form requires `pixels_per_meter` and
`texture_resolution=[width,height]`. These parameters also work with one object.
Scene units convert to meters; stored transforms are already baked into positions.

```python
app.call(
    "uv.generate",
    object_ids=[wall_id, stair_id],
    method="box",
    pixels_per_meter=128,
    texture_resolution=[2048, 2048],
    density_mode="atlas",
    atlas_region=[0.05, 0.05, 0.95, 0.95],
    padding=4,
)
report = app.call("uv.inspect", object_id=wall_id, texture_resolution=[2048, 2048])
```

Without a density target, the existing single-object generation workflow applies.
With a target, generated planar/box charts retain metric proportions in pixel space,
including rectangular images. `preserve_uv=true` instead fits the existing charts;
`method` does not regenerate UV in that mode. Both modes may split render vertices
at chart seams. World positions, face order and materials remain in place.

`density_mode="atlas"` scales each continuous island uniformly and packs its pixel
bounding rectangle into `atlas_region=[u0,v0,u1,v1]`. Padding is measured in pixels.
Packing uses height-sorted shelves without rotation or density reduction. It can fail
where a different packing strategy could fit. A capacity failure reports
`RESOURCE_LIMIT` with `reason="ATLAS_CAPACITY"` and leaves all objects unchanged.
Positive-area overlap within an island is rejected at a tolerance of 1e-10 square
pixels; islands occupy separate rectangles. Geometry-pair, memory and time limits
apply to overlap checks. This operation creates UV, not texture images or materials.

`density_mode="repeat"` allows overlap and UV outside [0,1]. It scales islands about
their original centers and requires the whole texture region and `padding=0`.
It does not repeat inside a subregion of an atlas. The consumer must use repeat
sampling for that image. Existing unequal overlapping charts can move relative
to each other when their required scale factors differ.

The result's `density` report includes the target, island count and measurements
per object. `uv.inspect(texture_resolution=...)` measures the current UV without
changing it. Density is the square root of pixel triangle area divided by physical
triangle area. Overlapping surfaces count separately. Reports include minimum and
maximum face density, covered area fraction, degenerate UV triangle count and
maximum pixel-space anisotropy. Uniform island scaling preserves existing distortion;
curved islands can have different density on different faces. Degenerate UV cannot
meet a target and fail without publishing partial UV changes.

The given resolution describes the image that will actually sample these UV.
Enlarging an atlas does not create detail in a lower-resolution source image.
The operation does not measure source-image detail or generate lightmap UV metadata.

### Scene variants, checkpoints and figure tables

`scene.clone(scene_id, name=None)` copies the complete scene with fresh scene, object and
material IDs. It preserves metadata, units, world geometry, hierarchy and visibility.
Materials are independent copies. Immutable workspace textures remain shared.
`scene.copy_objects(from_scene, to_scene, object_ids)` copies selected objects and all their
descendants. An overlapping selection copies each object once. Parents outside the copied
selection are removed while world geometry stays in place. The result returns object_mapping
and material_mapping. Copying into the same scene is supported. Instances retain sharing
relationships when their source is copied too. Geometry memory limits apply before allocation.
Coordinates are copied numerically; units are not converted between scenes.

`scene.checkpoint(scene_id, name)` saves or replaces a named checkpoint atomically.
Names contain 1ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â¦ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã¢â‚¬Å“64 ASCII letters, digits, underscores or hyphens and start with a letter/digit.
Files live under the reserved `.checkpoints` workspace directory. They retain stable scene,
object and material IDs and relative references to immutable texture files. They survive
restart and workspace relocation. They are not standalone bundles of texture pixels.
`scene.revert_to(scene_id, name)` restores one checkpoint and its texture references.
It can restore a deleted scene. It rejects texture-ID conflicts and missing image files.
Registry rollback protects the current workspace if restored state fails validation.
`scene.compare_snapshot(scene_id, name)` compares checkpoint to current scene by stable ID.
It returns added/removed object and material IDs, changed top-level model fields and changed
scene properties. It compares values, not rendered similarity. Other scenes and plugin state
are unaffected. Checkpoint writes cannot join atomic edits. Read-only comparison and restore
can join atomic scene.edit or app.transaction; only their scene state changes roll back.

`scene.create_table(scene_id, rows)` creates native figures atomically with one
successful state commit. Each row contains figure and optional parameters, name, transform,
material_id, parent_id and repeat. Repeat emits several copies of the row, so a repeated
fastener is one row instead of many. Rows are not capped at 100; the call is bounded by
MAX_TABLE_OBJECTS (20000) and the workspace geometry budget. Figure accepts a mesh.figures
kind or full native operation name.
Parameters follow that figure's discovered schema; scene_id belongs outside the rows.
Transform accepts position, XYZ Euler rotation in degrees and positive scale, or a 4x4 affine
matrix. Placement is absolute. Row material/parent IDs must already exist in the same scene.
Name overrides the figure's name parameter. Failed creation, placement or assignment rolls
back the complete table. No executable code or plugin lifecycle operation is accepted.
The result returns compact row/object IDs; use scene.digest to review the whole assembly.

```python
app.call("scene.create_table", scene_id=scene.id, rows=[
    {"figure": "prism", "parameters": {"sides": 6, "radius": 0.1, "height": 0.2},
     "name": "Fastener", "transform": {"position": [1, 0, 0]}},
    {"figure": "rounded_box", "parameters": {"size": [1, 0.4, 0.2], "corner_radius": 0.04},
     "name": "Housing"},
])
app.call("scene.checkpoint", scene_id=scene.id, name="shape")
```

### Imported assets and image planes

`scene.import_mesh(path, scene_id=None)` reads local OBJ, STL, GLB, PLY or FBX.
Omitting scene_id creates a scene. Existing scenes receive a named import root group.
The reader runs in the geometry child with a timeout and bounded source/sidecar bytes,
geometry counts, image pixels and output. Trimesh/Pillow handle common formats;
the required `ufbx` library reads binary and ASCII FBX. Quads use a stable diagonal;
VTK triangulates larger polygons in a best-fit plane.
Parsing can allocate memory before post-load checks; this is not an OS sandbox on Windows.
Paths must stay inside the workspace. OBJ sidecars may use sibling workspace folders.
Remote URIs, escaped paths and reserved engine/plugin paths are rejected.
Missing or failed sidecars fail the import instead of silently dropping referenced assets.

The importer preserves hierarchy, instances, triangles, UV, normals, vertex colors and
supported PBR channels. Face colors split render vertices to keep discontinuities.
Multi-material meshes split into parts. Cameras and lights are omitted from the scene view.
GLB skins and animation are omitted with a warning. FBX retention is described below. Alpha MASK is approximated as BLEND. Other unsupported source extensions
are not represented by the Scissors model. GLB auto-converts Y-up to Z-up.
OBJ/STL/PLY default to Z-up. Override source_up with "x", "y" or "z" when needed.
Positive scale changes dimensions uniformly; position applies a world translation.
OBJ/STL/GLB/PLY units are not inferred. FBX uses its declared axes, handedness and unit scale.
Automatic FBX conversion produces right-handed Z-up geometry in meters for a new scene,
or in the destination scene's units when extending an existing scene. Explicit `source_up`
overrides the FBX axis metadata while retaining its unit conversion. `scale` is an additional
multiplier, and `position` is in destination scene units.
Transforms bake once and remain recorded. Output IDs are new.
Images become new managed PNGs; a late failure may leave unused new image files.

FBX preserves static mesh instances, per-instance material assignments, polygon triangulation,
UV/normal/color seams and geometric transforms that do not affect child nodes. Embedded images
take precedence over stale file paths. External images must use workspace-contained relative
paths and share the source/sidecar byte budget. Phong/Lambert materials are approximated as PBR.
Supported image slots are base color, normal, emission, occlusion, roughness and metallic;
separate roughness/metallic images become a combined texture. Scissors FBX material factors
and ORM/occlusion image properties are recognized. `modeler.info.backends.import_fbx` reports reader availability.
FBX previews show the base mesh without animation or blend-shape evaluation.
The default `fbx_mode="preserve"` retains binary FBX rigs, animation curves, bind matrices
and embedded source media in an immutable workspace document. The result includes `rig`;
`scene.inspect` lists retained `rigs`. Complete FBX export preserves the original document,
including source axes and units. This mode requires a new/empty scene, automatic axes,
scale=1 and no position. Materials and rig placement must stay unchanged.
Conservative mesh edits can retain original vertex positions/UV and remap exact skin weights.
Other formats, partial scenes, material splitting, LOD export and unsupported edits fail
with `UNSUPPORTED_OPERATION`, rather than silently dropping the rig.
Set `fbx_mode="static"` to discard source rig/animation explicitly.
See [FBX rig retention](fbx-rig.md) for the supported workflow and limits.
Layered/procedural textures, texture transforms, maps using additional UV sets and polygon holes
must be baked or triangulated before import. Separate opacity maps are omitted with a warning;
base image alpha and the opacity factor are retained. Arbitrary shader graphs are not reproduced.

```python
result = app.call("scene.import_mesh", path="assets/model.fbx")
object_id = result["object_ids"][0]
app.call("mesh.simplify", object_id=object_id, reduction_percent=50)
app.call("scene.export", scene_id=result["scene_id"], output="exports/model.fbx", format="fbx")
```

The CLI uses the same registered operation:

```bash
uv run scissors --workspace workspaces/agents operations invoke scene.import_mesh --arguments '{"path":"assets/model.fbx"}'
```

Imported colors persist, follow affine transforms, survive copying/atlas merging and export
as glTF COLOR_0. General topology edits currently discard them. Previews shade vertex
colors. glTF enables alpha blending for transparent base-color image pixels.
Group/marker export keeps recorded orientation and scale without moving world geometry.

`reference.plane(scene_id, path, axis="y", size=None, position=None)` creates a double-sided
image mesh. Size is [width,height] in scene units. Default width is one; height follows
image aspect ratio. Image +U/+V map to Y/Z for axis X, X/Z for Y and X/Y for Z.
Position is the plane center. Hide reference geometry before game export.
Import/reference creation writes files and cannot join atomic scene edits or transactions.

### Fast preview backends and camera animation

Successful OpenGL capability probes are cached for the process. A failed probe retries
once, with a ten-second timeout per attempt. Negative results expire after 30 seconds
so later requests can detect a recovered device. Concurrent requests share one probe.
Driver contexts are created in a child process during discovery, including HTTP calls.

`scene.preview` draws the PNG with the VTK offscreen renderer when an OpenGL context
exists and with a Pillow painter when it does not. The result reports the backend in
`renderer` ("vtk" or "pillow"); `renderer_detail` carries the OpenGL device string when
VTK ran. `renderer="vtk"` fails with BACKEND_UNAVAILABLE if no context can be created and
`renderer="pillow"` forces the painter.

Set projection="perspective" or "orthographic" to choose the camera model.
camera_position and camera_target use world coordinates. camera_up defaults to world Z,
with a stable fallback at the poles. fov is vertical degrees. near/far are positive forward
camera distances. Omitted position/target auto-frame the selected visible geometry using
azimuth/elevation.

Both backends share one camera model, so framing matches between them. VTK interpolates
vertex normals, samples base-colour textures per pixel and honours vertex colors. The
painter sorts triangles by depth and shades each face flat, sampling a texture once per
face. light_direction points from the surface toward a world directional light; omitted
light follows the camera. ambient controls the ambient term and light_strength scales the
direct light. background is RGB in [0,1]. transparent=true keeps uncovered pixels at alpha
zero. Neither backend casts shadows and neither uses environment lighting, reflections or
tone mapping: previews are review images, not physically exact game renders.

Selection filters, wireframe, zoom, offsets and the whole-triangle diagnostic section
remain available. `scene.compare_reference` renders with the same backend and composites
the image beside or over the reference photo. Render sheets accept projection and
transparent for every view. Pixel/geometry, texture-cache, projected-work and elapsed-time
limits bound previews.

render_pass="depth" reads the OpenGL z-buffer and writes a 16-bit grayscale PNG plus a
`.depth.npz` sidecar with float32 depth, boolean coverage, near and far. Depth is positive
camera-forward distance in scene units, not radial range. Background depth is infinity.
The PNG maps near to zero and far to 65535. With transparent=true the depth image uses
RGBA8; the NPZ keeps numeric depth. Load it with allow_pickle=False.

render_pass="normal" draws world-space vertex normals as colours: RGB = (normal+1)/2 with
lighting off, so +Z is (128,128,255), +X is (255,128,128) and -Y is (128,0,128). Flat faces
need hard normals first: run mesh.split_normals so each face keeps its own normal. The
result reports normal_space="world". Both diagnostic passes need the VTK backend and fail
with BACKEND_UNAVAILABLE when no OpenGL context exists. Multisampling is disabled for them
so every covered pixel keeps an exact value.

`scene.turntable(scene_id, output="previews/turntable.gif", frames=24, size=256, fps=12)`
renders a full camera orbit without changing geometry. Default projection is perspective;
elevation_degrees controls its elevation. GIF uses an opaque palette and 10-ms time steps.
Identical encoded frames may combine: frames reports actual count and requested_frames
reports the requested count. Frame cache, file size and total elapsed time are bounded.
These artifact writers cannot join atomic scene edits or Python transactions.

### Surface thickness and plane cuts

`mesh.offset(object_id, distance=0.01, method="miter", miter_limit=10, replace=True)`
moves welded positions while preserving render seams, UV, colors and material.
Distance is signed in world units. Miter mode solves incident face-plane offsets by least
squares. It keeps planar corners sharp; curved regions receive a discrete approximation.
method="normal" uses a unit average normal instead. Excessive corner expansion, reversed
faces and inverted closed volumes fail. This is not an exact signed-distance surface.

`mesh.shell(object_id, thickness=0.01, offset=0, method="miter")` creates outer/inner faces
and closes every open boundary with walls. Offset -1 keeps the source as the outer surface;
+1 keeps it as the inner surface; zero centers the thickness on the source.
Closed sources create a hollow solid with an inward inner boundary. Open sources become
closed shells. UV and material remain on the two surfaces. Wall UV uses perimeter U and
thickness V. Colors interpolate from boundary endpoints. Consistent manifold topology is
required. Use split_normals after shelling when hard shading edges are needed.
Offsets and shells can self-intersect in tight concave regions; inspect them explicitly.
Resource limits bound output growth. These operations do not automatically resolve collisions.

`mesh.clip(object_id, normal, point=[0,0,0], keep="positive", capped=True)` keeps the selected
half-space. `mesh.slice(object_id, normal, point, capped=True, replace=False)` creates both
halves. Slice retains the source by default; replace=true reuses its ID for the positive half.
Clip changes the source by default. Use replace=false for a separate result.
Both return IDs and summaries. Parent, material and recorded affine transform stay intact.
Children stay with the original object; geometry copies do not duplicate its descendants.

Cuts interpolate existing UV, colors and shading normals. New caps use planar UV, flat
normals and the source material. The included VTK worker triangulates multiple contours
and holes. Boundary refinement preserves intermediate collinear cut vertices to avoid
topology cracks. Plane tolerance is absolute in scene units, default 1e-8.
Cutting an open surface may not form a closed cap contour; use capped=false in that case.
Empty cuts, zero normals, inward closed sources with caps and invalid boundaries fail.
Closed capped inputs must remain watertight. When a cap fails that check, the error details
report boundary_edges, non_manifold_edges, loops_found, closed_loops, open_loops, cap_faces
and a suggestion, so the caller can retry with capped=false or move the plane.
Diagnostic preview sections remain independent
and hide triangles without editing geometry. All four operations support atomic scene edits.

### Attributed booleans

`mesh.boolean` defaults to preserve_attributes=true. Manifold interpolates UV, colors and
normals and tracks the source operand per face. UV seams remain separate render vertices
while exact positions merge for topology. Inputs must be distinct, closed outward meshes
in the selected scene. Sources remain unchanged unless delete_inputs=true, which removes
the operands inside the same rollback point and returns deleted_object_ids. Result positions
are world coordinates with an identity transform.

material_policy="first" applies the first operand's material. material_policy="source"
keeps contributing materials. In difference mode an unassigned cutter falls back to the
first material; cut_material_id overrides cutter-contributed faces. Multiple output materials
produce a group: object_id names the root and object_ids lists its parts. Individual material
parts can be open; combined reports volume/closure for the full solid. One material produces
a single mesh with summary fields. Pass part IDs to later single-mesh tools.

Existing UV stays interpolated. cut_uv="planar" creates world-plane UV on new cut surfaces;
uv_scale is scene units per tile. cut_uv="cutter" keeps cutter UV. Missing UV is projected.
Projected UV may repeat outside [0,1]; unwrap or bake before atlas packing.
faces_by_source reports contribution counts. Empty or invalid results roll back state.
preserve_attributes=false requests geometry-only output. Attribute policy
options require preservation. Attributed booleans support atomic scene edits/transactions.
Manifold 3.5.4 or newer is required for the Mesh64 property and run-provenance interface.

### Delivery subsets, material files and LODs

`scene.export` accepts only_object_ids and exclude_object_ids. Selections expand subtrees;
excluded subtrees and hidden objects are omitted. Ancestors remain as empty transform frames
when their geometry is outside the selection. This preserves world placement and hierarchy.
export_transform is an invertible affine 4x4 matrix in scene coordinates. It applies once
at the export root before the Y-up conversion for glTF, GLB and static FBX.
root_name selects the sanitized root name.
Neither option changes stored geometry. A root named world is safely disambiguated.
STL/OBJ/PLY bake every mesh instance, including its graph placement and inverse normal matrix.

split_materials=true combines selected world geometry into one mesh per material for export.
It preserves UV, colors and shading normals and leaves source objects intact. Mesh hierarchy
flattens; empty frames and markers keep their world poses. Combined meshes must fit normal
geometry limits. Textured parts still require UV. Export metadata reports the resulting mesh count.
Each source part is validated before concatenation. Parts retain disjoint index ranges
even when their positions coincide. Exact contact between different parts is not a
topological weld and does not invalidate a render batch. Invalid topology within a
source part still fails. The export view records source vertex/face ranges in
`export_material_parts` metadata. This transient representation does not enter the
editable scene or change normal solid-modeling validation. Material-batched bundles
use the same service. LOD simplification processes source parts before material batching.

lod_reductions=[30,60] generates additional files with those percentages removed from the
base selection. Each level starts from the source geometry, not the previous level.
VTK retains topology, boundary vertices and UV seams. Normals recompute; surviving colors
are retained. Conflicting vertex-color seams must be baked to images before simplification.
lod_max_error_relative bounds the existing simplifier's error estimate.
The reductions must be unique and increasing. Every level must reduce actual face count.
lod_require_target=true also requires the global requested face target. Failures report
GEOMETRY_ERROR with reason TARGET_NOT_REACHED. Results expose actual counts and warnings.
Each level uses its own directory to avoid sidecar collisions. A relative-path `.lods.json`
manifest records levels. These are separate game-ready assets, not a runtime LOD extension.

`scene.split_export(scene_id, output_dir, by="object"|"group"|"material", format="glb")`
writes one asset per visible mesh, top-level subtree or material. It accepts only_object_ids
and export_transform. Each part has a safe, unique directory and separate sidecars.
Object mode does not include child mesh geometry. Group mode uses the highest ancestor.
Material mode never includes foreign-material descendants through hierarchy expansion.
The output manifest uses relative paths. Exporting files is not an atomic scene operation;
late errors can leave completed files. Source scene state remains unchanged.

PLY is a real binary PLY writer. It flattens geometry, preserves vertex normals/colors and
writes s/t properties when UV is present. Base color factors multiply vertex colors.
Texture images, PBR channels, hierarchy and instance sharing are omitted. GLB remains the
preferred self-contained material format. FBX, DAE and USDZ use dedicated export writers.

### Portable asset bundles

`scene.export_bundle` publishes a directory or ZIP from one detached scene snapshot.
All callers use the central registry, which serializes capture and publication.
MCP HTTP JSON replies and event streams let the HTTP server choose response framing;
MCP responses omit fixed Content-Length headers. REST response lengths are retained.
The source scene, textures, materials, transforms, hidden flags, and parenting remain
unchanged. The operation declares scene read and filesystem read/write permissions.
It cannot join `scene.edit`, an atomic batch, or `app.transaction`.
Its descriptor reports `side_effects=true` and `scene_mutation=false`: files change,
while the unchanged source scene needs no post-publication checkpoint. Native operation
registrations can set `Operation.scene_mutation` or the matching `add_function` option.
Omission retains the checkpoint policy implied by `side_effects`. A scene mutation
requires `side_effects=true`.

```python
result = app.call("scene.export_bundle", scene_id=scene_id,
    output_path="exports/asset.zip", package_format="zip",
    variants=[{"name": "editable", "preset": "hierarchy"},
              {"name": "runtime", "preset": "material_batches"}],
    preview_renderer="pillow", preview_size=128,
    preview_views=[{"type": "camera", "name": "Player",
                    "position": [0, -2, 1.6], "target": [0, 0, 1.6], "fov": 90}],
    verification="reopen")
```

Parameters:

- `output_path` stays inside the workspace and cannot use reserved paths or replace
  texture dependencies. ZIP output requires a `.zip` suffix. A directory cannot use it.
- `variants` contains 1ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã¢â‚¬Â¦ÃƒÂ¢Ã¢â€šÂ¬Ã…â€œ8 named presets. Names use 1ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã¢â‚¬Â¦ÃƒÂ¢Ã¢â€šÂ¬Ã…â€œ64 ASCII letters, digits,
  underscores, or hyphens, start with a letter/digit, and are unique ignoring case.
  Windows device names are rejected. Omission selects `hierarchy` and `material_batches`.
  Each variant currently supports `format="glb"` only.
- `hierarchy` retains visible nodes, parenting, and supported geometry instances.
  `material_batches` merges visible meshes by material and flattens parenting.
  Both return source-to-export ID and node-name mappings. Hidden nodes are marked omitted.
  Names are made unique and reserve the exporter's `world` base frame. A consolidated
  material mesh must pass normal mesh validation.
- `include_scene=true` includes `scene.json` with stable IDs, all source objects and
  materials, and only that scene's texture dependencies. `include_textures=true` copies
  captured dependency bytes under `textures/`. Unrelated workspace textures are excluded.
  A textured editable scene requires both options. With no editable scene, raw texture
  files can be omitted because GLBs embed their images and buffers.
- `preview_views` reuses the typed orbit and explicit-camera views of `scene.render_sheet`.
  `preview_view_sets` reuses its named head/stereo helper. Both are optional.
  `preview_size` is 64ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã¢â‚¬Â¦ÃƒÂ¢Ã¢â€šÂ¬Ã…â€œ2048, default 256. `preview_renderer` is `auto`, `vtk`, or `pillow`.
  The package retains a sheet, its individual tiles, and actual camera metadata.
- `report=true` includes `report.json` with actual mesh validation results and limitations.
  It does not request mesh self-intersection checks. `README.txt` records import/setup notes.
- `verification="reopen"` validates GLB structure, embedded dependencies, actual node and
  triangle counts, and reopens GLBs through Trimesh to compare counts and world bounds.
  `verification="structure"` skips Trimesh reopening and labels it skipped. These checks
  do not certify full glTF conformance, VR comfort, or gameplay quality.
- `overwrite=false` rejects existing output. `overwrite=true` can replace a ZIP file or
  an Scissors bundle directory. Directory replacement refuses undeclared files so
  personal additions are retained. Non-bundle directories are never replaced.

All dependency files are copied before export. Captured bytes receive content hashes.
The manifest contains a `scene_revision` hash of canonical source Scene JSON, a
`snapshot_hash` of that scene and captured texture IDs/byte hashes/sizes, export settings,
coordinate conventions, per-variant counts and object mappings, marker positions,
camera metadata, actual checks, and relative file paths with sizes and SHA256 hashes.
The manifest excludes itself from its own file table; `manifest_sha256` covers its bytes.
GLBs apply the existing Z-up to Y-up root conversion once. Numeric units are retained;
the manifest and README disclose the source units and lack of unit rescaling.

To edit a moved or extracted package, open its directory as a new Scissors workspace,
then call `scene.load(path="scene.json")`. Texture references are relative to the package
root. The package does not contain workspace state, plugins, or unrelated files.

Limits cover 20,000 source objects, 1,024 texture dependencies, 4,096 generated files,
snapshot memory, geometry work, decoded images, preview pixels, aggregate output bytes,
and elapsed time. Aggregate file bytes and ZIP bytes must each fit `max_file_bytes`.
Native export/reopen/render calls are not forcibly interrupted; time is checked between
steps and before publication. Links and Windows junctions are rejected in source
dependencies and output paths. ZIP entries are generated relative paths; entry bytes
are checked against the captured file hashes before publication.

Output is staged beside the destination on the same filesystem. Preparation failure
retains existing output. ZIP replacement uses one atomic file rename. Directory
replacement first moves the old bundle to recovery storage and restores it if the final
rename fails. This is not a crash-recovery transaction. If restoration also fails,
`FILESYSTEM_ERROR` reports `recovery_path` and retains that staging directory.
Owned staging cleanup checks containment before removing files.

The result returns the published `path`, file list, `size_bytes`, checks, source hashes,
and `manifest_sha256`. For directories, `manifest_path` is an absolute file path.
For ZIPs, it is the archive entry `manifest.json` with `manifest_in_archive=true`;
`package_sha256` hashes the ZIP itself. Invalid artifacts use `ARTIFACT_INVALID`,
existing outputs use `ALREADY_EXISTS`, and normal resource/path/filesystem errors retain
their structured codes.

### Vector text geometry

`mesh.create_text(scene_id, text, size=1, depth=0.1, font="Arial", segments=8)` extrudes
font contours into a real mesh. Glyph holes are retained. Overlapping filled contours union
before extrusion. It uses the existing VTK FreeType outline reader and Manifold backend,
without a bitmap image, display server or added dependency.

Built-in Arial, Courier and Times use VTK's embedded faces. Their supported input is ASCII
plus newlines. bold and italic select built-in styles. For accented or other Unicode glyphs,
provide a workspace-relative TTF/OTF path. Requested glyph IDs must exist in a Unicode cmap
format 4, 12 or 13. Malformed/missing glyphs fail instead of producing a replacement box.
Custom font files choose their own style; bold/italic flags are rejected for those files.
Font collections, complex script shaping, combining marks after NFC normalization and
right-to-left layout are unsupported. Tabs expand to four spaces. Whitespace-only text fails.

Size is nominal font em-height in scene units. Actual ink bounds depend on the text and
font. Depth is positive along the initial Z axis. segments samples each quadratic/cubic curve;
more samples cost geometry. line_spacing controls multiple lines. capped=false keeps only
extruded walls. axis, pivot, name and material_id follow other native figures.
Planar UV is generated in font-size units. Angle-based normals keep caps hard and curves
smooth. Results include contour count. Font file paths stay relative in metadata and their
SHA-256 records the source bytes. Geometry depends on the chosen font and backend versions.
mesh.figures includes the text family, and short Python calls/figure tables also support it.

Atomic batches and Python transactions allow filesystem.read alongside scene permissions.
This supports font files and checkpoint reads while rejecting filesystem.write and plugin
lifecycle permissions. A failed native text row restores all table/transaction scene changes.
Font parsing and curve sampling run in the timed geometry worker. File/path/geometry limits
apply; parsing is failure containment rather than a full Windows OS memory sandbox.

Outline code grouping follows the [VTK FreeType implementation](https://raw.githubusercontent.com/Kitware/VTK/v9.5.2/Rendering/FreeType/vtkFreeTypeTools.cxx).

### Workspace binary persistence

Workspace format 2 uses a `state.json` manifest plus private `.geometry` files.
Each mesh reference has a relative NPZ path, array checksum and exact dtype/shape descriptors.
The checksum covers canonical numeric arrays and descriptors, not ZIP container bytes.
Vertices/normals/UV use little-endian float64; faces use int64; vertex colors use uint8.
Empty hierarchy nodes remain inline metadata.

Successful mutations publish changed geometry before atomically replacing the manifest.
Content-derived names let unchanged arrays skip compression and file rewriting. Equal
geometry can share files across independent objects. Hashing still inspects geometry.
This reduces persistence I/O, not live arrays or per-operation rollback snapshots.
No performance measurements have been run.

The reader checks members, sizes, numeric dtypes, shapes and checksums before installing
scene state. Object arrays, pickle, unexpected members, missing files and invalid references
fail. Decode preflight includes temporary model memory; large workspaces may need a higher
memory limit than the old JSON format. `.geometry` is reserved from public artifact APIs.
Symlinks cannot redirect writes outside that private directory.

Format 1 remains readable. Opening alone does not migrate it. The next successful mutation
writes format 2. Older engines that only support format 1 cannot read the new manifest.
Automatic discovery of a new plugin is also a startup mutation and can trigger migration.
scene.save, named checkpoints and in-memory snapshots keep their existing JSON/model format
and stable IDs. Move the full workspace, including geometry and image files, to relocate it.
Old geometry files remain. A late failure can leave an unreferenced file; there is no automatic
garbage collection. Files flush and rename atomically; POSIX directory sync is best effort.
The manifest is the final root pointer, not an OS-wide multi-file transaction.

### Existing-solid bevel, chamfer and fillet

`mesh.bevel(object_id, width=0.01, segments=1)` treats an existing closed positive solid.
`mesh.chamfer(object_id, width=0.01)` selects the planar treatment.
`mesh.fillet(object_id, radius=0.01, segments=8)` selects a sampled spherical treatment.
All three use the same native registry, worker, resource checks and rollback contract.
They work on closed meshes, including prisms and concave panels, rather than only boxes.
Open surfaces and inconsistent winding are rejected.

Without `selection`, these use global rolling-kernel operations.
`mode="convex"` erodes then dilates the solid (morphological opening).
`mode="concave"` dilates then erodes it (closing); `mode="both"` applies opening then closing.
Opening stays inside the source solid; closing contains it. Erosion uses the reflected
kernel for Manifold's subtraction convention, including asymmetric face-normal kernels.
Chamfer uses the convex hull of source unit face normals scaled by width as its kernel.
Width is the kernel extent, not a fixed setback along every edge. Non-right-angle faces
therefore have different setbacks. Fillet uses a geodesic sphere sampled at `4*segments`.
It approximates a circular radius; it does not provide exact CAD tangency or an edge graph.

`preserve_topology=true` rejects changed component counts, Euler characteristic or boundaries.
Small features can shrink or disappear even if that signature remains unchanged. Widths that
consume the whole solid are rejected. Inspect tight corners and thin walls before delivery.
Each native stage checks geometry counts and the face-product work budget. Native work runs
under the geometry worker's process limits. Attribute projection also has a pair/time budget.

In global mode, `preserve_uv=true` projects source UV to the nearest original triangle. Equal-distance seams
prefer the face whose normal matches the new face. Vertex colors use the same barycentric
projection. Missing UV, or `preserve_uv=false`, uses world planar UV for each output face.
New surfaces can stretch projected textures; unwrap and rebake for final texture quality.
Material, parent, pivot and baked-world transform diagnostics remain attached to the result.
In global mode, normals split at hard chamfer edges and smooth fillet facets up to 60 degrees. Color seams
remain split. Tangent export frames are regenerated from the resulting normals and UV.
`replace=true` retains the object ID; `replace=false` creates a sibling mesh and keeps the
source. Children remain attached to the source. `name` optionally names the result.

#### Selected solid edges

All three operations accept `selection` from `mesh.select_edges` or a saved edge
selection. Consumed fields are `object_id`, `geometry_revision`, and a nonempty unique
`edge_indices` list. Stale, foreign, empty, duplicate or out-of-range selections fail
with `INVALID_PARAMETER`. Select geometric creases; coplanar triangulation diagonals
are rejected. Both adjacent faces must exist, and the source must be a closed,
consistently wound positive solid.

Selected mode constructs finite prisms along the original selected edges. Convex
edge prisms are subtracted; concave edge prisms are added. `mode` must match every
selected edge; use `mode="both"` for a mix. Convex cuts run before concave additions.
The prisms stop at the edge endpoints. Connected prisms combine through the Boolean
backend; they do not solve a CAD miter or rolling-ball junction. Inspect nearby
features and reduce width when prisms overlap unwanted regions.

For selected `mesh.bevel` and `mesh.chamfer`, width is the perpendicular setback on
each adjacent face. `segments=1` creates a planar band; higher bevel segment counts
sample a circular arc. Selected `mesh.fillet` instead uses the requested circular
radius to calculate the setback from the local dihedral angle. Open panels are not
supported by these solid treatments.

Supported source UV and colors interpolate through the attributed Boolean backend.
New cut faces use world planar UV, and new colors interpolate along edge endpoints.
Missing UV or `preserve_uv=false` generates planar UV. Material, hierarchy and baked
transform diagnostics survive. Normals recompute. No whole-solid nearest-surface
projection is used in selected mode. Old geometry selections become stale.
Face and render vertex indices can change throughout Boolean triangulation; query
the resulting geometry before another selection-based edit.
Results identify `method="selected_edge_prisms"`, `selected_edge_indices`, and
`uv_method`; `cleanup_tolerance=0` indicates no explicit cleanup pass.
The same replacement, topology, worker, comparison, memory and time limits apply.

```python
edges = app.call("mesh.select_edges", object_id=object_id, edge_indices=[edge_index])
app.call("mesh.chamfer", object_id=object_id, selection=edges, width=0.02)
```

#### Local patch reconstruction

`mesh.reconstruct_patch(object_id, selection, refinement=1, iterations=5,
strength=0.5, sharp_angle_degrees=45)` replaces selected face regions with a refined
triangulation and applies constrained Laplacian smoothing. It supports open and
closed meshes. A current face/component selection or saved selection is required.
It does not create a surface across a missing hole; use `mesh.fill_holes` for that.

The selected region's border stays fixed. Edges whose neighboring face normals
differ by at least `sharp_angle_degrees` are protected, including creases touching
the selected region. Their endpoints stay fixed and their edges never subdivide.
Refinement splits unprotected interior edges and adds triangle centers. Shared
midpoints agree across render seams. Each pass produces a new local triangulation.
`refinement` ranges from 1 to 3. `iterations` ranges from 0 to 100; zero refines
without smoothing. `strength` ranges above 0 through 1. The sharp angle ranges
above 0 through 180 degrees.

Smoothing moves only unprotected selected interior positions. Unselected triangles
keep their original face indices, render indices and world positions. Protected
border and crease positions remain exact. Vertices shared with unselected faces
also stay fixed, including point-only contact. Material, transforms and hierarchy survive;
new patch UV and colors interpolate within their original render triangle, retaining
source seam differences. Normals recompute. The method can shrink curved regions;
inspect shape, texture stretching and self-intersections. It rejects degenerate
geometry and children reversed relative to their source triangle.

Results identify `method="constrained_laplacian_refinement"`,
`protected_vertex_indices` in the original render table, `protected_edges` as
representative render pairs, `new_to_old_faces`, and a fresh face `selection`
covering the rebuilt region. Original named selections become stale. Geometry,
working-memory, topology comparison, time and response-byte limits apply.
The operation requires `scene.write`; errors and failed checkpoints restore state.

### Common figure options

`mesh.figures` includes `common_options` for each family. Each entry contains the actual
registered JSON Schema for supported `sides`, `segments`, `capped`, `axis`, `pivot` and
`name` parameters. Every native family supports `axis`, `pivot` and `name`.

Axis selects the axial direction, or the surface normal for planar figures.
Placement happens before rotation. Center placement centers the bounding box at zero.
Base placement moves the minimum axial coordinate to zero and keeps transverse coordinates.
Origin placement, available for point-defined and composite figures, retains the input origin.
This option places new vertices relative to zero. Use `mesh.pivot` or `mesh.set_origin` to
move an existing object's pivot.

| Family | Default placement | Cap control |
| --- | --- | --- |
| Cube, cylinder | Center; Z axis | Removes both axial end faces |
| Cone | Base; Z axis | Removes the base disk |
| Sphere | Center; Z axis | `capped=false` removes triangles at both axial poles |
| Plane | Center; Z normal | Intrinsically planar; no end caps |
| Profile, curve | Input origin and input plane | Planar input; extrusion controls caps |
| Polygon, star/cross/arrow | Input origin and XY plane | Controls positive-thickness extrusion ends |
| Rounded box | Base; Z axis | Removes planar top/bottom faces; retains side bevels |
| Tube | Input origin and path coordinates | `capped` aliases `caps` on an open path |
| Louver, switch grid | Original geometry origin; Z axis | Composite closed parts; no end-cap switch |
| Prism, pyramid, dome, hemisphere, plate, wedge, gear, spring, text | Base; Z axis | Family-specific ends/base |
| Polyhedron | Center; Z axis | Intrinsically closed; no end caps |
| Capsule | Base; Z axis | `capped=false` opens both rounded axial poles |
| Torus | Center; Z axis | Controls partial-arc ends; closed loops have no ends |

For profiles, curves and polygons, omitted `axis` retains `plane`. Explicit axis rotates its
positive normal toward X/Y/Z. A polygon with zero thickness rejects `capped=false` because
removing its only filled face would leave no mesh. The same rule applies to planar stars.
Sphere and capsule cap switches remove the triangles touching each local Z extreme before
axis placement. They create two pole openings; they do not remove planar disks. The opening
size depends on mesh resolution. A resolution that leaves no surface is rejected.

Existing primitive defaults remain compatible. Cylinder and cone accept `segments` as an alias
for circumferential `sections`; a different nondefault `sections` value is rejected. Tube treats
`capped` the same way relative to `caps`. Aliases can override legacy defaults.
Sphere keeps its default icosphere and `subdivisions`. Optional `segments` selects a latitude/
longitude sphere; the backend rounds counts to even and doubles longitude count. Choose either
segments or nondefault subdivisions. Resolution budgets are checked before allocation.

### Connected and floating parts

`scene.collisions` also returns `connected_components` and `isolated_object_ids` in selection
order. An edge in this graph means surface contact within tolerance or positive closed-solid
overlap. Hierarchy alone does not establish spatial attachment. Empty groups and markers
cannot be collision operands or anchors.

Provide `anchor_object_ids` as a nonempty unique subset of the selected meshes to classify
floating parts. `floating_object_ids` contains every selected mesh that has no contact path
to an anchor. Several anchors can support separate assemblies. Without anchors that field is
null: the report does not guess which disconnected component is the intended support.
An isolated anchor is supported by definition. An isolated unanchored mesh is floating.
Contact is a geometric connection, not proof of a physical joint, strength or gravitational
stability. Open meshes only contribute surface contact. Existing collision fields and pair
budgets remain unchanged. The query is read-only and uses the existing intersection service.

### FBX, COLLADA and USDZ delivery

`scene.export` and `scene.split_export` also accept `format="fbx"`, `"dae"` and `"usdz"`.
Python helpers `app.export.fbx`, `.dae` and `.usdz` forward the same selection, hierarchy,
root name, affine export transform, material consolidation and LOD options. Output extensions
must match the format. These native writers do not require Blender, Autodesk SDK, Assimp,
OpenUSD or a new optional feature installation.

| Format | Scene data | Material/shading contract |
| --- | --- | --- |
| FBX | Binary 7.4; shared geometry, named hierarchy, vertex normals, UV and RGBA | Phong approximation, diffuse/emissive/normal images, custom metallic/roughness and other image paths |
| DAE | COLLADA 1.4.1 XML; geometry instances, hierarchy, affine matrices, normals, UV and RGBA | Phong approximation; base/emission textures; other PBR images retained through SCISSORS extras |
| USDZ | USDA root layer plus PNG images; uncompressed ZIP with each payload aligned to 64 bytes | USD Preview Surface with base/normal/metallic/roughness/emissive/occlusion maps, alpha and double-sided flags |

FBX materials write shininess twice: `ShininessExponent` for modern readers and
`Shininess` for older ones, with the same value. This matches the property pair that
the Autodesk FBX SDK writes.

Static FBX exports use right-handed Y-up coordinates. Scene `(x, y, z)` becomes
FBX `(x, z, -y)`. The writer converts mesh vertices, normals and local node transforms
to that basis. DAE and USDZ retain scene Z-up coordinates. Static FBX declares centimeters
per scene unit in its metadata. Retained FBX documents keep their original axes and units.
See [rig retention](fbx-rig.md). Importers choose whether to honor the declarations.
FBX uses RSrs matrix inheritance and applies the shared export graph once.
A local shear is factored into two TRS nodes; the extra node has an `_Affine` name. DAE and
USD store full local matrices. USD uses row-vector matrices, so the writer transposes the
internal column-vector matrix in its layer text.

Keep every returned `files` entry with FBX and DAE. Texture files have a sanitized stem and
content hash. USDZ includes its assets and has `defaultLayer.usda` as the first member.
It uses ASCII USDA, not USDC. This follows the OpenUSD package format; Apple consumers
that require a binary USDC layer may reject it. Apple Quick Look compatibility is unverified.
USD currently repeats mesh arrays for instances. It preserves vertex-color primvars, but
textured USD materials do not multiply those colors into surface shading. Material-only
vertex colors use primvar readers. FBX/DAE vertex-color and normal-map interpretation vary
by importer. DAE COMMON has no standard metallic/roughness shader or normal-map slot.
The writer stores those source images as extras; it does not claim native PBR rendering.

FBX/DAE tint base and emissive images in linear color space before PNG encoding.
Neutral factors reuse the source image. Non-neutral factors process bounded pixel
blocks without reducing resolution. A per-export cache reuses encoded images with
the same source pixels and effective factors, including equivalent RGB and RGBA
factors. Source images, output images, temporary buffers and encoded assets remain
subject to the memory budget. An image that cannot fit still fails explicitly.
USD keeps
the images and applies factors in shader nodes. Source texture files remain unchanged.
Geometry, images, serialized bytes, hierarchy depth and elapsed time have resource limits.
The static writers do not create scripts, rigging or animation.
The separate retained-FBX path preserves source rig and animation data. Static writers use fixed authoring timestamps for repeatable
output; retained documents keep source authoring timestamps. Files publish through the same atomic writer;
a late filesystem error can still leave earlier sidecars or the primary file on disk.

External consumer compatibility is unverified. Open exported files in the intended
application before delivery.

Format references: [COLLADA 1.4.1](https://www.khronos.org/files/collada_spec_1_4.pdf),
[OpenUSD USDZ](https://openusd.org/release/spec_usdz.html),
[USD Preview Surface](https://openusd.org/release/spec_usdpreviewsurface.html),
[FBX binary layout](https://code.blender.org/2013/08/fbx-binary-file-format-specification/),
and [Autodesk transform inheritance](https://help.autodesk.com/cloudhelp/2018/ENU/FBX-Developer-Help/cpp_ref/_transformations_2main_8cxx-example.html).


## Geometry selection and wall inspection

A selection is an explicit set of mesh elements bound to `object_id` and
`geometry_revision`. Geometry edits invalidate old selections. Queries use world
coordinates because object transforms are already baked into vertices.

`mesh.select_vertices(object_id, vertex_indices=null, region=null, tolerance=1e-6)`
selects render vertices. Coincident copies at UV or normal seams remain separate.
An omitted index list selects all candidates; an empty list selects none.

`mesh.select_edges(object_id, edge_indices=null, region=null, boundary_only=false,
tolerance=1e-6)` selects exact-position topology edges. Its `edges` array gives each
selected edge's representative render endpoint pair. The `edge_indices` address
all topology edges, ordered lexicographically by their welded vertex pairs.
Welded vertices are ordered lexicographically by position; each representative is
the first render vertex at that position. Indices always refer to the current
geometry revision. `boundary_only=true` keeps edges used by exactly one face.

`mesh.select_boundaries(object_id, loop_indices=null, region=null, tolerance=1e-6)`
selects whole closed boundary loops. A boundary loop is a closed sequence of edges
bordering an open surface. Its `loops` entries and `loop_indices` match
`mesh.boundaries`; malformed boundaries raise the same errors. Select one loop
before building a `mesh.bridge` input with that loop's `loop_index`.

`mesh.select_components(object_id, component_indices=null, seed_face_indices=null,
region=null, tolerance=1e-6)` selects whole components. A component contains faces
connected through shared exact-position edges. UV seams do not split components;
point contact does not connect them. Components are ordered by their lowest face
index. A seed face chooses its entire component. When several filters are supplied,
all must match. The result contains both `component_indices` and `face_indices`.

All four queries accept an optional `region` with `bounds: [[xmin,ymin,zmin],
[xmax,ymax,zmax]]` and `rule: "fully_inside" | "centroid_inside" | "intersects"`.
Tolerance expands the box; it does not weld nearby positions. Vertex rules all
test point containment. Edge centroid means midpoint; loop centroid means the
mean of its vertices; component centroid is weighted by triangle area.
Intersection tests use actual segments for edges and loops, and triangle surfaces
for components. An interior box that misses a boundary does not select its loop.
Explicit indices and box predicates combine with AND. Duplicate or out-of-range
indices fail with `INVALID_PARAMETER`. Queries can fail with `RESOURCE_LIMIT` or
`OPERATION_TIMEOUT` when their work or result exceeds configured limits.

Results include `kind`, primary indices, representative `vertex_indices`, `count`,
`empty`, and world `bounds` (`null` for empty results). Count measures elements of
the selected kind. Query operations are read-only and require `scene.read`.

### Named selections

`mesh.selection_save(name, selection, overwrite=false)` validates and stores a
selection on its mesh. It accepts complete query results, including existing
`mesh.select_faces` results. Face query results without `kind` use `"faces"`.
Only the kind's primary index list is consumed; derived indices are recomputed.
The response contains `name` and the canonical `selection`.

`mesh.selection_get(object_id, name)` returns that canonical selection directly.
`mesh.selection_list(object_id)` returns names, kinds, counts, stored revisions
and `stale` status. `mesh.selection_delete(object_id, name)` removes an entry,
including a stale entry. Save and delete require `scene.write`; get and list
require `scene.read`. Names contain 1ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Å“128 characters and must include a non-space
character. Existing names require `overwrite=true`.

Selections persist in workspace state and scene snapshots. Geometry edits do not
remap saved indices: get rejects a stale selection with `INVALID_PARAMETER`.
List remains available so agents can find and replace stale entries. Empty
selections can be stored. Each mesh permits at most 128 names; serialized storage
must fit both `max_file_bytes` and one quarter of `max_memory_bytes`.
Failures and atomic batches restore selection metadata with the rest of scene state.

```python
selected = app.call("mesh.select_components", object_id=object_id, seed_face_indices=[0])
app.call("mesh.selection_save", name="Body panel", selection=selected)
panel = app.call("mesh.selection_get", object_id=object_id, name="Body panel")
```

### Editing selected faces

Local face edits accept `object_id` and `selection`. The selection contains
`object_id`, `geometry_revision`, and a nonempty unique `face_indices` list.
Use `mesh.select_faces`, `mesh.select_components`, or a stored face/component
selection. An empty selection, another object, stale revision, or invalid index
raises `INVALID_PARAMETER`. All edits run through the shared registry and require
`scene.write`. Invalid results and failed checkpoints restore the entire scene.

`mesh.move_faces(object_id, selection, offset, detach=true)` translates selected
faces by a nonzero world XYZ vector. With `detach=true`, render vertices shared
with unselected faces are duplicated first. Only selected face positions change;
gaps and open boundaries may result. With `detach=false`, every render vertex at
a selected exact position moves, including copies across UV seams. Neighboring
unselected faces can deform because they share those positions.

`mesh.delete_faces(object_id, selection, empty_policy="error")` removes selected
triangles and unused render vertices. Deleting every face requires
`empty_policy="delete_object"`; the object is removed and its children are
reparented to its parent. Other openings remain uncapped.

`mesh.separate_faces(object_id, selection, name=null, keep_source=false)` extracts selected
triangles to a new mesh. The new mesh retains the source's material, UV, colors,
parent, visibility and world geometry. Its transform is identity because source
coordinates are already baked. By default, selected faces are removed from the
source. An empty source is deleted. `keep_source=true` retains the source unchanged.
Named selections remain attached to the original object; they are not copied.

`mesh.extrude_faces(object_id, selection, offset)` replaces selected faces with
translated caps and adds walls around their boundary contours. Offset is a nonzero
world XYZ vector, shared by every selected face. Each selected component must have
an unbranched, consistently wound manifold boundary. Closed selected components
are rejected; use `mesh.move_faces` to translate them. UV seams do not create
internal walls. Interior diagonals of a selected patch do not create walls.
Outer and inner contours both receive walls. Existing unselected triangles stay
at their original positions. Open surfaces remain open at their original border;
extruding a patch on a closed solid can keep that solid closed.
Cap UV and colors are copied. Each boundary edge gets a separate unit UV rectangle
on its wall; wall colors copy the corresponding endpoints. Inspect stretching and
self-intersections. Offset alone does not guarantee intersection-free geometry.

`mesh.flip(object_id, selection=null)` reverses selected triangle vertex order and
recomputes normals. Omit the selection to reverse the whole mesh. Partial reversal
can create inconsistent winding where selected faces meet their neighbors.
It does not automatically repair orientation.

Local edits preserve material references and remap UV and vertex colors through
vertex compaction or duplication. Normals recompute. Construction-specific topology
metadata is removed. Source named selections and thickness certificates keep their
original revisions/signatures; geometry changes invalidate them.
Results include `source_object_id`, `source_geometry_revision`, `source_deleted`,
`edited_face_count`, `side_face_count`, `new_to_old_vertices`, and
`new_to_old_faces`. New wall faces map to `-1`; repeated vertex origins identify
attribute copies. When the result exists, its summary and a fresh face `selection`
are returned. For extrusion that selection addresses the moved caps. For deletion
it is empty. Separation also returns the remaining `source` summary with its index
maps, or `null` when the source was deleted, and `copied` status.
Mesh-size, working-memory, timeout and response-size limits apply.

```python
top = app.call("mesh.select_faces", object_id=object_id,
               normal={"direction": [0, 0, 1], "angular_tolerance_degrees": 1})
raised = app.call("mesh.extrude_faces", object_id=object_id,
                  selection=top, offset=[0, 0, 0.2])
app.call("mesh.move_faces", object_id=object_id, selection=raised["selection"],
         offset=[0, 0, 0.1], detach=False)
```

### UV and PBR transfer between surfaces

`uv.copy_from` copies UV between meshes with matching indexed topology. Use
`mesh.transfer_uv` when the source and repaired target have different triangles.
Keep a separate textured source object before rebuilding a surface.

`mesh.transfer_uv(object_id, source_object_id, max_distance, selection=null,
source_selection=null, material_policy="source", transfer_colors=true,
min_normal_dot=0)` projects source UV onto target face corners. Source UV is required.
Optional target and source selections are current face/component selections.
Omitting a selection uses all faces. The objects must be distinct; their vertices
already contain world transforms. No diagnostic transform matrix is applied again.
Align both objects in the same numerical coordinate space; scene unit labels are not converted.

Each corner uses the nearest source triangle whose geometric normal dot product
with the target face normal meets `min_normal_dot` (from -1 through 1).
`max_distance` is a required nonnegative world distance, with a small floating-point
allowance. Unmatched corners fail with `GEOMETRY_ERROR`. Source face index breaks
ties after normal alignment. Selected target render corners split so unselected UV
and colors stay unchanged. Unused render vertices compact; face indices and world
triangle positions stay fixed. The result gives `new_to_old_vertices`, maximum
measured distance, transferred face count and a fresh face `selection`.

`material_policy="source"` assigns the source material and its five PBR map
references. Materials in the same scene are shared; cross-scene materials are cloned
into the target scene. A partial transfer requires matching source/target materials;
otherwise use `material_policy="target"` to keep the current material, or bake maps.
Optional colors use source barycentric interpolation. Shading normals, material
properties, hierarchy and transforms survive. Normal-mapped output requires a valid
tangent basis. UV that collapses selected triangles is rejected.
Corner projection can stretch across source UV islands inside a coarse target face;
use per-texel baking for such seams. This operation writes scene state only and
works in atomic batches and Python transactions.

#### Baking PBR maps onto target UV

`texture.transfer(object_id, source_object_id, max_distance, selection=null,
source_selection=null, resolution=256, channels=null, padding=2, wrap="repeat",
min_normal_dot=0)` samples the source at target UV texel centers. Both objects need
UV and assigned materials. It uses the same bounded correspondence as UV transfer.
The source object, materials and texture files remain unchanged.

Target UV must lie inside `[0,1]`, have nondegenerate triangles, and have no overlapping
interior texel samples. Every selected face must own at least one bake sample;
otherwise increase resolution or reduce mesh density. Shared-edge samples belong
to the first target face. Overlap checks work at the requested raster resolution;
they are not an analytic UV-overlap certificate. Source UV can tile with
`wrap="repeat"`, or use edge clamping with `wrap="clamp"`.

`channels=null` transfers all supported maps: `base_color`, `normal`,
`metallic_roughness`, `emissive` and `occlusion`. An explicit list must be nonempty
and unique. Resolution ranges from 16 to 4096, within pixel/memory/work budgets.
Padding from 0 to 16 extends selected colors into unused atlas texels; it does not
overwrite texels owned by unselected faces.

The operation clones the target material. For each transferred channel it creates
a managed PNG and incorporates material factors into the image, then sets the new
factor to neutral. Base color and emissive RGB filter and multiply in linear color
space and encode back to sRGB. Alpha, metallic/roughness and occlusion remain linear.
Metallic uses B and roughness G. Normal vectors transform through the source tangent
basis into world space, then into the target tangent basis, including mirrored UV.
Normal baking requires valid unit shading normals and nondegenerate tangent frames;
split mirrored seams before baking. The tangent basis is Scissors's angle-weighted
UV derivative basis; it is not MikkTSpace.

Unselected texels retain the target's effective channel values, subject to output
resolution, filtering and 8-bit quantization. Untransferred channels retain their
original target maps and factors. Vertex-color modulation and lighting are not
baked. Target world geometry, UV, normals and hierarchy stay unchanged except that
unused render vertices compact. Shared target materials are not edited. Retained
texture files are never overwritten. Inspect texel density, seams and gutters.

Results include new texture artifacts by channel, painted pixel count, maximum
measured distance, vertex index mapping and a fresh face selection. New textures
persist with the workspace and export as ordinary PBR maps. Selections become stale
if vertex compaction changes the geometry revision; material-only baking keeps it.

The operation requires `scene.write` and `filesystem.write`, so atomic batches and
Python transactions reject it. Failure restores scene state and removes maps owned
by the failed transfer, including checkpoint or enclosing native call failure.
Cleanup failures appear in structured error details. Geometry, pixel, memory,
comparison, raster-work, time and byte limits apply to both transfer workflows.

```python
patch = app.call("mesh.fill_holes", object_id=target_id, selection=opening)
app.call("texture.transfer", object_id=target_id, source_object_id=textured_source_id,
         selection=patch["selection"], max_distance=0.02, resolution=128)
```

### Topology repair

`mesh.repair_topology(object_id, voxel_size, mode="solid", shell_thickness=null)`
reconstructs an existing mesh. It replaces geometry while keeping the object ID,
material, hierarchy, visibility, pivot and diagnostic transform. Coordinates are
already in world space; the recorded transform is not applied again.

`mesh.repair_topology_data(scene_id, vertices, faces, voxel_size, mode="solid",
shell_thickness=null, name="Repaired mesh")` accepts a damaged triangle soup and
creates only the repaired mesh. Vertices are finite triples. Faces are triples of
nonnegative integer vertex indices. This entry point can receive non-manifold
geometry that `mesh.create` and normal scene validation reject. It does not weaken
scene invariants. Exact geometric duplicate triangles and degenerate triangles are
removed before sampling. No source attributes or materials are supplied by this entry point.

Both operations use a uniform grid with explicit spacing in scene units:

- `solid` extracts the region where the absolute generalized winding number exceeds
  0.5. Consistently oriented overlapping shells form their occupied union. Inward
  nested shells can retain cavities. Opposite overlapping orientations can cancel;
  repair winding first when necessary. Open surfaces have no reliable solid interior.
- `shell` extracts an unsigned-distance envelope around all input triangles. It
  requires `shell_thickness >= 3 * voxel_size`. The requested thickness spans both
  sides of each surface. Open, crossing or non-manifold panels become a closed thick
  envelope. Nearby sheets can merge. This is a sampled offset, not exact thickness
  certification or recovery of the original solid interior.

Reconstruction changes triangle topology and shape. Small details, openings and gaps
near the grid spacing can disappear. There is no exact surface deviation guarantee.
UV and vertex colors are cleared and normals recomputed. Keep a separate textured
source when UV or PBR transfer is needed. Existing named selections become stale.

Before publication, output must pass closed topology, winding, positive total volume,
duplicate/degenerate face checks, single-fan vertex links and nonadjacent triangle
intersection checks. As in `mesh.self_intersect`, faces sharing a vertex are excluded
from intersection pairs. Results include `validation`, `grid_samples`,
`removed_input_faces`, resolution, mode and warnings. Empty interiors, boundary
clipping and invalid output fail with `GEOMETRY_ERROR`. An empty interior includes a
hint to refine the grid or use shell mode.

Input/output geometry, grid memory, file size and worker timeout limits apply.
Solid sampling budgets `grid_samples * cleaned_input_faces` against
`max_geometry_pairs`. Output verification uses a sorted bounding-box broad phase,
also bounded by that comparison budget and `operation_timeout`. A limit produces an
error instead of publishing unchecked output. Both operations require `scene.write`
and support atomic batches and Python transactions. Failure restores scene state.
They use the included NumPy/VTK backends without extra dependencies.

```python
repaired = app.call("mesh.repair_topology", object_id=object_id,
                    voxel_size=0.01, mode="solid")
panel = app.call("mesh.repair_topology_data", scene_id=scene_id,
                 vertices=damaged_vertices, faces=damaged_faces,
                 voxel_size=0.01, mode="shell", shell_thickness=0.04)
```

`mesh.remesh` retains its closed, oriented input requirement. Use topology repair
when reconstruction must accept damaged topology or resolve intersecting surfaces.

### Winding repair

Winding is the vertex order of a triangle. Two neighboring triangles must traverse
their shared edge in opposite directions for consistent winding. Recomputing normal
vectors alone does not change this order.

`mesh.repair_winding(object_id, selection=null, orientation="preserve", dry_run=false)`
solves these shared-edge constraints. Omit `selection` to inspect the whole mesh.
Pass a current `mesh.select_faces` or `mesh.select_components` result to limit
editable faces. Stored face/component selections also work. Outside faces remain
unchanged and fix the orientation required at the selected border.
An empty, foreign, invalid or stale selection raises `INVALID_PARAMETER`.

If fixed neighbors impose conflicting requirements, repair fails with
`GEOMETRY_ERROR`; expand the selection to include the conflicting region.
Non-orientable surfaces with contradictory edge constraints also fail.
The operation requires nondegenerate manifold edges. It does not resolve
self-intersections or non-manifold topology.

`orientation="preserve"` keeps the majority orientation in each selected region
that has no fixed neighbor. It chooses the smaller set of face reversals. A tie
keeps the lowest selected face unchanged. Consistent inward components remain
inward, including cavity walls. Open components can be made consistent, but
consistency alone cannot determine their intended exterior.

`orientation="outward"` or `"inward"` requires each selected region to be a complete
closed component. After making edge directions consistent, the operation chooses
positive or negative component signed volume respectively. Near-zero signed volume
is rejected as ambiguous. Volume evaluation uses a local origin and normalized
coordinates. These modes do not infer cavity nesting: explicitly making a cavity
wall outward changes its material orientation. They do not certify that a component
is free of self-intersections.

Vertex positions, render vertex order, UV, colors, material, transforms, hierarchy,
object IDs and face indices stay fixed. Only triangle vertex order changes.
Normals recompute when faces change. Older geometry selections and thickness
certificates then become stale. Construction-specific topology metadata is cleared.
If no reversal is needed, geometry and its revision remain unchanged.
Use `mesh.flip` for explicit face reversals.

Results include `flipped_face_indices`, `flipped_face_count`, `planned_flip_face_indices`,
`planned_flip_count`, `changed`, and a fresh `selection` covering the inspected faces.
`regions` lists inspected face indices, `anchored` and `closed` status, planned flip
counts, and planned normalized signed volume when absolute orientation is requested.
`scope_conflicts_before` and `scope_conflicts_after` count inconsistent edge joins
touching selected faces. `conflicts_before` and `global_conflicts_after` include
unselected regions, whose defects may remain. The `planned_scope_conflicts_after`
and `planned_global_conflicts_after` fields describe the plan.

With `dry_run=true`, actual flip counts are zero, actual conflict counts and
geometry remain unchanged, and planned counts describe the proposed repair.
The operation requires `scene.write` and supports atomic batches. Geometry,
working-memory, comparison, time and response-byte limits apply. Failures restore
scene state; a failed local repair never expands its selection automatically.

```python
component = app.call("mesh.select_components", object_id=object_id, seed_face_indices=[0])
plan = app.call("mesh.repair_winding", object_id=object_id, selection=component, dry_run=True)
fixed = app.call("mesh.repair_winding", object_id=object_id, selection=component)
```

### Face selection and wall inspection

`mesh.select_faces(object_id, normal=None, region=None, tolerance=1e-6)` is read-only.
A normal predicate uses `direction` (unit XYZ) and `angular_tolerance_degrees`.
A region uses `bounds` (two XYZ vectors) and an explicit `rule`:
`centroid_inside`, `fully_inside`, or `intersects`. Predicates combine with AND.
Results include `object_id`, `geometry_revision`, `face_indices`, `count`, bounds and predicates.
The triangle-box intersection rule uses a separating-axis test.

`mesh.shell(..., opening=selection)` consumes that selection to remove exterior faces
and join the outer and inner wall surfaces around the opening.
The source must be a closed outward volume when an opening is supplied.
A stale revision, another object, empty indices or invalid indices is rejected.
The registry restores the source if construction fails.

`mesh.validate(object_id, require_closed=false, require_connected=false,
check_self_intersections=false, include_selections=false)` reports mesh invariants.
Connectedness counts surface components joined by
exact-position edges. Point contact does not connect two surfaces.
A sealed cavity may have separate inner and outer surface components.
The report does not equate surface components with material connectivity.
Requested intersection checks must finish; resource and timeout errors use normal envelopes.
The report includes component counts, signed volumes, duplicate and non-manifold counts,
winding, boundary counts and intersection statuses.

#### Repair selections from validation

With `include_selections=true`, validation adds `selection_status`, `selections`,
`selection_statuses`, and `components`. Normal validation calls and internal state
checks do not generate these arrays. The operation remains read-only.
Each selection includes `object_id`, `geometry_revision`, `kind`, primary element
indices, `count`, `empty`, bounds, and a `preview` hint. Save it with
`mesh.selection_save`, pass its face indices to compatible repair operations, or
pass it to `scene.preview(highlights=[...])`. Query selections again after geometry changes.

| Selection | Kind and meaning |
| --- | --- |
| `boundary_edges` | Exact-position topology edges with one incident face. |
| `non_manifold_edges` | Topology edges with more than two incident faces. |
| `duplicate_faces` | Extra copies of each exact-position triangle, ignoring winding; retains the lowest face index. |
| `degenerate_faces` | Faces with area at most `1e-14`. |
| `winding_edges` | Two-face edges traversed in the same direction by both faces. |
| `inconsistent_winding` | Faces incident to those inconsistent edges. |
| `disconnected_components` | All faces when more than one surface component exists. |
| `nonpositive_volume` | All faces when the welded mesh is closed with nonpositive signed volume. |
| `incorrect_normals` | Vertices with missing, nonfinite, nonunit or inconsistent normals, following validation's normal policy. |
| `unused_vertices` | Render vertices referenced by no face. |
| `invalid_uv` | Invalid UV entries; all vertices if the UV array shape is wrong. Present when UV exists. |
| `uv_outside_unit_square` | Vertices with UV outside `[0,1]`; present for a correctly shaped UV array. |
| `invalid_vertex_colors` | Invalid color entries; all vertices if shape/type is wrong. Present when colors exist. |
| `self_intersections` | Faces from a completed requested intersection query. |

Edge selections include representative render endpoint pairs and incident
`face_indices`. `components` contains a face selection for each surface component.
These are repair targets and structural observations; open borders, multiple surfaces,
unused vertices or tiled UV can be intentional. Their presence does not replace
`errors`, `warnings`, `valid` or the caller's requested invariants.

Intersection selections are omitted when the query was not requested or could not
complete. Check `selection_statuses.self_intersections`; an omitted selection does
not prove absence of intersections. A requested query that cannot complete leaves
`selection_status="partial"` while retaining the other available selections.
Invalid base geometry arrays return
`selection_status="unavailable"`, an empty selection map and an explanatory reason.
Groups and markers return `not_applicable`. Geometry-index, memory, comparison,
time and response-byte limits apply. Diagnostics do not bypass scene validation
rules for subsequent writes.

#### Highlighting selections

`scene.preview` accepts `highlights`, a list of at most 64 current face, edge,
vertex, boundary or component selections. Face selections without `kind` are accepted.
The renderer uses each kind's primary indices and recomputes derived data. Objects
must belong to the scene, be visible, and pass the preview's object filters.
Stale, foreign, invalid or filtered selections fail before rendering the output.

Highlights draw orange polygons, lines or vertex markers over the color image.
The layer uses the same world camera in VTK and Pillow. It is a diagnostic x-ray
overlay: surfaces do not occlude selected elements. Camera near/far and viewport
clipping apply. Section views test each highlighted element's centroid, matching
the whole-element section policy. Faces hidden by a section do not draw highlights.
Only `render_pass="color"` accepts nonempty highlights; quantitative depth and normal
passes remain unchanged. The overlay does not edit materials, geometry or visibility.

The result reports `highlight_mode="xray_overlay"` and per-selection `highlights`
with kind, requested count and drawn primitive count. Clipped elements may draw
no primitive. Image, geometry, memory, pixel-work and time limits apply.
`scene.preview` retains its filesystem-write permission and atomic-batch restrictions.

```python
report = app.call("mesh.validate", object_id=object_id, include_selections=True)
edges = report["selections"]["boundary_edges"]
app.call("scene.preview", scene_id=scene_id, output="previews/boundary.png",
         highlights=[edges])
```

`mesh.check_thickness(object_id, minimum, tolerance, selection=null, rim_selection=null)`
is read-only and requires positive `minimum` and `tolerance`, in scene units.
It measures the infimum of material-interior chords along each source triangle's
inward geometric normal. A chord stops at the first boundary exit. This is a
definition for the actual planar triangles, not the thickness of an ideal smooth
surface or a measurement in every possible direction.

Omit `selection` to inspect all faces. A current face/component selection limits the
source faces; all triangles remain exit candidates. Named face selections also work.
`rim_selection` marks opening rims or panel end caps explicitly. Rim faces are not
sources, and source regions whose first exit hits a rim are excluded from the measured
domain. Results report these regions and their area in `excluded_rim_exit_regions`.
They do not certify the excluded areas. Without explicit rims, a current shell rim
certificate supplies the rim map. A stale map gives `inconclusive`; provide a current
rim selection or rebuild the shell. An empty current `rim_selection.face_indices`
explicitly declares no rim exclusions. Empty source selections, stale selections
and foreign selections are rejected.

The mesh must have closed, consistently oriented, nonintersecting manifold boundaries.
Nested boundary shells must alternate outward/inward orientation. The tool checks the
whole volume even when source faces are selected. Invalid or unverified geometry is
`inconclusive`. Open surfaces do not define material-interior thickness.

For general meshes, the tool partitions each source triangle into regions with one
first exit triangle. Ray coverage, depth ordering, clipping and extrema use exact
rational arithmetic on the stored floating-point coordinates. Chord depth is affine
within each region. Its minimum occurs on the region boundary, so narrow thin regions
between sample locations are included. Exact squared lengths are enclosed by rounded
floating-point bounds. Face edges count through interior limits; a sharp wedge can
therefore have zero minimum. Zero-area tangent domains do not count. Mark actual rims
explicitly rather than assuming they have the same wall thickness as the panel skin.

Results include `status`, `scope`, `samples`, `violations`, `unresolved_regions`,
`coverage`, and `achieved_error_bounds`. General-method `samples` are whole-face-domain
minima with witness locations, opposing face IDs, lower/upper bounds and error bounds;
they are not a finite sampling certificate. `coverage.complete` refers to the selected
domain after the reported rim exclusions. `measured_area` and `excluded_exit_area`
describe that scope. Displayed areas and locations are rounded; thickness bounds use
exact squared-length comparisons. An unchanged rectangular miter shell can use its
conservative analytical plane bounds instead.
That analytical path reports `certified_faces`; area fields are null because it does
not compute a triangle partition or excluded-exit area.

`pass` requires complete coverage, an achieved bound width no larger than `tolerance`,
and a global lower bound at least `minimum`. `fail` requires a demonstrated upper
bound below `minimum`; a proved violation can fail even if other faces remain unresolved.
A threshold inside the bound interval is `inconclusive`. No incomplete check produces
a pass. Memory, comparison, timeout, rational-size, partition and output limits apply.
The general method allows at most 4096 face minima and 4096 active cells, and budgets
triangle tests and cell updates against `max_geometry_pairs`. Limit failures are
reported in unresolved regions. Large meshes can need a source selection or higher
operator-configured budgets. No new geometry or texture files are created.

```python
result = app.call("mesh.check_thickness", object_id=panel_id,
                  minimum=0.02, tolerance=1e-6,
                  selection=skin_faces, rim_selection=end_caps)
if result["status"] == "pass":
    lower = result["achieved_error_bounds"]["global_lower"]
```
# Coordinated cuts

`scene.cut_volume` subtracts an inline world-space box from several independent
closed volumes. It expands groups and deduplicates targets. It retains object IDs,
names, parents, source UV coordinates, vertex colors, and interpolated normals.
The box is parameter data. It never becomes a scene object.

```python
result = app.call(
    "scene.cut_volume",
    scene_id=scene_id,
    target_ids=[body_id, frame_id, fasteners_id],
    volume={"type": "box", "min": [-2.75, -0.90, 0.79], "max": [-1.12, 0.90, 2.08]},
    dry_run=False,
)
```

Only `operation="difference"` and `cut_uv="planar"` are supported. Cut UV coordinates
use world units divided by positive `uv_scale` (default 1). Existing face attributes
are interpolated where triangles are split. New surfaces use `cut_material_id`, or
the target's original material when omitted.

A distinct cut material retains the target ID as a group with material parts.
Further cuts resolve those parts as one closed volume. Selecting a generated part
also selects that logical volume. Part IDs can change on later cuts; use the stable
root ID. Unrelated child objects retain their world geometry and parent root.

`dry_run=True` computes a plan without changing scene state or geometry revisions.
Complete removal fails by default. Set `empty_policy="delete_object"` to allow it.
Deletion fails if unrelated descendants would be removed or detached.
All targets roll back on failure. Empty targets never remain as invalid meshes.

Results include `changed_ids`, `unchanged_ids`, `deleted_ids`, per-target counts,
attribute policies, prior and new material part IDs, and opening contour metadata.
Contours describe boundaries of new cut surfaces. They do not identify an inner or
outer rim automatically. Ambiguous boundaries are reported. Dry-run contours are
previews and cannot serve as revision-bound selections.

The call accepts up to 128 input IDs and expanded logical targets. Aggregate input
corner count and output vertex count use `max_vertices`; aggregate face counts use
`max_faces`. Working memory, worker files, and total backend time also use workspace
limits. Inputs must be closed oriented volumes, including hollow walls and separate
closed components. Unsupported volume types and UV policies fail explicitly.

## Opening frames

`mesh.frame_opening` creates a separate frame along an identified opening.
It keeps the source body unchanged. It uses the shared tube ring-connection code.
No transport contains geometry logic, and no additional dependency is needed.

Three typed `opening` forms are supported:

- `cut`: use the `geometry_revision` returned by `scene.cut_volume` and an explicit
  `contour_index` when several contours exist. The engine reads the stored cut
  contours. A dry run does not create a stored selection.
- `rim_faces`: provide a current `geometry_revision`, selected `face_indices`,
  and a `contour_index` when needed. For example, use the indices returned by
  `mesh.select_faces`. The selected rim can belong to a closed hollow wall with
  no mesh boundary edges. Face indices address a mesh, not a material group.
- `points`: provide a current `geometry_revision`, ordered world-space `points`,
  and `closed` (default true). These points express the caller's intended path.
  They are not automatically checked for contact with the source surface.

All forms reject stale geometry revisions before creating an object. Cut references
also work on the stable material group returned by a cut with multiple materials.
The latest cut contours persist across workspace restarts. Older workspaces without
stored cut contours can use rim faces or explicit points.

```python
cut_target = cut_result["targets"][0]
frame = app.call(
    "mesh.frame_opening",
    object_id=cut_target["object_id"],
    opening={
        "type": "cut",
        "geometry_revision": cut_target["geometry_revision"],
        "contour_index": 0,
    },
    section={"type": "circle", "radius": 0.019, "sides": 12},
    name="Front opening frame",
)
```

Select `contour_side="inner"` or `"outer"` instead of an index only when there are
exactly two corresponding rim contours. Supply `normal` directed from inside to
outside. For parallel rim faces, their projections must match. For coplanar loops,
they must be disjoint and nested. Ambiguous or mismatched pairs fail explicitly.
An explicit contour index remains available when semantic side selection is unsuitable.

Sections are `circle` with positive `radius` and `sides` (4-64, a multiple of four),
or `rectangle` with positive `width` and `depth`. In a planar miter frame, width is
across the path in its plane. Depth is along `normal`. Circle dimensions are its
diameter. Circular sections are faceted, with vertices on the requested radius.

`joint_policy="miter"` (default) requires a planar path. The operation fits a plane
when possible. Its normal sign is deterministic. Supply `normal` to choose the sign
explicitly, or to define the plane of a straight open path. Closed loops use the
right-hand winding around that normal. Collinear triangulation points are removed.
Corners share one connected section and are stretched to maintain edge thickness.
`miter_limit` bounds the corner stretch (default 4).

`placement="centered"` follows the selected contour and requires zero `clearance`.
For closed planar paths, `inside` and `outside` place the nearest lateral section
edge at the requested nonnegative clearance from the contour's straight spans.
Their centerline shift is half the section width plus that clearance.
Signed `offset` translates along the normalized plane normal in meters.
Clearance describes the contour's plane. It does not prove clearance from every
surface of the source body. The result includes the resolved path, centerline,
normal, dimensions, and numerical tolerance for inspection.

`joint_policy="transport"` supports spatial paths with the existing parallel
transport and loop seam correction. Sections are measured in transported ring
planes. Placement must be centered and lateral clearance must be zero.
A nonzero offset requires an explicit world-space `normal` direction.
The corner sharpness is still bounded by `miter_limit`.

Closed contours join the seam and require `end_policy="auto"`. Open paths use
closed caps with `auto` or `cap`. `end_policy="open"` deliberately leaves their
ends open and reports that the mesh is not watertight.
`material_id` and `parent_id` must belong to the source scene. The default parent
is the source's parent, so the frame joins the same assembly as a sibling.
Geometry stays in baked world coordinates; the source diagnostic transform is not
applied a second time. No UV coordinates are generated by this operation.

The call validates paths, sections, planar envelopes, mesh topology, and bounded
non-adjacent triangle intersections before publishing the frame. Adjacent faces
are excluded from the intersection query. Source contact and VR visibility are
not checked. Invalid paths, collapsed offsets, sharp corners, stale selections,
and failed required checks leave no new object in the scene.

Limits include 512 resolved corners, 4096 total input contour points, section
resolution, geometry counts, working memory, pair count, and operation time.
By default a query limit or timeout fails the operation. Explicitly setting
`allow_incomplete_checks=True` permits an unfinished non-adjacent surface query.
Its result remains `uncompleted` and carries a warning. Path and topology checks
are still required. An incomplete check is never reported as passed.

## Sampled player visibility

`scene.visibility_report` is a native read-only query. It uses a NumPy triangle
BVH (a hierarchy of bounding boxes) to find the nearest surface hit on each finite
ray. It does not create previews, write files, checkpoint state, or change geometry.
Python, REST, and MCP use the same registry operation.

```python
parameters = {
    "scene_id": scene_id,
    "eyes": [{"name": "left", "position": [0.5, -0.032, 1.72]},
             {"name": "right", "position": [0.5, 0.032, 1.72]}],
    "forward": [-1, 0, 0],
    "up": [0, 0, 1],
    "horizontal_range": [-40, 40],
    "vertical_range": [-25, 20],
    "sampling": {"type": "steps", "horizontal": 5, "vertical": 5},
    "max_distance": 5,
    "detail": "samples",
}
before = app.call("scene.visibility_report", **parameters)
# Modify the scene through normal modeling operations.
after = app.call("scene.visibility_report", **parameters, baseline=before)
```

Eyes have unique names and world-space positions in meters. Optional named
`head_offsets` are world-space offsets added to each eye. The operation evaluates
every eye/head combination and names it `eye@head`. If offsets are omitted, it
uses a zero offset named `neutral`. An explicit list replaces that default.
Names contain letters, digits, underscores, dots, or hyphens and start with a
letter or digit. Up to 16 eyes and 16 offsets are accepted, with at most 32
combinations and 32768 total ray samples.

`forward` defaults to -X and `up` to +Z. Both must be nonzero and nonparallel.
The query normalizes forward and projects up to an orthogonal viewing frame.
Positive horizontal angles turn toward `cross(forward, up)`. Positive vertical
angles turn toward the corrected up direction. Directions use spherical yaw and
elevation, rather than a rectangular perspective image projection.

Horizontal bounds must be ordered within [-180, 180] degrees. Vertical bounds
must be ordered within [-90, 90]. Their defaults are [-45, 45] and [-30, 30].
Sampling defaults to 5-degree steps on both axes. Step sampling starts at each
lower bound and advances without going beyond the upper bound. It only includes
the upper bound when the step reaches it within numerical rounding.
`sampling={"type": "counts", "horizontal": 17, "vertical": 10}` instead samples
uniformly between the endpoints. A count of one uses the range midpoint.
A zero-width range requires one count. Each axis is limited to 1024 samples.

`near` defaults to 0.001 m and `max_distance` to 100 m. They define the inclusive
ray segment measured from the actual eye, with 0 <= near < max_distance.
All hits are double-sided. An eye inside a closed object can see its exit surface.
Geometry uses baked world vertices; the diagnostic transform is not applied twice.

`include_ids=None` considers all meshes. An empty list considers none.
Include and exclude filters expand groups and deduplicate descendants. Exclusions
win. Unknown IDs and IDs from another scene fail explicitly. Markers and groups
themselves have no surface. Hidden objects and descendants of hidden ancestors
are skipped by default. Set `include_hidden=True` to include them.

The supported `obstruction_policy` is `geometric_surfaces`. Alpha values, textures,
material names, and material backface settings do not remove a surface. Use explicit
object exclusions for a different geometric inspection. The operation does not
simulate light transmission or textured transparency.

Each eye reports clear, blocked, and unresolved counts, coverage fractions, blocking
object counts, and horizontal spans of consecutive clear samples for every vertical
row. If both zero angles are sampled and the central ray is clear, it also reports
the clear horizontal span around that ray at zero elevation. Otherwise it states
why that central span is unavailable. Fractions describe grid samples, not a
solid-angle integral. Spans join sampled endpoints and do not certify unsampled
directions or a headset's field of view.

`detail="samples"` adds each sample's angles, world direction, status, nearest
object ID, render face index, and hit distance from the eye. Summary output omits
that sample list. Both forms report unresolved reason counts.
Coplanar and near-parallel contacts can be conservatively unresolved. A requested
distance tolerance below the estimated numeric resolution is also unresolved.
The default world-space `tolerance` is 1e-9 m.

The query limits aggregate triangle count, working memory, BVH construction time,
ray-triangle checks, node checks, and serialized result size. Triangle work uses
`max_geometry_pairs`; node checks are limited to twice that value. Input or BVH
preparation limits fail with structured errors. A limit reached while tracing
returns an `uncompleted` report and marks pending samples unresolved. It never
turns pending work into a clear result. Reduce samples or use summary output when
the report would exceed the result size limit.

Reports include the exact resolved configuration, a SHA-256 configuration
fingerprint, and a content-based `scene_revision`. That revision covers object
geometry revisions, IDs, hierarchy, and hidden flags. It is not the registry's
catalog counter and does not track material edits ignored by this geometric policy.

Supply a previous full report as `baseline` to obtain per-eye clear, blocked, and
unresolved deltas. The scene ID and measurement configuration must match. The
operation checks the baseline fingerprint, eye names, and count totals. Detail
level can change because it does not change the measurement. A comparison with
unresolved samples is marked `partial`. Baseline results are caller-supplied data;
the engine does not claim to authenticate a historical report.

## Resize to final dimensions

`mesh.resize` sets the final world-axis extents of a mesh or group subtree around
one fixed anchor. It measures baked world geometry and applies one delta through
the shared engine transform. The recorded cumulative transform is not applied to
the vertices again. No additional dependency is required.

```python
result = app.call(
    "mesh.resize",
    object_id=pedestal_id,
    dimensions={"z": 0.29},
    anchor="min_z",
    aspect_policy="independent",
)
```

This request keeps the pedestal's base plane fixed. A pedestal with a 0.48 m
height and base at Z = 0.30 m ends with a 0.29 m height and top at Z = 0.59 m.
The caller does not need to calculate a scale factor or a compensating translation.

`dimensions` accepts positive finite `x`, `y`, and `z` extents in meters. At least
one field must be non-null. `axes` only accepts `world`. The operation does not
infer a local basis from the diagnostic transform.

With `aspect_policy="independent"` (default), unspecified or null axes retain
their extents. With `aspect_policy="uniform"`, one scale factor applies to all
axes. Several requested dimensions must imply the same ratio within a relative
tolerance of 1e-9. Omitted axes then scale proportionally. A specified axis with
zero source extent fails; resizing does not add thickness to a planar mesh.
An omitted zero-extent axis can remain zero under a valid uniform resize.

The default `anchor="center"` keeps the measured bounding-box center fixed.
`min_x`, `max_x`, `min_y`, `max_y`, `min_z`, and `max_z` keep that world bounds
plane in place. The resolved point is the bounds center with the chosen coordinate
set to its minimum or maximum. Points within the plane can move along the plane
when its other dimensions change.
`anchor={"type": "point", "position": [x, y, z]}` instead keeps an explicit
world-space point fixed, including a point outside the object.
The anchor does not replace the object's stored pivot.

Bounds include every mesh in the target subtree, including hidden meshes.
Markers and empty groups do not contribute to those bounds. The root can be a
mesh or group, and mesh roots include their mesh descendants in the measurement.
Every descendant, including markers and nested groups, receives the common delta
exactly once. A marker's position moves with the assembly. A marker root, or a
group without any mesh geometry, cannot be resized.

Object IDs, names, parent links, hidden flags, material references, UV coordinates,
vertex colors, and face indexing remain stable under this positive scaling.
Normals update for the new geometry. Split normals retain their method and use
the inverse linear transform before normalization. Geometry revision references
become stale when the object changes. An exact identity resize leaves the scene
data and geometry revisions unchanged.

The result reports `old_bounds`, `new_bounds`, old and new dimensions, resolved
`anchor`, `scale_factors`, `delta_matrix`, `changed_ids`, `unchanged_ids`, and
`bounds_mesh_ids`. The bounds describe the whole measured subtree, rather than
the empty pivot bounds of a group. Numerical tolerance and dimension relative
tolerance are included. The engine checks actual output bounds against the
expected bounds and requested dimensions before committing.

The call is limited to 4096 affected objects, aggregate `max_vertices` and
`max_faces`, working memory, and computation time. Invalid dimensions, inconsistent
uniform ratios, singular or nonfinite scales, insufficient coordinate precision,
or invalid output geometry fail with structured errors. Positive target dimensions
can still fail if their output faces become degenerate. The registry restores
the full scene on failure, including failures after some descendants were transformed.
The operation also participates in normal scene transactions and atomic batches.

Shared transforms apply finite deltas directly to baked vertices and marker or
explicit pivot positions. Small changes are not discarded by an identity tolerance.
Reflections preserve outward winding. Descendant traversal uses a parent lookup
while retaining its stable traversal order and cycle detection.

## Remove whole components from a mesh

`mesh.delete_components` removes complete face components selected by a world-space
box. A component consists of faces connected through shared edges after exact-position
welding for topology analysis. UV and normal seam duplicates do not split a component.
Point contact does not connect two components. Nearby positions are never welded.
Stored render vertices remain separate, including their seams.

```python
parameters = {
    "object_id": merged_fasteners_id,
    "region": {"type": "box", "bounds": [[-0.6, -0.6, -0.6], [0.6, 0.6, 0.6]]},
    "selection_rule": "fully_inside",
}
plan = app.call("mesh.delete_components", **parameters, dry_run=True)
result = app.call("mesh.delete_components", **parameters)
```

The root must be a mesh, not a group or marker. The query uses baked world vertices;
it does not apply the diagnostic transform again. A box has ordered minimum and
maximum `bounds`. Zero-width axes are supported. `tolerance` defaults to 1e-9 m
and expands the box in every direction. Boundaries are inclusive. Tolerance affects
region selection only; it does not affect exact topology welding.

Selection rules are:

- `fully_inside` (default): every referenced vertex of the component is inside or
  on the expanded box. A component's exact bounds provide this equivalent test.
- `intersects`: some triangle surface touches or crosses the expanded box. Bounds
  overlap only identifies candidates; it is not a positive intersection result.
  A box entirely inside a closed piece without touching its surface does not select
  it with this rule. The operation does not infer a filled solid from a face component.
- `centroid_inside`: the area-weighted surface centroid is inside or on the expanded
  box. The centroid is not the vertex average or the bounding-box center.

The operation always removes the whole selected component, including faces outside
the box. It never clips triangles. A new call reevaluates the current geometry.
Component indices are deterministic by first source face and are bound to the
reported source geometry revision. They are not persistent part IDs.

`dry_run=True` computes selection, prospective counts, and index maps without changing
scene data. The selected descriptors match an applying call when the source and
parameters are unchanged. If all components are selected with `empty_policy="error"`
(the default), the plan returns `allowed=false` and `planned_action="reject_empty"`.
An applying call then raises `GEOMETRY_ERROR` without changing the scene.

Set `empty_policy="delete_object"` explicitly to allow complete removal. The mesh is
deleted rather than left with invalid empty geometry. Its direct children retain
their world geometry and are reparented to the deleted mesh's parent, as with normal
object deletion. The result reports those IDs and planned parent links.
If the deleted mesh is a material part of a cut-volume group, the parent's part
references are updated and old cut contours are invalidated. An empty material group
remains a valid ordinary group. The operation does not claim that other open material
parts still form a closed volume after a deliberate surface removal.

For a nonempty result, object ID, name, parent, material, hidden flag, pivot, and
diagnostic transform remain unchanged. Surviving vertices retain their exact positions,
UV, colors, and normals. At a shared render vertex, normals are preserved even when
removing a point-touching component changes its smooth shading neighborhood. The
result warns about this case; recalculate normals separately if desired.
Missing source normals are generated for the surviving geometry and reported.

Faces keep their source order. Render vertices are compacted in source index order.
Unused vertices are removed when geometry changes. A missed region is an exact no-op,
including existing unreferenced vertices and geometry revisions.
Changed geometry invalidates old revision-bound face selections. Construction-specific
`boundary_rings` and `center_pairs` metadata are cleared instead of retaining stale
indices. The result lists the invalidated metadata keys.

Results contain selected component indices, source face indices, bounds, face and
vertex counts, area, and surface centroid. `before`, `planned_after`, and `after`
separate the original state, plan, and actual state after the call. `performed_action`
is `none` for a dry run. `geometry_revision` remains the source revision during a
dry run and is null after deleting the object.

`index_maps` describes the planned geometry in both dry runs and applying calls:

- `old_to_new_vertices` and `old_to_new_faces` use -1 for removed indices.
- `new_to_old_vertices` and `new_to_old_faces` identify the retained source entries.

Whole deletion returns empty new-to-old maps and only -1 in old-to-new maps.
The implementation bounds component count (8192), geometry, working memory,
triangle-box work, computation time, and serialized result size. It reuses shared
connectivity and separating-axis geometry without optional graph dependencies.
Result-size and geometry checks run before publishing the replacement mesh.
Errors roll back scene state through the registry. Scene transactions and atomic
batches use the same implementation. No Boolean cutter or temporary scene object
is needed.

## Review sheets with player cameras

`scene.render_sheet` accepts orbit views and explicit cameras. Its default six
orbit views, angle-only view form, `size`, column layout, and `_view_N.png` tile
filenames remain supported. It uses the same camera preparation and renderer as
`scene.preview`; it does not implement a separate rasterizer.

```python
sheet = app.call(
    "scene.render_sheet",
    scene_id=scene_id,
    output="previews/player_views.png",
    views=[
        {"name": "Exterior", "azimuth_degrees": 35, "elevation_degrees": 25},
        {"type": "camera", "name": "Low head", "position": [0.5, 0, 1.62],
         "target": [-2, 0, 1.62], "up": [0, 0, 1], "fov": 95},
    ],
    view_sets=[
        {"name": "Player", "position": [0.5, 0, 1.72], "target": [-2, 0, 1.72],
         "up": [0, 0, 1], "stereo": True, "eye_separation": 0.064, "fov": 95},
    ],
)
```

This request yields exterior, low-head, center, left, and right views in one call.
Orbit views accept `type="orbit"` or omit the type. Their angle defaults are 35
degrees for azimuth and elevation, matching the angle-only request form.
Explicit views use `type="camera"`, `position`, `target`, and `up` in world
coordinates. Type can also be inferred from position and target. Up defaults to
+Z and must not be parallel to the view. A top-down explicit camera therefore
needs a suitable up vector. Orbit fields mixed with explicit camera fields fail
validation rather than being ignored.

Explicit cameras default to perspective unless a per-view or sheet-wide projection
is supplied. Perspective `fov` is vertical degrees before zoom, defaulting to 45.
Explicit orthographic views require positive `orthographic_scale`, which specifies
the vertical world span in meters before zoom. They reject an explicit `fov`.
Orbit views default to orthographic, including the six-view default sheet.
`near` defaults to 0.001 m. Optional `far` must exceed near; otherwise it is fitted
by the shared preview camera code.

Each view can set width and height (32-2048 pixels), projection, zoom, offsets,
wireframe, renderer, texture sampling, background, ambient light, light strength,
and light direction. Width and height default to the sheet's `size` (64-2048,
default 256). Per-view settings override their sheet-wide defaults where available.
The sheet uses a common cell size based on the largest width and height and centers
smaller images without resizing them. Headers use 24 pixels. Display labels are
shortened to fit; full names remain in metadata. Sheet transparency is shared by
all views. Only color previews are included in sheets.

View sets have a unique identifier `name`, an explicit base camera, and named
`head_offsets`. Offsets are world-space translations of both position and target.
The default offset is a zero translation named `neutral`. An explicit list replaces
that default. `include_center` defaults true. `stereo=true` adds left and right
views with an `eye_separation` in meters, defaulting to 0.064. The right vector is
derived from the viewing direction and up. Both position and target receive each
eye offset, so the two directions remain parallel. They do not point at a shared
near target. `include_center=false` can emit only the stereo pair. A non-stereo set
requires its center and rejects eye separation. Names identify sets and offsets;
they are not used as output paths. These are symmetric parallel cameras, not a
simulation of headset runtime projection matrices.

Results include the sheet path, dimensions, columns, rows, renderer(s), and a
`views` list. Each entry reports its PNG path, full name, display label, dimensions,
backend, effective position/target/up, near/far, and camera parameters. Perspective
`effective_fov` accounts for zoom; it is null for orthographic views. Returned
`orthographic_scale` is the effective vertical span after zoom and is null for
perspective views. `preview_parameters` can be passed to `scene.preview` with the
same scene to reproduce the tile. View-set entries also identify the head and eye.

`scene.preview` accepts the same optional `orthographic_scale` parameter, with the
same world-span meaning. It requires orthographic projection. It also returns
camera up, requested FOV, effective FOV, and effective orthographic span. Camera
diagnostics distinguish explicit world cameras from orbit cameras.

The expanded sheet is limited to 24 views. Combined tile and sheet pixels share
`max_texture_pixels`. Geometry instances, working memory, aggregate output bytes,
result metadata, and elapsed computation time are bounded. The time limit is checked
between preview calls and before publication; it does not preempt a native driver
call. Output and tile paths use the normal workspace and reserved-path protections.
Object selection follows `scene.preview`, including its visible-object and explicit
ID filter semantics.

Every camera and the aggregate image budget are checked before rendering.
Tiles and sheet are staged in an owned temporary directory. Final files are only
published after all images and metadata pass their checks. Publication uses atomic
file replacement and restores touched prior files on ordinary write failure. If
restoration fails, `FILESYSTEM_ERROR` identifies the unrestored paths. This is not
a filesystem-wide atomic transaction or a crash-recovery journal. Existing tiles
outside the returned view set are retained. The operation declares filesystem write
permission and cannot run inside an atomic scene batch or scene transaction.
Scene geometry remains unchanged.
