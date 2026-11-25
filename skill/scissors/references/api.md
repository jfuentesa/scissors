# API and connection reference

Scissors API `1.0` exposes operation names, parameter/result schemas and capabilities
at runtime. Use these public descriptions as the source of truth. This skill requires
an installed application or an existing service, not the application's source code.

MCP stdio configuration for compatible clients:

```json
{"mcpServers":{"scissors":{"command":"/absolute/path/to/scissors","args":["--workspace","/absolute/path/to/workspace","mcp","stdio"]}}}
```

Use the actual installed executable (`scissors.exe` on Windows) and your client's
MCP settings format. Alternatively use an interpreter with Scissors installed:
`/absolute/path/to/python -m scissors.cli --workspace /absolute/workspace mcp stdio`.
Python 3.12+ is required. The skill directory is independent of the application and workspace.
To select a custom shared plugin store, add `--plugins-dir /absolute/plugins` before
`mcp stdio` in the server arguments, or set `SCISSORS_PLUGINS_DIR` in the client's server
environment. A client's environment filter may omit variables from its parent process.
Use the operator's store configuration; `modeler.info` reports the resolved `plugins_dir`.

For HTTP use the operator-provided MCP URL, such as `http://127.0.0.1:8765/mcp`.
The operator can start it with
`scissors --workspace /absolute/workspace serve --host 127.0.0.1 --port 8765`.
Choose the actual host and port; 8765 is only the default.
Bearer authentication is optional on loopback and required on other bind addresses;
configure the server's `SCISSORS_TOKEN` and the client's bearer credentials when using it.
Relative CLI workspace paths resolve from the process working directory; absolute paths
avoid ambiguity. Only one process can open a workspace. While HTTP or stdio owns it,
use that connection. Stop that owner before accessing the same workspace via CLI or Python,
including when installing or uninstalling plugins. A session belongs to the workspace it
opened. Only open a different workspace when the operator asks for it: it is a new session
with its own scenes, textures and plugin activation settings. Plugin packages are shared
through the application plugin store (`plugins_dir` in `modeler.info`).

Discovery: `operations_list({"category":"mesh"})`,
`operations_describe({"name":"mesh.create_cube"})`,
`operations_invoke({"name":"mesh.create_cube","arguments":{"scene_id":"SCENE_ID","size":2}})`.
Omit `category` to discover all operations. Names such as `scene.create` are arguments
to `operations_invoke`, not literal MCP tool names. Most direct tools replace `.` with
`__`; some have aliases such as `scene_create` and `scene_export`. Consult the actual
tool list or use generic invocation.

Invocation success contains `success=true`, `operation`, `result` and `warnings`.
Discovery success contains `success=true` and `result`; `operation` and `warnings`
are not guaranteed. Failure contains `success=false` and `error` with `code`, `message`
and `details`; `operation` may be absent. MCP provides the object as structured content
and JSON text, with its error flag set on failure. Check success before reading IDs or
continuing dependent steps. An `INVALID_PARAMETER` message names the failing field and
the violated constraint, for example `Invalid parameter background[0]: 16 is greater
than the maximum of 1`. `details.parameter` repeats the path and `details.reason` the
constraint; read the message before inspecting the schema.

Choose methods from the current parameter enum. Standard installation includes all
built-in geometry backends. If a stale request receives
`BACKEND_UNAVAILABLE`, its `error.details` provides `backend`, `requirement`,
`parameter`, `requested_value` and `available_values`. Select an appropriate available
method or report the missing dependency to the user; do not install it automatically.

Python usage, with an installed Scissors environment and an unowned workspace:

```python
from scissors import Scissors

with Scissors("/absolute/path/to/workspace") as app:
    scene = app.call("scene.create", name="Example")
    cube = app.call("mesh.create_cube", scene_id=scene["id"], size=2)
```

`app.call` returns the result dictionary directly and raises `ScissorsError` on failure.

Public convenience namespaces include `app.scenes`, `app.meshes`, `app.materials`,
`app.textures`, `app.uv` and `app.export`; their results support attribute access and
`.as_dict()`.

REST: `POST /api/v1/operations/invoke` accepts the same name/arguments object.
`GET /api/v1/operations` lists capabilities; `GET /api/v1/operations/{name}` returns
full schemas. The running service's `/docs` endpoint provides OpenAPI.

Operation file paths are relative to the server workspace and must stay inside it.
Exports report `path`, `format`, `size_bytes` and `diagnostics`: these describe server
files, not download URLs. MCP has no arbitrary file upload/download or general filesystem
interface. Texture import and plugin validation require files already in that workspace;
place them using available local filesystem tools or ask the operator to do so.

## FBX import

Use the built-in `scene.import_mesh` operation with a workspace-relative `.fbx` path.
`modeler.info.backends.import_fbx` reports the included ufbx reader. Binary and ASCII
FBX need no external converter. The importer retains static geometry, UV/normal/color
seams, hierarchy, instances, material bindings and supported embedded/relative images.
It converts the declared axes and units to right-handed Z-up destination scene units.
`source_up` overrides axes, while `scale` is an additional multiplier and `position`
uses destination scene units. `source_unit_meters` reports the original declared unit.
Phong/Lambert materials are approximated as PBR. Inspect returned warnings and preview
the imported material. Skins, blend shapes and animation are not evaluated. Bake
layered/procedural textures, transformed texture coordinates and maps on additional UV
sets; triangulate polygon holes. Separate opacity maps are omitted with a warning.
Missing supported external images fail import, and all image reads remain inside the
workspace. Static FBX exports use Y-up coordinates and PNG sidecars.

Binary FBX defaults to `fbx_mode="preserve"` when rig, blend-shape or animation data exists.
The result includes `rig`; `scene.inspect` lists retained `rigs`. Use a new/empty scene,
source_up="auto", scale=1 and no position. Retained documents embed their source images
and keep original axes and units at complete FBX export. The bind-pose view is normalized
to Z-up. Animation playback and rig editing are unavailable. Keep scene membership,
hierarchy, placement and materials unchanged. Conservative simplification remaps surviving
original positions/UV to exact original skin weights. Arbitrary weight transfer and edits
with extra deformers are unsupported. Other formats, partial/split/LOD exports and root
renaming fail explicitly. `fbx_mode="static"` deliberately discards source rig/animation.
Keep `assets/fbx_documents` with state.json when relocating a workspace.

## Mesh simplification

Discover and describe `mesh.simplify` before using it. It is a native operation.
`modeler.info` reports its availability in `backends.simplify`.
If VTK is missing from an incomplete installation, it returns `BACKEND_UNAVAILABLE`;
inform the operator. Extra flags are not needed for a healthy standard installation.

`reduction_percent=50` requests removal of half the faces.
`uv_policy="preserve"` preserves UV and protects their seams by default.
The method preserves topology, components, boundaries and user metadata. Changed geometry
updates its revision and invalidates earlier geometry references. It may reduce less than requested.
Read `actual_reduction_percent`, `target_reached` and `warnings`.
With `require_target=True`, an unmet target returns an error and restores the scene.
`max_error_relative` limits a geometric error estimate from VTK.
It does not guarantee identical appearance or a maximum distance between surfaces.

Use `uv_policy="discard"` only when UV removal has been requested.
The material is retained, but UV must be generated before textured export.
New UV can change the placement of the existing texture.
Validate the object and review a preview after simplification.

## Boundary bridges

`mesh.boundaries(object_id)` returns `object_id`, `geometry_revision`, and `loops`.
Each loop contains `loop_index`, directed representative render `vertex_indices`, and
`edge_count`. Exact-position topology joins UV seams for boundary discovery.
Closed meshes return no loops. Branched or non-manifold boundaries fail.

`mesh.bridge(first, second, name="Bridged mesh", replace=false, second_offset=null,
material_id=null, uv_policy="preserve")` takes two selections, each containing
`object_id`, `geometry_revision`, and `loop_index`. They must identify different
meshes in one scene. Stale selections fail. The result combines both source surfaces
and a triangle strip between the selected boundaries. Unequal edge counts are supported.
Sources remain unless `replace=true`. Coordinates stay fixed, normals recompute, and
the combined object has an identity transform. Other openings remain open.

UV and colors survive; absent colors become opaque white. Mixed UV requires
`uv_policy="discard"` or UV generation on the missing source. Different materials
require a scene `material_id` override. Bridge UV reuses endpoints and may stretch.
The second loop traverses reverse source order. Automatic alignment chooses the nearest
vertex to the first loop's start; `second_offset` overrides its reversed-loop index.
The response includes the used offset, `bridge_face_indices`, source IDs and vertex
offsets. Degenerate or non-manifold joins and inconsistent winding fail atomically.
Inspect self-intersections and previews; a bridge does not certify intersection-free geometry.

## Geometry and named selections

Queries return `object_id`, `geometry_revision`, `kind`, primary indices,
`vertex_indices`, element `count`, `empty`, and world `bounds` (`null` when empty).
Never reuse indices after geometry edits.

| Operation | Primary indices | Additional filters/results |
| --- | --- | --- |
| `mesh.select_vertices` | `vertex_indices` | Render vertices; seam copies remain distinct. |
| `mesh.select_edges` | `edge_indices` | `boundary_only`; `edges` gives representative render pairs. |
| `mesh.select_boundaries` | `loop_indices` | Whole `loops` matching `mesh.boundaries`. |
| `mesh.select_components` | `component_indices` | `seed_face_indices`; returns complete `face_indices`. |

All take `object_id`, optional primary indices, `region`, and `tolerance=1e-6`.
Omitted indices mean all candidates; `[]` means none. All filters combine with AND.
Edges use exact-position topology. Edge indices order welded vertex pairs
lexicographically; welded vertices order positions lexicographically.
Components share edges, including across seams; point contact is insufficient.
Component order follows the lowest face index in each component.

Regions contain `bounds` with two world XYZ vectors and `rule` equal to
`fully_inside`, `centroid_inside` or `intersects`. Tolerance expands the box.
Vertex rules test containment. Edge centroids are midpoints, loop centroids average
vertices, and component centroids use triangle area. Intersections test actual
segments or triangle surfaces, not just bounding boxes. Query errors include
`INVALID_PARAMETER`, `RESOURCE_LIMIT`, and `OPERATION_TIMEOUT`.

`mesh.selection_save(name, selection, overwrite=false)` stores a complete query
result, including `mesh.select_faces` output. The response contains `name` and
canonical `selection`. `mesh.selection_get(object_id, name)` returns it directly.
`mesh.selection_list(object_id)` lists names, kinds, counts and `stale` status.
`mesh.selection_delete(object_id, name)` removes a name, including a stale one.
Names have 1–128 characters with at least one non-space character. Each mesh stores
at most 128 names within configured byte limits. Save/delete require scene writes;
queries/get/list are read-only. Stored selections persist with scene state.
Geometry edits make them stale: get raises `INVALID_PARAMETER`; refresh the query
and overwrite the entry explicitly. Saved face/component selections can be passed
to operations accepting revision-bound `face_indices`, such as `mesh.shell`.

## Local face edits

Pass `object_id` and a current selection containing matching `object_id`,
`geometry_revision` and nonempty unique `face_indices`. Face/component query
results and stored face/component selections are accepted.

| Operation | Arguments | Behavior |
| --- | --- | --- |
| `mesh.move_faces` | `offset`, `detach=true` | Move selected faces; duplicate shared render vertices first. With `detach=false`, all exact-position seam copies move and neighboring faces can deform. |
| `mesh.delete_faces` | `empty_policy="error"` | Remove selected faces and unused vertices. Use `delete_object` to permit deleting every face. |
| `mesh.separate_faces` | `name=null`, `keep_source=false` | Extract faces to a new mesh with identity transform and baked world coordinates. Remove them from the source unless `keep_source=true`; delete an empty source. |
| `mesh.extrude_faces` | `offset` | Replace selected caps and add walls around all selected boundary contours, including holes. Each component must have an open, consistently wound manifold boundary. |
| `mesh.flip` | `selection=null` | Reverse selected faces, or the whole mesh when omitted. Partial flips can introduce inconsistent winding. |

Offsets are nonzero world XYZ vectors. Existing UV, colors and material references
survive; normals recompute. Extruded caps copy source UV, while each wall edge uses
a separate unit UV rectangle. Side faces copy endpoint colors. Inspect stretching,
open boundaries after detached movement, and self-intersections after extrusion.
New separated meshes retain source parent and visibility, without copying named selections.

Results include source ID/revision, `source_deleted`, counts, `new_to_old_vertices`
and `new_to_old_faces` (`-1` for new wall triangles). Vertex origins can repeat.
When the output exists, `selection` addresses its edited faces (extruded caps for
extrusion; empty after deletion). Separation also returns `source` with the remaining
mesh summary and index maps, or `null` for a deleted source. Use the returned fresh
selection for the next edit. Geometry changes make older selections stale.
Every operation requires `scene.write`; failures restore scene state. Geometry,
memory, time and result-size budgets apply.

## Targeted hole filling

`mesh.fill_holes(object_id, max_edges=64, selection=null, method="projected",
refinement=2, tangent_tolerance_degrees=20)` fills selected boundary loops or all
eligible loops when `selection` is omitted. Use `mesh.select_boundaries` or a saved
boundary selection with `object_id`, `geometry_revision` and nonempty unique
`loop_indices`. Unselected openings remain open. Selected loops above `max_edges`
fail; automatic mode skips oversized loops. The edge limit ranges from 3 to 512.

Projected mode triangulates a best-fit projection without adding interior vertices.
Smooth mode fits a cubic height chart to neighboring positions and boundary tangents.
It adds interior samples with `refinement` from 1 to 4, preserving the original
boundary and all source geometry. Existing UV, colors, material and transform remain;
new smooth samples interpolate boundary attributes. Normals recompute.

Smooth mode requires every new boundary triangle's geometric angle to its existing
neighbor to be within `tangent_tolerance_degrees` (greater than 0, at most 90).
Unsupported height charts, invalid projections or unmet bounds raise `GEOMETRY_ERROR`.
The error for an unmet bound reports the loop, maximum angle and requested tolerance.
No projected fallback occurs. The bound describes triangle joins; it does not certify
continuous curvature or intersection-free geometry. Inspect patch UV and intersections.

Results include `filled_holes`, `filled_loop_indices`, `patch_face_indices`, `method`,
and `patches` with `loop_index`, `face_indices` and `max_join_angle_degrees`.
The returned face `selection` uses the current revision. Older saved selections
become stale. With no eligible loops, geometry stays unchanged.
The operation requires `scene.write`. Invalid selections, exceeded budgets and
failed geometry/angle checks restore the scene. Geometry, memory, comparison, time
and output-byte limits apply.

## Winding repair

`mesh.check_thickness(object_id, minimum, tolerance, selection=null, rim_selection=null)`
is a read-only query. Positive minimum/tolerance use scene units. It bounds the infimum
of inward face-normal chords on actual triangle interiors, ending at the first boundary
exit. A current face/component selection limits sources; the whole mesh remains exit
geometry. Explicit rim_selection excludes source rim faces and first-exit rim domains.
A current shell rim map is used when explicit rims are omitted; stale maps are unresolved.
An empty current rim_selection.face_indices explicitly declares no rim exclusions.
Read excluded_rim_regions, excluded_rim_exit_regions and coverage.excluded_exit_area.
A pass covers only the stated domain, not excluded rims or ideal smooth geometry.

Closed manifold topology, completed nonadjacent intersection checks and alternating
nested-shell orientation are required. Exact rational clipping/depth partitions cover
source faces and locate extrema between sample locations. samples contains face-domain
minima with witnesses, opposing faces and rounded exact-length bounds. Corner limits
count and can be zero; zero-area tangent domains do not count. coverage.complete and
achieved_error_bounds.global_lower/global_upper state the guarantee. A pass needs full
coverage, bound width <= tolerance and lower >= minimum. An upper < minimum proves a
failure even if other regions remain unresolved. Otherwise return inconclusive.
Rectangular unchanged miter shells retain analytical plane bounds. Geometry, memory,
comparison, rational-size, partition/output and timeout limits can prevent completion;
no uncompleted check passes. General queries allow 4096 face minima and 4096 active
cells. Triangle tests and cell updates consume max_geometry_pairs. No mutation or files.

`mesh.repair_topology(object_id, voxel_size, mode="solid", shell_thickness=null)`
replaces an existing mesh while retaining ID, hierarchy, material and diagnostic
transform. `mesh.repair_topology_data(scene_id, vertices, faces, voxel_size,
mode="solid", shell_thickness=null, name="Repaired mesh")` accepts raw damaged
triangles and creates only validated output. Coordinates are finite triples and
faces contain three nonnegative integer indices. Input may have non-manifold edges,
duplicate or degenerate faces; normal scene validation stays enforced.

Solid mode samples absolute generalized winding above 0.5. Coherent overlapping
shells form occupied union regions; inward nested shells can keep cavities.
Opposite orientations can cancel. Open surfaces have no reliable solid interior.
Shell mode samples an unsigned-distance envelope on both sides of all triangles;
provide `shell_thickness >= 3 * voxel_size`. Crossing panels can merge into a closed
thick envelope. Resolution can lose small details and close nearby gaps. Neither
mode guarantees exact deviation or thickness. UV/colors clear; normals recompute.

Results contain `validation`, `grid_samples`, `removed_input_faces`, mode, resolution
and warnings. Output checks closed topology, winding, positive total volume,
duplicate/degenerate triangles, single-fan vertex links and nonadjacent intersections.
Faces sharing a vertex are excluded from intersection pairs. Failed verification,
empty interiors or clipped grid boundaries raise GEOMETRY_ERROR. Grid memory,
geometry, file, worker timeout and comparison limits apply. Solid sampling budgets
grid samples times cleaned input faces; the output bounding-box broad phase also
uses max_geometry_pairs. Both operations need scene.write and support atomic batches
and transactions. No invalid or unchecked output enters a scene. `mesh.remesh`
continues to require closed oriented input.

`mesh.repair_winding(object_id, selection=null, orientation="preserve", dry_run=false)`
finds the triangle reversals needed for consistent shared-edge directions. Selection
accepts current face/component query results or saved selections. Without a selection,
it inspects all faces. Outside faces stay fixed and anchor selected border directions.
An insufficient selection or contradictory winding constraints raises `GEOMETRY_ERROR`;
no faces outside the selection are changed. Exact positions join render seams.

Default `preserve` chooses the fewest reversals in each region without fixed neighbors.
Ties keep the lowest selected face unchanged. Consistent inward components remain
inward, including cavity walls. `outward` and `inward` require complete closed
components and choose positive or negative signed volume. Near-zero volume is
ambiguous. Cavity nesting is not inferred, and intersections are not repaired.

Only face vertex order changes. Positions, render indices, face indices, UV, colors,
material, transforms and hierarchy survive. Normals recompute on changed geometry.
Old selections become stale; the response provides a fresh `selection`.
No required reversal leaves geometry and its revision unchanged.

Read `flipped_face_indices`, `flipped_face_count`, `planned_flip_face_indices`,
`planned_flip_count`, and `regions` with face indices, anchoring, closed status and
planned counts/normalized signed volume. Compare `scope_conflicts_after` with
`global_conflicts_after`: defects outside the selection may remain.
In dry runs actual counts and geometry stay unchanged; `planned_scope_conflicts_after`
and `planned_global_conflicts_after` describe the plan. `changed` is false and actual
flip counts are zero. Selection errors use `INVALID_PARAMETER`; geometry failures
and exceeded geometry/memory/comparison/time/response budgets use structured errors.
The operation requires `scene.write`; failures and atomic batches restore state.

## Selected solid bevels and patch reconstruction

`mesh.bevel`, `mesh.chamfer`, and `mesh.fillet` accept optional `selection` from
`mesh.select_edges` or named edge storage. It consumes `object_id`,
`geometry_revision` and nonempty unique `edge_indices`. Stale or invalid selections
fail. Coplanar diagonals are not geometric creases and are rejected. The source
must be a closed positive consistently wound solid; open panels are unsupported.

Without a selection, existing global rolling-kernel behavior applies. With a
selection, finite edge prisms subtract convex corners or add concave corners.
Choose matching `mode` or `both` for mixed selections. Convex cuts precede concave
additions. Prisms stop at original edge endpoints. Local bevel/chamfer width is
face setback; local fillet radius sets its circular arc. Segments sample the band.
Inspect overlapping widths and junctions; no CAD miter/tangency guarantee is provided.

Source UV/colors interpolate; new cut UV is world planar and new colors follow
edge endpoints. Missing/discarded UV becomes planar. Material and transforms
survive, normals recompute, and Boolean triangulation can change face/render indices.
Refresh selections. `replace=false` retains the source. The result identifies
`selected_edge_prisms`, selected edge indices, UV method and zero cleanup tolerance.

`mesh.reconstruct_patch(object_id, selection, refinement=1, iterations=5,
strength=0.5, sharp_angle_degrees=45)` refines and smooths an existing selected
surface region. Face/component and saved selections are accepted. It supports
open/closed meshes. Border and sharp-feature positions stay fixed, including across
seams. Only unprotected interior positions smooth. Creases at or above the sharp
angle never subdivide. New UV/colors interpolate from the original render triangle.
Unselected faces retain indices and positions. Normals recompute.

Refinement ranges from 1 to 3; iterations from 0 to 100 (zero means no smoothing);
strength from above 0 to 1; sharp angle from above 0 to 180. The output includes
`protected_vertex_indices`, representative `protected_edges`, `new_to_old_faces`
and a fresh face `selection`. Saved selections become stale. Inspect shrinkage,
UV and intersections. Reversed or degenerate triangles fail. Use `mesh.fill_holes`
for missing surfaces. Both workflows require `scene.write`, enforce resource limits,
and roll back on failure.

## Repair diagnostics and highlighted previews

`mesh.validate(..., include_selections=true)` adds revision-bound `selections` and
one face selection per surface in `components`. Available keys include
`boundary_edges`, `non_manifold_edges`, `duplicate_faces`, `degenerate_faces`,
`winding_edges`, `inconsistent_winding`, `disconnected_components`,
`nonpositive_volume`, `incorrect_normals`, `unused_vertices`, and attribute issues.
Duplicate selection contains extra copies, keeping the lowest face index.
Edge targets provide primary `edge_indices`, representative `edges`, and incident
`face_indices`. Each target has count, bounds, empty status, and a preview hint.
Store it or consume its primary indices with a matching repair operation.

`self_intersections` is included only after a completed requested query. Read
`selection_statuses.self_intersections`: unrequested or uncompleted queries do not
yield a clean selection. Invalid base arrays return `selection_status="unavailable"`;
an uncompleted requested intersection check returns `partial` with other selections retained;
non-mesh nodes return `not_applicable`. Open borders, multiple components, tiled UV
and unused vertices can be intentional. Selections supplement errors and warnings.
Diagnostics remain read-only and do not bypass validation rules for scene writes.

`scene.preview(..., highlights=[selection, ...])` accepts up to 64 current geometry
selections. Faces/components draw polygons; edges/boundaries draw lines; vertices
draw markers. The shared orange x-ray overlay works with VTK and Pillow on the color
pass. Surface occlusion is ignored; camera/viewport clipping and section centroid
tests apply. Objects must be visible and included in the chosen scene/object filters.
Stale or invalid input fails before output. The image reports `highlight_mode` and
counts per selection. Depth/normal passes reject nonempty highlights. Geometry,
material and visibility remain unchanged; existing filesystem/resource limits apply.

## Surface UV and PBR transfer

Keep a textured source object before rebuilding. `uv.copy_from` requires matching
indexed topology. `mesh.transfer_uv(object_id, source_object_id, max_distance,
selection=null, source_selection=null, material_policy="source", transfer_colors=true,
min_normal_dot=0)` projects source UV onto target face corners across different topology.
Selections are revision-bound face/component results. Max distance is nonnegative;
normal dot ranges from -1 to 1. Unmatched samples and collapsed UV triangles fail.
Selected corners split, unused vertices compact, and world face positions stay fixed.
Source material policy shares PBR references in the same scene or clones the material
across scenes. Partial source-policy transfer requires matching materials. Target
policy keeps the old material. Corner sampling can stretch across source UV seams;
use baking when those seams cross target faces. UV-only transfer is scene-write only.

`texture.transfer` uses the same object/distance/selection/normal parameters plus
`resolution=256`, `channels=null`, `padding=2`, `wrap="repeat"`. Both objects require
UV/materials. Target UV stays in `[0,1]` with nondegenerate triangles and no overlapping
interior bake samples. Every selected face must own a texel; increase resolution if
needed. Overlap detection is raster based, not analytic. Source UV repeats or clamps.
Resolution ranges from 16 to 4096; padding from 0 to 16.

Channels default to base_color, normal, metallic_roughness, emissive and occlusion.
Explicit lists are nonempty and unique. The target material is cloned. Selected
texels receive source effective values; other texels retain target values after
filtering and 8-bit quantization. Channel factors bake into images and become neutral.
Color RGB filters in linear space and stores as sRGB. Normal vectors move through
source/world/target tangent frames, including mirrored UV. Valid shading normals and
UV tangent frames are required; the basis is angle weighted and is not MikkTSpace.
Vertex colors and lighting are not baked. Untransferred channels remain unchanged.

New PNGs and material references persist and export normally. Source files and
shared materials remain unchanged. Unused target vertices compact; otherwise UV,
world geometry, shading normals and hierarchy stay fixed. Results include channel
artifacts, painted pixels, maximum distance, new_to_old_vertices and a fresh selection.
Compare its revision after compaction before reusing saved selections.
Baking requires scene.write/filesystem.write and rejects atomic batches/transactions.
Owned maps are cleaned on ordinary failure, including failed checkpoints; cleanup
errors are reported. UV transfer supports atomic scene edits. Both workflows enforce
geometry, memory, pixel, comparison, raster work, time and byte limits.
