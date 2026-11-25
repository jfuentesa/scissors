# Modeling workflows

## Textured cube through MCP

Describe unfamiliar operations first. For each row call `operations_invoke` with
`{"name": OPERATION, "arguments": ARGUMENTS}`. Check success and replace placeholders
with the real IDs returned by preceding calls:

| Operation | Arguments | Keep |
| --- | --- | --- |
| `scene.create` | `{"name":"Textured cube"}` | `result.id` as SCENE_ID |
| `mesh.create_cube` | `{"scene_id":"SCENE_ID","size":2}` | `result.id` as OBJECT_ID |
| `material.create` | `{"scene_id":"SCENE_ID","name":"Checker"}` | `result.id` as MATERIAL_ID |
| `texture.generate_checker` | `{"width":256,"height":256,"cells":8}` | `result.id` as TEXTURE_ID |
| `uv.generate` | `{"object_id":"OBJECT_ID","method":"auto"}` | validation |
| `texture.assign` | `{"material_id":"MATERIAL_ID","texture_id":"TEXTURE_ID"}` | assignment |
| `material.assign` | `{"object_id":"OBJECT_ID","material_id":"MATERIAL_ID"}` | assignment |
| `mesh.validate` | `{"object_id":"OBJECT_ID","require_closed":true}` | `result.valid` and diagnostics |
| `mesh.mirror` | `{"object_id":"OBJECT_ID","axis":"x","plane":0,"name":"Right part"}` | new `result.id`, source kept |
| `scene.preview` | `{"scene_id":"SCENE_ID","output":"previews/cube.png"}` | artifact |
| `scene.export` | `{"scene_id":"SCENE_ID","output":"exports/cube.glb","format":"glb"}` | artifact |
| `scene.save` | `{"scene_id":"SCENE_ID","output":"scenes/cube.json"}` | snapshot |

A successful validation call can return `valid=false`; resolve geometry errors before
claiming a valid solid. Verify files when server filesystem access is available.

## Equivalent local Python workflow

Use an interpreter with Scissors installed and a workspace not owned by another process.

```python
from pathlib import Path

from scissors import Scissors

with Scissors("model-workspace") as app:
    scene = app.call("scene.create", name="Textured cube")
    cube = app.call("mesh.create_cube", scene_id=scene["id"], size=2)
    material = app.call("material.create", scene_id=scene["id"], name="Checker")
    texture = app.call("texture.generate_checker", width=256, height=256, cells=8)
    app.call("uv.generate", object_id=cube["id"])
    app.call("texture.assign", material_id=material["id"], texture_id=texture["id"])
    app.call("material.assign", object_id=cube["id"], material_id=material["id"])
    validation = app.call("mesh.validate", object_id=cube["id"], require_closed=True)
    assert validation["valid"], validation
    app.call("scene.preview", scene_id=scene["id"], output="previews/cube.png")
    artifact = app.call("scene.export", scene_id=scene["id"], output="exports/cube.glb")
    app.call("scene.save", scene_id=scene["id"], output="scenes/cube.json")
    assert Path(artifact["path"]).stat().st_size == artifact["size_bytes"]

# Independent reopening when trimesh is available in this environment:
import trimesh

reopened = trimesh.load(artifact["path"], force="scene")
assert reopened.geometry
assert any(mesh.visual.kind == "texture" for mesh in reopened.geometry.values())
```

## Batching

Operation batching accepts:

```json
{"name":"operations.batch","arguments":{"atomic":true,"operations":[
  {"operation":"mesh.translate","arguments":{"object_id":"OBJECT_ID","x":1}},
  {"operation":"mesh.rotate","arguments":{"object_id":"OBJECT_ID","axis":"z","angle_degrees":45}}
]}}
```

Atomic batches allow scene reads/writes and enabled geometry plugins, up to 100 calls.
They reject exports, preview generation and plugin lifecycle changes, because filesystem
artifacts and code registration are not part of a scene transaction. No nested batches.
With `atomic=false`, successful scene changes remain when another operation fails.
Returned IDs must be supplied explicitly; batch steps do not interpolate prior results.

Delete helper objects in one `mesh.delete` call with `object_ids`. Each call snapshots,
validates and rewrites the whole workspace state, so deleting 60 objects one by one can
take a minute on a dense scene while one batch takes about a second. A batch validates
every ID first, runs in one rollback point and re-parents children.

UV generation should follow topology changes. `auto` uses planar UV for planes,
spherical UV for spheres, cylindrical UV with planar caps for cylinders/cones, and
box projection otherwise. Seams split render vertices; topology validation welds
identical positions for diagnostics. Cylindrical/spherical seam U may slightly exceed
one (repeat addressing), which is reported as a warning. Box UV overlaps; use the included
xatlas for a packed atlas. Smooth deformations keep UV attached to vertices.

Use GLB for a self-contained textured asset. OBJ is a material approximation; STL
contains geometry only. glTF creates multiple files; give it a dedicated export folder.
glTF and GLB export the Z-up scene as Y-up, the glTF convention, and name nodes after the
objects, so Y-up engines such as Unity or Godot load the model upright; OBJ and STL keep
scene Z-up coordinates. Scene snapshots refer to textures within their workspace; move the
whole workspace
to preserve those assets.

`scene.preview` renders a PNG with VTK offscreen or, when no OpenGL context exists, with a
Pillow painter; the result reports the backend in `renderer`. Orbit cameras keep world +Z
as screen up. Explicit position/target/up cameras can roll. `azimuth_degrees` 0 looks along -Y, 90 along +X, 180 along +Y,
270 along -X; `elevation_degrees` 90 looks straight down (where -Y becomes screen up) and
-90 straight up.
`zoom` and `offset_x`/`offset_y` frame the subject. Use `clip_axis`, `clip_position` and
`clip_keep` for an axis-aligned section; the plane is tested in world coordinates and hidden
triangles do not change framing. `only_object_ids` and `exclude_object_ids` narrow the render,
which matters because orthographic drawing paints the nearest surface on top: an interior view
usually needs the shell or the glass excluded. `sample_textures` samples base-colour textures
so labels and screen pages are readable, without alpha blending. Read the returned
`diagnostics` to confirm the camera, section and filters actually used.
`mesh.mirror` reflects a part across an axis-aligned plane and reverses face winding;
`duplicate=true` keeps the source object.
For scripted builds with many calls, wrap them in `app.transaction()`: the state file is
written once instead of after every call, and an exception discards the whole block.

## Review renders and geometry before export

For a shared atlas density, describe `uv.generate`, then call it with `object_ids`,
`pixels_per_meter=128`, `texture_resolution=[2048,2048]`, `density_mode="atlas"`
and `padding=4`. Add `preserve_uv=true` to scale existing charts. All selected objects
must be meshes in one scene. The result reports per-object density and anisotropy.
Inspect again with `uv.inspect(object_id=..., texture_resolution=[2048,2048])`.
Use a larger atlas or a deliberately lower target when the shelf pack reports
`ATLAS_CAPACITY`; it never silently reduces density. Repeat mode uses the whole image,
allows overlap, and requires padding=0. Confirm repeat sampling in the target material.

Material batching validates each source part independently and preserves separate
indices at coincident contacts. It is a render optimization, not a solid union.
FBX and DAE preserve image dimensions during bounded tint processing. Keep all returned
PNG sidecars, and reopen the result in the intended consumer before delivery.

Rendered views, the geometry report and the texture gate below catch most problems.
`scene.preview` draws with VTK offscreen or the Pillow painter and reports the backend.
`mesh.validate` reports closure, degenerate faces, winding and normal errors.

```python
from scissors import Scissors

with Scissors("model-workspace") as app:
    scene = app.call("scene.create", name="Bracket")
    part = app.call("mesh.create_cube", scene_id=scene["id"], size=1)
    camera = {
        "scene_id": scene["id"],
        "width": 768,
        "height": 768,
        "projection": "perspective",
        "camera_position": [2.3, -2.6, 1.5],
        "camera_target": [0, 0, 0],
        "fov": 40,
    }

    # 1. Full view: shape, colour and material.
    full = app.call("scene.preview", output="previews/bracket.png", **camera)
    assert full["renderer"] in {"vtk", "pillow"}

    # 2. Section: wall thickness and interior, without editing geometry.
    app.call(
        "scene.preview",
        output="previews/bracket_section.png",
        clip_axis="y",
        clip_position=0,
        clip_keep="negative",
        **camera,
    )

    # 3. Geometry report: closure, winding and normal errors.
    report = app.call("mesh.validate", object_id=part["id"], require_closed=True)
    assert report["valid"], report["errors"]

    app.call("scene.export", scene_id=scene["id"], output="exports/bracket.glb")
```

The same calls over MCP. Tools are generated from the operation registry, so
`scene.preview` is `scene__preview` and accepts the same arguments:

| Tool | Arguments | Keep |
| --- | --- | --- |
| `scene_create` | `{"name":"Bracket"}` | `result.id` as SCENE_ID |
| `mesh__create_cube` | `{"scene_id":"SCENE_ID","size":1}` | `result.id` as OBJECT_ID |
| `scene__preview` | `{"scene_id":"SCENE_ID","output":"previews/bracket.png","width":768,"projection":"perspective","camera_position":[2.3,-2.6,1.5],"camera_target":[0,0,0],"fov":40}` | `result.renderer` |
| `scene__preview` | same plus `{"clip_axis":"y","clip_position":0,"clip_keep":"negative","output":"previews/bracket_section.png"}` | artifact |
| `mesh__validate` | `{"object_id":"OBJECT_ID","require_closed":true}` | `result.valid`, `result.errors` |
| `scene_export` | `{"scene_id":"SCENE_ID","output":"exports/bracket.glb","format":"glb"}` | artifact |

`operations_invoke` with `{"name":"scene.preview","arguments":{...}}` reaches the same
operation when a client prefers the generic dispatcher.

Read the results like this:

- **Full view:** the silhouette shows holes and missing faces. The `diagnostics` line names
  the backend, so a flat image means the Pillow painter ran instead of VTK.
- **Section view:** hidden triangles disappear and framing does not move. An empty interior
  usually means the wall is too thin or the cut missed the part.
- **Geometry report:** `errors` lists hard failures such as `NOT_CLOSED`,
  `DEGENERATE_FACES` or `INDEX_OUT_OF_RANGE`. `warnings` lists open meshes and incorrect
  normals.
- **Depth and normal passes:** `render_pass="depth"` writes camera distance as a 16-bit
  PNG with an NPZ sidecar, and `render_pass="normal"` writes world normals in RGB. Both
  require VTK and reject diagnostic highlights.

Previews are review tools: nothing about the scene changes, and `scene.preview` does not
rewrite `state.json`.

## Texture review gate

Every textured model passes this gate before export. One rendered view does not satisfy it.
The full angle list is mandatory: a front view alone hides seams on the back, stretching
under the base and mirrored text on the far side.

```python
angles = [
    ("front", 0, 0), ("right", 90, 0), ("back", 180, 0), ("left", 270, 0),
    ("top", 0, 89), ("bottom", 0, -89),
]
target = 1024  # pixels per meter agreed for this job
camera = {
    "scene_id": scene["id"],
    "width": 768,
    "height": 768,
    "projection": "perspective",
    "sample_textures": True,
    "zoom": 0.95,
}
for name, azimuth, elevation in angles:
    app.call(
        "scene.preview",
        output=f"previews/texture_{name}.png",
        azimuth_degrees=azimuth,
        elevation_degrees=elevation,
        **camera,
    )

uv = app.call("uv.inspect", object_id=part["id"], texture_resolution=[2048, 2048])
density = uv["density"]
assert density["covered_area_fraction"] > 0.999
assert density["degenerate_uv_triangles"] == 0
assert density["max_anisotropy"] <= 2.0
assert 0.8 * target <= density["min_pixels_per_meter"]
assert density["max_pixels_per_meter"] <= 1.2 * target
```

Read the evidence in this order:

| Criterion | Evidence | Pass condition |
| --- | --- | --- |
| Material and base colour | `material.list`, object material | Every textured object has a material with a base-colour map |
| UV coverage | `uv.inspect` | `covered_area_fraction` is 1 and no degenerate UV triangle remains |
| Chart overlap | `uv.generate` atlas mode | Packing succeeds; a self-overlapping island fails with `UV_OVERLAP` |
| Texel density | `uv.inspect(texture_resolution=...)` | `min`/`max_pixels_per_meter` within 20 percent of the target |
| Stretching | `uv.inspect` | `max_anisotropy` at or below 2.0 unless the job accepts more |
| PBR map set | `material.get` | Every declared map resolves to an existing workspace PNG |
| Visual quality | Six previews with `sample_textures=true` | No visible seam, mirror, blur or wrong scale |

Add one close-up per object and one section view for interiors. Reopen the exported file:
a GLB must embed its base-colour texture, and static FBX/DAE need their PNG sidecars.
When the job gives a different density, anisotropy or resolution limit, use the job value
and record it with the result. Keep the six images and the measured density values with
the delivery so the reviewer can check the same evidence.

## Hollow body with an underside opening

Discover schemas before modeling. Build a closed exterior with profiles and loft.
Keep construction profiles outside the final export selection.

```python
selection = app.call(
    "mesh.select_faces", object_id=body_id,
    normal={"direction": [0, 0, -1], "angular_tolerance_degrees": 1},
)
# Review selection["bounds"] and selection["face_indices"] before opening the body.
app.call("mesh.shell", object_id=body_id, thickness=0.03, offset=-1,
         opening=selection)
validation = app.call("mesh.validate", object_id=body_id, require_closed=True,
                      require_connected=True, check_self_intersections=True)
thickness = app.call("mesh.check_thickness", object_id=body_id,
                     minimum=0.025, tolerance=1e-5)
```

Use a region predicate when the normal filter also selects unwanted downward faces.
Selections bind to one geometry revision. Query again after changing geometry or transforms.
The rim joins the two wall surfaces, so an accessible underside can still be a closed wall volume.
A closed wall volume and a single edge-connected surface are separate checks.
Never accept `inconclusive` thickness as proof of a sufficient wall.
Curved triangulated walls can use exact whole-face normal-chord partitions and global bounds.
Use `selection` to limit source faces and `rim_selection` to mark end caps or opening rims.
The tool excludes source rim faces and regions whose first exit hits a rim. Read the
excluded area and measurement scope before accepting a pass. Sharp corner limits can
have zero thickness. This measures actual triangle geometry, not an ideal smooth wall.
Incomplete geometry, nesting or budget checks remain unresolved. An unchanged rectangular
miter shell can use analytic plane bounds. Geometry edits invalidate its certificate
and rim map; provide a current explicit rim selection or rebuild the shell when needed.
# Cut several closed objects with one box

Discover `scene.cut_volume` before using this workflow. A running service can use
an older catalog than the installed source.

Use `target_ids` for the body and related frames or fasteners. Supply an inline
world-space `volume={"type": "box", "min": [x0, y0, z0], "max": [x1, y1, z1]}`.
Call with `dry_run=True` to inspect changed, unchanged, and deleted targets first.
Then repeat with `dry_run=False`. No temporary cutter object or Boolean cleanup
is needed. Each target is cut independently, and the call is atomic.

Keep the stable target IDs. A different `cut_material_id` can turn a target into
a group of material parts. Later cuts treat that group as one volume. Child part
IDs may change. New cut faces use planar UV coordinates in world units, scaled
by `uv_scale`. Inspect their texture placement.

Complete removal requires `empty_policy="delete_object"`. Opening contours in the
result need an explicit choice; the operation does not infer the intended rim.

## Frame an opening without rebuilding its path manually

Discover `mesh.frame_opening`. After a real `scene.cut_volume` call, use the changed
target's `object_id` and `geometry_revision`. Choose a contour index explicitly:

```python
frame = app.call(
    "mesh.frame_opening",
    object_id=target["object_id"],
    opening={"type": "cut", "geometry_revision": target["geometry_revision"],
             "contour_index": 0},
    section={"type": "circle", "radius": 0.019, "sides": 12},
)
```

If there are several contours, inspect them first. Inner/outer selection needs two
matching contours and an explicit normal from inside to outside. Do not assume
that every edge loop is an opening. A closed hollow wall can have a rim without
any mesh boundary edges. Select its rim faces or use stored cut contours.

For an existing opening, use `type="rim_faces"` with current selected face indices,
or `type="points"` with a current revision and ordered world points. An open arch
uses `closed=False` and closed end caps by default. Choose the intended material
and parent. The default parent is the source body's parent.

Planar frames support circular or rectangular sections and mitered corners.
Use `placement="outside"` with `clearance` to keep the frame outside the selected
outline. `offset` moves along the plane normal. Inspect the resulting centerline
and dimensions. This lateral clearance does not replace a body collision check.
Spatial paths use `joint_policy="transport"`, centered placement, and no lateral
clearance. Generate UV coordinates separately when applying a texture.

The source stays unchanged. Stale references and unsuitable corners fail before
creating an object. Read the returned checks. An explicitly allowed unfinished
intersection check is not proof that the frame is free of intersections.

## Measure the player's view before and after an edit

Discover `scene.visibility_report`. Set named world-space eyes, forward and up,
angular ranges, sampling steps or counts, and near/maximum distances. Use both
eyes when checking a VR cockpit. Optional named head offsets add positions such
as a lower or higher head. Offsets use world meters and apply to every eye.

Capture a report before the edit. After the edit, repeat the same measurement
parameters and pass the first report as `baseline`. The operation checks that
the configuration matches before reporting deltas. Inspect the central horizontal
span when the grid includes zero yaw and zero elevation. It only describes the
clear sampled directions around the forward ray.

Use `detail="samples"` to identify the nearest obstructing object and its distance
for each blocked direction. Use `include_ids` or `exclude_ids` to inspect a region
of the assembly. Exclusions win and groups expand to descendants. Hidden ancestors
hide their descendants unless `include_hidden=True` is supplied.

Treat unresolved samples separately from clear ones. A work limit, a timeout, or
coplanar contact can leave a sample unresolved. Read coverage and reason counts
before comparing improvements. A partial comparison is not a complete visibility
assessment. The query does not mutate the scene or write a preview file.

All geometric surfaces block the query, including objects with transparent
materials. This matches a cockpit with no glass. Geometric visibility samples
do not certify headset FOV, physical comfort, or visibility between grid points.

## Set an assembly's size while keeping its base fixed

Discover `mesh.resize`. Use final dimensions instead of calculating scale factors
and translations manually:

```python
result = app.call("mesh.resize", object_id=pedestal_id,
                  dimensions={"z": 0.29}, anchor="min_z")
```

`min_z` keeps the current base plane fixed in Z-up world coordinates.
The default anchor is the bounds center. Other named world bounds planes or an
explicit `{"type": "point", "position": [x, y, z]}` anchor are also supported.

Independent scaling keeps unspecified axes unchanged. Use
`aspect_policy="uniform"` when omitted axes should scale proportionally.
Several uniform target dimensions must agree on one scale ratio.
Only world-axis extents are supported. A rotated object's bounds are measured
after its existing placement; no diagnostic transform is applied twice.

Group the assembly first when its parts should share one anchor and scale.
Bounds include all mesh descendants, even hidden ones. Markers do not enlarge
those bounds, but their positions move with the assembly. The operation transforms
each descendant once and preserves IDs, hierarchy, materials, UV, and colors.
Inspect the returned bounds, actual dimensions, scale factors, and changed IDs.

Resizing a flat mesh cannot create thickness on its zero-extent axis. Use a
solid modeling operation for that purpose. Invalid dimensions or geometry roll
back the full call. Repeating exact current dimensions leaves scene data unchanged.

## Delete complete pieces already merged into one mesh

Discover `mesh.delete_components`. Use it for fasteners or other disconnected
pieces stored in a single mesh. It follows shared-edge connectivity after exact
position welding for analysis. Render seams remain intact. Pieces that merely
touch at a point, or whose edges are only nearby, remain separate components.

```python
parameters = {
    "object_id": fasteners_id,
    "region": {"bounds": [[-0.6, -0.6, -0.6], [0.6, 0.6, 0.6]]},
    "selection_rule": "fully_inside",
}
plan = app.call("mesh.delete_components", **parameters, dry_run=True)
```

Inspect `selected_components`, `planned_after`, and `allowed`. Then apply the
same request without `dry_run` if the plan matches the intended removal.
`fully_inside` keeps partially selected pieces. `intersects` selects a whole piece
when its triangle surface touches the box. It does not test a filled interior.
`centroid_inside` tests the component's area-weighted surface centroid.

The command removes whole components rather than clipping triangles at the box.
It keeps the mesh ID and surviving attributes and returns vertex and face maps.
Those maps describe the planned output even in a dry run. Component indices are
local to the source revision, so reevaluate after changing the mesh.

Complete removal fails by default. A dry run reports this as `allowed=false`.
Choose `empty_policy="delete_object"` explicitly when deleting the whole object
is intended. Children keep their world positions and move to the object's parent.
No invalid empty mesh is left in the scene. A missed region leaves the mesh unchanged.

Normals at shared render vertices remain unchanged and may need review at point
contacts. Read the returned warnings and use a normal operation separately when
the desired shading requires recalculation.

## Render player, eye, and exterior views together

Discover `scene.render_sheet`. Keep angle-only orbit views for an exterior review.
Use explicit `type="camera"` views with position, target, up, and perspective FOV
for the player. A low-head view can translate both position and target downward.

Use `view_sets` for named head offsets and stereo pairs. Set a base camera,
`stereo=true`, and `eye_separation=0.064` for a 64 mm pair. The center view is included
by default. The helper derives the left/right vector and translates both the eye
and target, keeping their directions parallel. Head offsets use world meters.
These views do not reproduce headset runtime projection matrices.

For orthographic explicit views, set `projection="orthographic"` and a positive
`orthographic_scale` vertical span in world meters. Omit FOV in that mode. Zoom
changes the effective span. Width, height, lighting, textures, and renderer can be
set per view. A sheet retains the full names in metadata and fits display labels
to their cells.

Inspect returned `views` for actual camera metadata and individual PNG paths.
Pass a view's `preview_parameters` to `scene.preview` with the same scene when
checking an individual tile. The color image uses the same backend in both paths.

The operation validates every camera before rendering and stages images before
publishing them. Image, work, and file budgets are bounded. Failures clean staging
and ordinary publication failures restore touched prior files. Scene geometry is
unchanged. Run it outside scene.edit or an atomic scene transaction because it
writes artifacts.


## Keep section corners when lofting

Discover `mesh.loft` before using its options. For profiles whose corners must stay
fixed, use `preserve_vertices=true` and leave `resample=0`. Corresponding rings need
the same number of points. Curves contribute their centerline points. The default
mode resamples by arc length and may move a corner.

Keep the same point order in each section. If starts or winding differ, pass
`correspondence` entries with `object_id`, its current `geometry_revision`, and
`rings`. A ring entry selects `source_ring`, `start_index`, and `reverse`.
A reversal keeps the chosen starting point fixed. Open curves can only start at
an endpoint. Map the outer ring (0) first, then every hole exactly once. Profiles
with holes require an explicit map for every section. Do not guess stale indices.

Example for two one-ring profiles:

```python
result = app.call("mesh.loft", object_ids=[lower_id, upper_id],
    preserve_vertices=True, correspondence=[{
        "object_id": upper_id, "geometry_revision": upper_revision,
        "rings": [{"source_ring": 0, "start_index": 2}],
    }])
```

Read `result["loft"]` for the resolved source indices, output seam map, closure,
and checks. The output revision binds the seam map to that output geometry.
With smoothing, original section i is at layer `4 * i`. A closed spine requires
at least three sections and has no caps. Open curves have no end caps.
Section crossings, inconsistent hole winding, unequal counts, and stale maps fail.
A surface check can report `unresolved` when its bounded work cannot complete;
review its warnings before using the result. The check excludes triangle pairs
sharing exact positions. It does not certify adjacent triangle folds.


## Publish a portable asset package

Discover `scene.export_bundle` and use one request to capture related artifacts.
Choose `package_format="directory"` or `"zip"` and an output path inside the workspace.
ZIP paths end in `.zip`. Keep `verification="reopen"` to check actual exported GLBs.

```python
result = app.call("scene.export_bundle", scene_id=scene_id,
    output_path="exports/asset.zip", package_format="zip",
    variants=[{"name": "editable", "preset": "hierarchy"},
              {"name": "runtime", "preset": "material_batches"}],
    verification="reopen")
```

`hierarchy` retains visible parenting. `material_batches` merges by material and flattens
parenting. Both are GLB presets. Inspect the manifest's source-to-export mapping before
using node IDs in a game. Markers include source and glTF world positions. Numeric units
are retained; apply an import unit scale if the source is not in meters.

Keep `include_scene=true` and `include_textures=true` for editing. To open a relocated
package, extract or move it, use that directory as an Scissors workspace, then call
`scene.load(path="scene.json")`. Relative texture references use that package root.
For a GLB-only package, both options can be false. Embedded GLB textures remain included.

Pass `preview_views` for named orbit or explicit cameras. Pass `preview_view_sets` for
head offsets or parallel stereo pairs. These use the same schema and renderer as
`scene.render_sheet`. The package retains the cameras, sheet, and individual views.

Read the manifest and optional `report.json` for actual checks. `verification="structure"`
labels reopening as skipped. Neither mode certifies VR comfort or full glTF conformance.
The report does not request self-intersection checks. Files have sizes and SHA256 hashes;
the manifest excludes itself and the result supplies its hash separately.

Keep `overwrite=false` unless replacement is intended. Replacing a directory requires
an Scissors bundle with no undeclared files. A failed preparation preserves old output.
If publication and restoration both fail, preserve the reported recovery directory.
The operation cannot run inside a scene transaction or atomic batch. It bounds bytes,
geometry work, images, and elapsed computation. It leaves the source scene unchanged.
