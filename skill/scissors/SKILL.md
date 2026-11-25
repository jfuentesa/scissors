---
name: scissors
description: Model and texture local 3D objects with Scissors MCP or Python, validate and export assets, and develop reusable Python geometry plugins when the engine lacks an operation.
---

# Scissors modeling and extensions

Use this skill when operating Scissors. Reasoning and code generation belong to you;
Scissors has no LLM. Start with capability discovery instead of guessing operation names.
Its scope is modeling, validation, export and independent plugins using the public API.
Development of the Scissors engine and maintenance of this skill are separate tasks.

## Check the connection first

If Scissors MCP tools are already available, use that connection and call `modeler_info`
to identify its workspace and capabilities. Do not start another instance for that workspace.

If no connection is available, ask the user how to access Scissors and which workspace
to use. Ask for the installed executable or Python environment for local API/stdio access,
or the local service URL for HTTP. Reuse details the user has already provided; ask only
for missing information. Do not search for installations, choose paths or start a service
until the required details are provided.

The workspace belongs to the user. Use the workspace of the connection you already
have, and report it to the user when you start work. Never choose, create or open
another workspace, and never start a second instance, unless the user explicitly names
it. Reusing an existing connection never authorizes a different workspace. When a task
needs another workspace, name it, say why, and wait for the user to provide access.

The application installation, this skill's directory and the workspace are separate
locations. This skill contains instructions; its location does not determine where
Scissors is installed or where models, textures and exports are stored.

The launchers, CLI and Python API default to `workspaces/agents`. Launchers resolve
this path from the repository; direct CLI and Python calls use the current directory.
An existing connection may use a different workspace; check `modeler_info`.

One process owns each workspace. Use its existing connection rather than opening the
same workspace again through stdio, the CLI or Python.
See [API and MCP reference](references/api.md) for complete configuration and result shapes.

## Discover capabilities

After connecting, call `modeler_info` if you have not already done so, then
`operations_list` with a category such as `mesh`, `material`,
`uv` or `deform`. Use `operations_describe` with `name` before invoking unfamiliar
operations. The catalog's `plugin` field distinguishes native operations (`null`) from
extensions. Consult each operation's current schema and choose an available method.
`uv.generate` lists only available methods; its description identifies missing required
backends in an incomplete installation. All geometry backends are installed by default.
`BACKEND_UNAVAILABLE` reports alternatives for an unavailable method.
Do not install dependencies on the user's behalf without their instruction.
Use `operations_invoke` with `name` and `arguments` even when your client's tools list
is cached. Direct dynamic tool names use double underscores: `deform__twist_mesh`.

## Build a model

When you build or edit polygon geometry, reuse the same vertex index in every face
that meets at that point on the same surface. Create one vertex per shared position.
Split render vertices only where attributes such as UVs or normals require a seam.

Remove or connect orphan faces before delivery. An orphan face has no shared edge
with its intended surface. Use `mesh.select_components` after topology edits to
check for unintended disconnected faces or patches. Keep intentionally separate
parts and surfaces that consist of a single face.

1. Invoke `scene.create`; keep its `result.id` as `scene_id`.
2. Create a primitive with `mesh.create_cube`, `mesh.create_cylinder`, etc. Keep `object_id`.
   Cylinders intended for deformation need vertical resolution (`height_segments`).
3. Use `mesh.translate`, `mesh.rotate`, `mesh.scale`, `mesh.subdivide` or a plugin.
   Rotations are in degrees around the world origin; coordinates are Z-up, right-handed.
   Scale factors must be positive. Subdivision clears UV, so perform it before UV generation.
   To reduce faces, use `mesh.simplify` when `backends.simplify` is available.
   It preserves UV by default. Check the actual reduction and warnings.
   Remove helper objects with one `mesh.delete` call passing `object_ids`, never one call per
   object: a batch validates every ID, deletes in one rollback point and writes the state
   once. Deleting 60 objects individually can cost a minute on a dense scene; the batch
   takes about a second. Children are re-parented to the deleted object's parent.
4. Create a material with `material.create`, generate `texture.generate_checker`, then
   `uv.generate` and `texture.assign`. Assign the material with `material.assign`.
   Materials belong to scenes; texture IDs refer to workspace-managed PNG files.
5. Inspect using `mesh.inspect` and `uv.inspect`; call `mesh.validate` after complex edits.
   `require_closed=true` is appropriate for printable solids, but open planes are valid otherwise.
6. Review the model and its textures before delivery. This review is part of the build,
   not an optional extra. Render `scene.preview` with `sample_textures=true` from the four
   side azimuths (0, 90, 180, 270), the top and the bottom, plus one close-up per
   object. For interiors, add the section view (`clip_axis`, `clip_position`,
   `clip_keep`). Camera arguments are `azimuth_degrees`, `elevation_degrees`, `zoom`,
   `offset_x` and `offset_y`. The back and underside must appear in the images you
   inspect; one hero view is not a review.
   Every textured object passes a mandatory texture gate. Run
   `uv.inspect(texture_resolution=[width,height])` for each textured mesh and record
   `covered_area_fraction`, `degenerate_uv_triangles`, `min_pixels_per_meter`,
   `max_pixels_per_meter` and `max_anisotropy`. Reject the object when coverage is
   incomplete, a degenerate UV triangle remains, charts overlap outside repeat mode,
   density differs from its target by more than 20 percent, or anisotropy exceeds 2.0
   unless the job accepts more. Check every image for seams, stretched texels, mirrored
   text, missing maps and wrong scale. Do not export until the views pass.
   Depth and normal passes require VTK; diagnostic highlights use the color pass.
   Follow the [review recipe](references/workflows.md).
7. Export using `scene.export` and save using `scene.save`. Keep outputs inside the
   workspace, for example `exports/model.glb`. Before export, check the geometry report
   with `mesh.validate` and review a section view for wall thickness.
   With access to the server's files, verify the artifact exists, reopen the GLB and
   confirm it carries its base-colour texture. Otherwise report the returned server
   path, size and diagnostics, and state that the file was not independently reopened.
   A server path is not a download URL.
   GLB, glTF and static FBX export Y-up. OBJ and STL keep scene Z-up coordinates.

Use [workflows](references/workflows.md) for runnable examples and batching.
For organic surfaces, local edits, sculpting, controlled UV and image projection,
read [anatomical modeling](references/anatomical-modeling.md).
Results are compact: avoid requesting arrays unless developing or diagnosing geometry.
Use `mesh.figures` to discover native figures. Start with a profile and `mesh.extrude`
or `mesh.loft` for shaped panels and shells. Use `mesh.create_prism` with the required
side count and `mesh.facet` for flat mechanical faces. Native operations need no plugin.
Use `mesh.create_rounded_box` for panels, `mesh.create_tube` for frames and cables,
and `mesh.create_louver` or `mesh.create_switch_grid` for mechanical detail.
These figures are native.
Use capsule/dome for rounded bodies, plate for through holes, wedge for ramps,
gear for toothed wheels and spring for a helix. The figure table lists variants.
Use `mesh.split_normals(angle=30)` after geometry edits to retain hard edges while
smoothing UV seams. Capsule height includes both hemispheres. Spring height is
centerline travel. Dome radius is its base radius. Read schemas for exact limits.

To connect openings in two existing meshes, call `mesh.boundaries` for each object.
Pass each `object_id`, `geometry_revision`, and chosen `loop_index` as `first` and
`second` to `mesh.bridge`. Refresh boundary queries after geometry edits.
The bridge supports different edge counts and creates one combined mesh.
Set `replace=true` to remove the two sources after validation. Different materials
need an explicit `material_id`; mixed UV needs UV generation or `uv_policy="discard"`.
Inspect intersections and texture stretching before keeping the result.

Use `mesh.select_vertices`, `mesh.select_edges`, `mesh.select_boundaries` or
`mesh.select_components` for explicit geometry selections. Queries accept index
lists and world boxes; all supplied filters combine with AND. Edges and components
weld exact positions for topology, while vertex indices address render vertices.
Use `seed_face_indices` to select whole components from known faces. Point contact
does not connect components. Read schemas for box rules and result fields.
Store a query result with `mesh.selection_save(name=..., selection=...)` and retrieve
it with `mesh.selection_get(object_id=..., name=...)`. `mesh.select_faces` results
can also be stored. Named selections persist across restarts. Geometry edits make
them stale; list with `mesh.selection_list`, query the geometry again and save with
`overwrite=true`. Remove unused or stale entries with `mesh.selection_delete`.

For local face edits, pass a current face/component selection to `mesh.move_faces`,
`mesh.delete_faces`, `mesh.separate_faces`, `mesh.extrude_faces`, or `mesh.flip`.
Movement uses a world `offset`; it detaches selected faces by default. Set
`detach=false` to move shared exact-position vertices and deform their neighbors.
Extrusion replaces selected caps and adds boundary walls using a world `offset`;
each selected component needs an open manifold boundary. Inspect wall UV and
self-intersections. Separation removes selected faces from the source unless
`keep_source=true`. Deleting all faces needs `empty_policy="delete_object"`.
`mesh.flip(selection=...)` reverses only those faces; omitting the selection reverses
the whole mesh. Partial reversal can leave inconsistent winding. Use the returned
fresh `selection` to continue editing moved faces or extruded caps. Refresh saved
selections after geometry changes. See the API reference for attribute index maps.

To close one opening, use `mesh.select_boundaries(loop_indices=[...])` and pass its
result as `mesh.fill_holes(selection=...)`. Other loops stay open. Without a selection,
hole filling closes all loops up to `max_edges`. Selected oversized loops fail explicitly.
Use `method="projected"` for a faceted cap or `method="smooth"` for a refined patch
fitted to the neighboring surface. Smooth mode requires each boundary triangle's
join angle to meet `tangent_tolerance_degrees` (default 20); unmet bounds or unsupported
height charts fail without a flat fallback. Read `patches[].max_join_angle_degrees`.
The original boundary stays fixed. Use the returned face `selection` to edit or save
the new patch. Inspect texture stretching and self-intersections before accepting it.

Use `mesh.repair_winding` to correct inconsistent triangle vertex order. Pass a face
or component selection to keep the repair local. Outside faces stay fixed; conflicts
that need changes outside the selection fail, so query a larger region explicitly.
The default `orientation="preserve"` keeps each unanchored region's majority
orientation, including inward cavity walls. Use `outward` or `inward` only for
complete closed components when that signed-volume orientation is intended.
Open surfaces have no automatic exterior, and cavity nesting is not inferred.
`dry_run=true` reports planned flips without changing the mesh. Check scope and
global conflict counts separately; unselected defects can remain. Normals alone
cannot repair winding. For intersecting or non-manifold geometry, use
`mesh.repair_topology` with explicit `voxel_size`. Solid mode uses absolute winding
above 0.5; source orientation determines occupied regions and cavities. Keep coherent
winding, since opposite shells can cancel. Open panels can use `mode="shell"` with
`shell_thickness >= 3 * voxel_size` to form a thick envelope on both sides. This
changes the panel shape and can merge nearby sheets. Use `mesh.repair_topology_data`
to submit damaged vertex/triangle arrays that normal scene creation rejects.
Only validated output enters the scene. Output checks closed topology, single-fan
vertices and nonadjacent intersections. Read `validation` and warnings. Limits or
unverifiable output fail atomically; both tools support scene transactions.
Reconstruction can remove sub-voxel details and clears UV/colors. Preserve a separate
textured source, regenerate UV, then transfer attributes or bake PBR maps as needed.
Refresh selections after repair. `mesh.remesh` still requires closed oriented input.

Request `mesh.validate(include_selections=true)` to locate reported defects.
Use its `selections` for boundary/non-manifold edges, duplicate or degenerate faces,
inconsistent winding, attribute issues and completed intersection checks. Duplicate
face selections contain extra copies, retaining the lowest index. `components` gives
one face selection per surface component. Inspect `selection_status` and intersection
status; omitted intersection selections do not prove a clean mesh.
Pass a selection to `scene.preview(highlights=[...])` to show it in orange without
changing the scene. Highlights are x-ray overlays, so hidden selected elements can
appear through other surfaces. They require the color pass and a visible included
object. Save useful selections by name or pass face selections to compatible repairs.
Refresh them after geometry edits. Structural observations such as open borders or
multiple components can be intentional; use the validation errors and requested invariants.

Keep a separate textured source before rebuilding geometry. Use `mesh.transfer_uv`
for nearest-surface UV/color projection across different triangle topology. Provide
`max_distance` and optional source/target face selections. Selected render corners
split so other UV stays fixed. Source material policy shares its PBR references;
partial edits need matching materials or explicit `material_policy="target"`.
For UV islands crossing a coarse target face, bake instead of relying on corners.

Use `texture.transfer` to bake base color, normal, metallic/roughness, emissive and
occlusion into target UV. Both objects need UV/materials; target UV must form a
nonoverlapping atlas at the bake resolution. Bound distance and normal alignment.
The target material is cloned; unselected texels keep their effective values.
Factors bake into maps, colors filter in linear space, and normal vectors reorient
between source/target tangent frames. Vertex colors and lighting are not baked.
Inspect seams, gutters and texel density. New maps are immutable; failed transfers
clean their own maps. Baking writes files and cannot run in atomic batches or
Python transactions. UV-only transfer can. Read the API reference for limits and
normal-map basis requirements.
Use `scene.group` and `object.parent` for subassemblies, and `scene.marker` for anchors.
Use `scene.edit` for atomic REST/MCP edits. It rejects filesystem and plugin lifecycle effects.
Use `uv.planar` with an explicit atlas rectangle for labels. Use `scene.render_sheet`
to inspect the whole model. Use `scene.digest` and `operations.schema` to reduce tool output.
Use `scene.collisions` to distinguish surface contact from penetration of closed solids.
Triangle queries are bounded and can return `RESOURCE_LIMIT`; narrow the selection.
`mesh.data` pages arrays; offsets apply independently to vertex and face arrays.
Procedural geometry is deterministic for identical inputs, but new object IDs are random.

For repeated parts, discover mesh.array. Count includes the source. Linear copies use
offset; polar copies use axis, center and angle_degrees. Copies include descendants.
mesh.distribute builds a Fibonacci sphere of cutter cylinders around a target and returns
their matrices; orient="normal" points each cutter along the radius, so one axis drills two
holes. Follow it with mesh.boolean and delete_inputs=true to consume the cutters.
mesh.mirror supports normal/point planes and updates winding. scene.symmetrize matches
world point sets; review overlapping center-crossing objects before merging.
Use mesh.align for a target triangle and mesh.snap for the nearest surface. Both accept
gap; choose source_face for explicit face contact. Face indices can change after mesh edits.
deform.warp supports bend/twist degrees and positive end-scale taper. Use enough sections,
reapply split_normals after editing and inspect self-intersections.
mesh.measure provides triangle distance, normal/plane angle and circular hole diameter.
For automatic hole measurement, select a cap triangle with face_a. Noncircular or nonplanar
rims are rejected. Explicit vertex_indices can select a rim directly.

Before exporting normal maps, unwrap the mesh and discover mesh.tangents. It returns
angle-weighted frames; it does not promise MikkTSpace compatibility. glTF exports refresh
frames for marked meshes and normal-textured meshes. Degenerate UV triangles and shared
mirrored seams need correction first. Emissive RGB factors and emissive/occlusion slots are
available in materials. Set emissive above zero to make a screen emit in the target engine.
Previews render through VTK or a Pillow fallback and report the backend in renderer.
Use texture.draw_text for labels, texture.compose for image layers and resize/crop/rotate
for image edits. They create new managed PNGs. Pixel positions start at the top-left.
Use unused output paths or omit output. texture.export supports PNG, JPEG and WebP;
JPEG removes transparency over white. Image writes cannot join atomic scene edits.

Use texture.atlas_pack for aligned base-color and PBR atlases. Selected meshes need material
and UV in [0,1]. Tiled UV need baking. A full atlas fails instead of reducing resolution.
Padding helps base-level filtering but cannot protect all mips. merge=true combines
compatible leaf siblings and removes absorbed IDs. Read object_mapping before later edits.
Set merge=false to retain independent pieces. Atlas writes cannot join scene.edit or
app.transaction. scene.budget uses glTF sharing rules for differently placed instances.

Use scene.clone for a complete variant and scene.copy_objects for selected subtrees.
Read the returned ID mappings. Materials copy independently; immutable workspace textures
remain shared. Omitted external parents detach while world geometry stays in place.
Use scene.create_table for native figure rows with parameters, name, transform, material_id,
parent_id and repeat. Discover figure schemas first. Rows share one scene and commit; failed
placement or geometry restores all rows. There is no 100-row cap: repeat emits several copies
of one row and the call stops at the object budget. Each transform uses position/rotation/scale
or one matrix.
Save named scene.checkpoint stages. scene.compare_snapshot reports stable-ID changes;
scene.revert_to restores a stage, including a deleted scene. Names use ASCII letters,
digits, underscores or hyphens. Checkpoints reference workspace textures and survive restart.
Keep texture files with the workspace. Checkpoint writes cannot join atomic edits.
Read-only compare/restore can join scene.edit or app.transaction. Only scene changes roll back.

Use scene.import_mesh for local OBJ/STL/GLB/PLY/FBX. Provide scene_id to extend a scene;
omit it for a new scene. Paths and sidecars must stay in the workspace. Remote URIs are
unsupported. GLB uses Y-up conversion automatically; OBJ/STL/PLY default to Z-up.
Binary/ASCII FBX uses the included ufbx reader, with no manual conversion. It reads axes
and units from the file and converts to right-handed Z-up destination scene units.
Embedded images are retained as managed PNGs; missing required external images fail import.
Phong/Lambert materials are approximated as PBR. Check warnings and preview the imported
material. Bake layered/procedural textures, texture transforms and maps on additional UV
sets before import; triangulate polygon holes. Separate opacity maps are omitted with a
warning. Skins, blend-shape deformation and animation are not evaluated.
Override source_up when needed and set scale/position explicitly. Imported hierarchy,
materials, UV and colors remain editable in static mode. Cameras and lights are omitted
from the bind-pose view. Binary FBX defaults to fbx_mode="preserve" for rig/animation
retention. Use a new/empty scene, automatic axes, scale=1 and no position. Inspect result.rig
and scene.inspect.rigs. Export the complete scene as FBX without selection, transform,
root rename, material splitting or LODs. Source axes/units and original embedded media
are preserved. Keep materials and rig placement unchanged. mesh.simplify can remap weights
when surviving positions/UV remain exact; arbitrary remeshing and weight transfer are
unsupported. Unsupported exports fail explicitly. Animation playback is not available.
Use fbx_mode="static" only when discarding rig/animation is intended. Keep
assets/fbx_documents when moving the workspace. See [FBX import](references/api.md).
Topology edits can discard vertex colors. Previews shade those colors.
Use reference.plane with path, axis, size [width,height] and center position for measured
image references. Hide reference geometry before export. Import/reference creation cannot
join atomic scene.edit or app.transaction. Keep source files and required sidecars together.

For review images, set projection="perspective" or "orthographic".
Use camera_position/target, vertical fov and near/far in scene units. Enable sample_textures
for base-colour images. light_direction, light_strength and ambient control direct light.
transparent=true preserves background alpha. scene.preview reports the backend in renderer:
"vtk" uses OpenGL offscreen, "pillow" is the painter that runs without a GPU driver.
Prefer the default renderer="auto". Force "pillow" to reproduce flat, driver-independent
output. Set `render_pass="depth"` for numeric camera distance and its NPZ sidecar,
or `render_pass="normal"` for world normals. Both passes require VTK. Use sections,
mesh.inspect, mesh.validate and mesh.measure for geometry checks. Shadows and
environment lighting are not simulated. Render sheets accept projection/transparent.
Use scene.turntable for a looping GIF camera orbit. It uses an opaque palette and reports
actual/requested frame counts. Large frame caches or slow scenes can reach resource limits.

Use mesh.shell to turn a surface into thin closed geometry. Thickness uses scene units.
Offset -1 keeps the original outside, +1 keeps it inside and 0 centers thickness.
mesh.offset moves the surface without adding walls. Miter mode preserves planar corners;
curved offsets are discrete approximations. Inspect tight concave regions for intersections.
Use mesh.clip for one half-space and mesh.slice for both. Both accept world normal/point,
capped and tolerance. Caps preserve holes and use planar UV with the source material.
Clip replaces by default; slice preserves the source unless replace=true. Read returned IDs.
Open cuts may require capped=false. These edits retain source UV/material and can join
atomic scene.edit. Use split_normals after shelling for hard shading edges.

mesh.boolean preserves attributes by default. Inputs must be distinct, closed outward meshes
in one scene. UV seams are accepted. material_policy="first" keeps the body material;
"source" keeps contributing materials. cut_material_id can distinguish interior cuts.
Multiple materials produce a group. Read object_ids for mesh parts and combined for solid
statistics. Pass mesh part IDs to single-mesh tools. cut_uv="planar" uses world-plane UV
with uv_scale scene units per tile; "cutter" retains cutter UV. Missing UV is projected and
may repeat outside [0,1]. Unwrap or bake before atlas packing. preserve_attributes=false
requests geometry-only output. delete_inputs=true removes the operands in the same call and
returns deleted_object_ids, which replaces one mesh.delete per cutter.

Export subtrees with scene.export only_object_ids/exclude_object_ids. Ancestor frames keep
world placement. export_transform and root_name affect only the output. split_materials
combines export geometry by material and flattens mesh hierarchy without editing the scene.
lod_reductions creates real simplified files and a relative-path manifest. Inspect actual
face counts and warnings; topology/UV protection can prevent a target. Every level must be
smaller. Bake conflicting vertex-color seams before LOD generation. Normals recompute.
Use scene.split_export for files by object, top-level group or material. It keeps sidecars
in separate directories. Late failures can leave completed files. PLY exports geometry,
normals/colors and UV properties without images/PBR/hierarchy; use GLB for complete materials.

For one texture scale across meshes, discover `uv.generate` and `uv.inspect`.
Pass `object_ids`, `pixels_per_meter` and `texture_resolution=[width,height]` to
generate and fit charts in one scene. Use `preserve_uv=true` to fit existing charts.
Atlas mode packs separate island rectangles inside `atlas_region` with pixel padding;
capacity failure leaves every selected mesh unchanged. It never lowers density to fit.
Packing does not rotate charts and is not optimal. Repeat mode permits overlapping
UV outside [0,1], requires the full image and padding=0, and needs repeat sampling.
Inspect the returned minimum/maximum face density and anisotropy, not just the average.
Density uses meters and pixel area; it does not measure source image detail. These
numbers do not accept a texture on their own: the rendered texture gate in step 6
of the build must pass as well.
Material-batched exports keep validated parts independent at exact contacts. Use a
Boolean union when a single solid is required. FBX/DAE image tinting uses bounded
blocks and preserves texture resolution when the complete export fits memory.

Use mesh.create_text for true vector-font extrusion. Arial/Courier/Times accept ASCII and
newlines; provide a workspace TTF/OTF for accented/Unicode characters. Missing glyphs fail.
Size is nominal em-height, not exact ink height. Depth is positive and segments controls curve
sampling. Capped/axis/pivot/name/material_id are supported. Custom files supply their style;
built-ins accept bold/italic flags. Complex shaping, font collections and right-to-left text
are unsupported. mesh.figures and scene.create_table include text. Read-only font files can
join atomic scene edits; file writes and plugin lifecycle operations remain blocked.

Workspace format 2 persists geometry in private `.geometry` NPZ files referenced by
state.json. Keep that directory and image files when moving a workspace. Format 1 loads
and upgrades on the next successful mutation. Older engines cannot read the new manifest.
Use scene.save for a full JSON snapshot; its format and stable IDs remain unchanged.
Private geometry files are retained, including unreferenced files after failed commits.

Use `mesh.bevel` or `mesh.chamfer` with positive `width` on an existing closed solid.
Use `mesh.fillet` with `radius` and `segments` for a sampled round edge treatment.
Without `selection`, these treat the whole solid: convex opening by default, concave closing with
`mode="concave"`, or both. Opening stays inside the source; closing contains it.
Pass a current `mesh.select_edges` result as `selection` for local solid creases.
Select geometric edges, excluding coplanar triangulation diagonals. Local bevel/chamfer
width is the setback along adjacent faces; local fillet uses its circular radius.
Use `mode="both"` for mixed convex/concave selections. Finite edge prisms stop at
endpoints; inspect widths and junctions. These bevels require closed solids and do
not provide exact CAD tangency.
Keep `preserve_topology=true`; choose `replace=false` to retain a source for comparison.
Material survives. Global mode projects UV/colors; selected mode interpolates source
attributes and uses planar cut UV. New surfaces may need unwrap/rebake.
Inspect thin features and concave corners. Work budgets may reject dense source meshes.

Use `mesh.reconstruct_patch` with a current face/component selection to rebuild an
existing surface region. Refinement and Laplacian smoothing keep the selected border
and sharp-edge endpoints fixed. Set `sharp_angle_degrees` for protected creases and
`iterations=0` for refinement alone. Unselected face positions stay exact. New patch
UV/colors interpolate from source triangles, including seams. Inspect shrinkage and
intersections; use `mesh.fill_holes` when the region has no surface yet.

Read each `mesh.figures` entry's `common_options` schemas before creating pieces.
All families accept axis, pivot and name. Base placement makes the minimum axial coordinate
zero; center placement centers the bounds. Point/path figures keep their original origin by
default. Planar inputs keep their plane unless an axis is specified. Read the family's cap
schema: sphere and capsule accept capped=false to remove triangles at both axial poles,
creating two openings whose size depends on resolution. Cylinder/cone accept segments;
sphere segments selects a latitude/longitude sphere instead of its default icosphere.

Use `scene.collisions` with `anchor_object_ids` set to intended fixed mesh parts, such as
the chassis or base, to find floating components. Read `floating_object_ids`,
`connected_components` and `isolated_object_ids`. Without explicit anchors, floating is null.
Contact paths include touching or overlapping parts. Inspect penetrations separately;
spatial contact does not prove a mechanical joint or physical support.

`scene.export` and `scene.split_export` support binary FBX 7.4, DAE 1.4.1 and USDZ in
addition to the earlier formats. Match output extension and format. Keep all returned PNG
sidecars with static FBX/DAE. Retained rig FBX embeds its source images.
Static writers use Phong approximations and preserve unsupported PBR channels
as extras. Static FBX exports Y-up. DAE and USDZ retain Z-up. All three declare scene units.
USDZ embeds a USDA root layer and
its images with aligned uncompressed members. It is not USDC; Apple compatibility is
unverified. USD keeps vertex-color primvars, but textured shaders do not multiply them.
Open the result in the intended consumer before delivery. Structure tests do not certify
every importer or visual material result.

## Extend with a plugin

Search the catalog and installed plugins before writing code. Use an independent plugin
for new procedural shapes or deformations supported by the public PluginContext.
If the required capability needs engine internals or a public API change, describe the
missing capability, expected inputs/outputs and blocking API limitation to the maintainers.
Read [plugin development](references/plugin-development.md) for the manifest and context contract.

Prepare code under `<workspace>/plugin_staging/<plugin_id>/`, including `manifest.json`,
`plugin.py`, README and tests. The manifest declares API `1.0`, input/output JSON Schema,
dependencies, permissions and namespaced operations. The module exports an `OPERATIONS`
mapping from each declared operation name to a function receiving `PluginContext` plus
validated keyword arguments. Use public context methods, never private engine imports.

Call `plugins_validate` with the workspace-relative staging path. Validation checks the
manifest and dependencies without importing executable code. Fix failures before asking
the operator to review the package. Installation is local CLI or Python only:
`scissors plugins install PATH`, which enables the package immediately. Do not install
unknown code on the operator's behalf. Tests execute Python with the operator's permissions.

After activation, refresh `operations_list`, describe and invoke the new operation. Enabled
plugins persist across restarts. Packages live in the application plugin store reported as
`plugins_dir` by `modeler_info` (default `~/.scissors/plugins`), shared by all workspaces.
Every new session discovers them and enables them unless explicitly disabled in that
workspace. Enable/disable affects only the current workspace. Installation and uninstallation
affect the shared store; reopen other sessions after either change. Keep staging in the
workspace; installation copies the package into the shared store. Code changes take effect
on the next invocation,
which imports the current files in a fresh child; `plugins_reload` re-registers the package.
Plugin failures return structured error codes and leave scene changes uncommitted.

Plugins execute Python with the operator's OS permissions, so writing to the application plugin store is a
trust decision affecting all workspaces that use it.
Keep plugins reproducible, bounded and documented. Never hide a missing capability behind
simulated output.

For hollow bodies, use revision-bound `mesh.select_faces` results as `mesh.shell(opening=...)`.
Require closed wall geometry, one edge-connected surface and a completed intersection check
with `mesh.validate`. Use `mesh.check_thickness` and inspect its coverage and bounds.
It can bound whole face-normal chord domains for curved triangulated walls. Pass a
current face/component `selection` to measure panel skin and `rim_selection` to mark
end caps or opening rims. Sources and first-exit regions on those rims are excluded;
read their reported area. A pass covers only that stated domain. Sharp corner limits
can be zero, so inspect scope and violations. Bounds concern the actual planar mesh,
not an ideal smooth surface or every possible measurement direction. Exact partition
limits can leave a check incomplete; no incomplete check can pass. Treat `inconclusive`
as unresolved. See `references/workflows.md` for the full sequence.
