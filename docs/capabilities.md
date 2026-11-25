# Modeling features and limitations

Scissors supports native cubes, spheres, cylinders, cones, planes, tori, prisms,
pyramids, polygons, stars, profiles and curves, profile/ribbon extrusion, resampled lofts, flat normals,
native rounded boxes with edge chamfers, transported tubes, louvers and switch grids,
global rolling-kernel bevel/chamfer/fillet on existing closed solids,
selected solid creases and local patch reconstruction with fixed borders and sharp features,
capsules, hemispheres/domes, Platonic solids, plates with holes, wedges, gears and springs,
torus arcs/knots, star/cross/arrow variants, angle-based normals with UV seam smoothing,
groups, markers, editable instances with shared matching GLB geometry, persistent visibility,
explicit UV rectangles, labeled render sheets, bounded triangle contact/distance queries,
closed-solid penetration queries, nonadjacent self-intersection queries, scene digests/reports,
mesh repair, explicit triangular meshes, transforms, duplication, mirroring,
revision-bound boundary discovery and bridges between existing mesh openings,
vertex/edge/boundary/component selections and persistent named selections,
selected-face movement, deletion, extraction, extrusion and winding reversal,
automatic winding repair with fixed outside faces and explicit component orientation,
validation repair selections and backend-independent x-ray diagnostic highlights,
surface UV projection and five-channel PBR baking with tangent-normal reorientation,
sampled solid and thick-envelope reconstruction for intersecting/non-manifold topology,
targeted hole patches with projected or measured-angle smooth joins,
merge, subdivision, topology/stats, PBR materials, checker/imported textures, primitive UV and
packed atlas, GLB/glTF/OBJ/STL/PLY/DAE/USDZ/binary FBX, subset/material/LOD/split delivery,
fast preview with
VTK or a Pillow fallback, camera, section, object filters and optional
texture sampling, versioned persistence, atomic scene batches, deferred-checkpoint
transactions, Python, REST, real stdio/HTTP MCP, auto-enabled dynamic plugins and CLI.

One process owns each workspace. Versioned JSON manifests reference private numeric NPZ
geometry files and reuse unchanged arrays. Legacy workspaces upgrade on successful mutation. Scene
snapshots reference textures in their workspace; move the whole workspace to keep assets.
Box UV overlaps; by default preview uses solid colors without texture sampling or shadows,
and `sample_textures` adds base-colour sampling without alpha blending. glTF and GLB
export convert the Z-up scene into the glTF Y-up convention and name nodes after objects;
OBJ and STL keep scene Z-up coordinates. OBJ approximates
PBR; STL has no materials. Generic merge clears UV/materials; subdivision clears UV.
Booleans preserve interpolated UV/colors/normals and support first/source/cut materials.
Multiple material results use grouped mesh parts and combined solid statistics.
Normals are recomputed and transforms baked. Topology welds exact-position UV seams,
so overlapping coincident surfaces need inspection. Triangle queries reject workloads above
`max_geometry_pairs`; adjacent faces are excluded from self-intersection queries. No rig editor, animation playback, GUI or generative images. Binary FBX rigs and animation
can be retained for complete FBX export; see [FBX rig retention](fbx-rig.md). Nothing depends on Blender.

Previews render through VTK offscreen when an OpenGL context exists and through a Pillow
painter otherwise. The result reports the backend. Both share one camera model with
perspective and orthographic projections, sections and object filters. Two diagnostic
passes use VTK: depth reads the z-buffer and writes numeric camera distance, and normal
draws world-space normals as RGB colours with lighting off. Looping GIF turntables move the
camera without adding scene animation data.

Surface tools include seam-aware signed offset, closed thickness shells and plane clip/slice
with attributed cuts and VTK caps, including holes. Existing UV/material/color data remains;
new cap UV is planar. Miter offsets approximate curved regions and can self-intersect in
tight concavities. They are not exact signed-distance offsets. Inspect thin geometry.

Boundary bridges join two meshes in one scene with an oriented triangle strip, including
contours with unequal edge counts. They preserve source surfaces, render seams, UV and
colors. The combined mesh uses one material; differing source materials need an explicit
override. Other openings remain open. Sources can be retained or replaced atomically.
New faces reuse boundary UV. Inspect texture stretching and self-intersections.

Hole filling accepts revision-bound boundary selections so other openings stay open.
Projected patches triangulate a best-fit projection and retain exact boundary positions.
Smooth patches fit the neighboring surface, refine the interior and require measured
boundary triangle angles within a requested tolerance. Unsupported height charts or
unmet tolerances fail atomically. Existing geometry and attributes stay fixed; inspect
new patch UV and self-intersections. Smooth joins bound triangle angles, not continuous
surface curvature.

Topology repair reconstructs existing objects with `mesh.repair_topology` or accepts
damaged triangle soups with `mesh.repair_topology_data`. Solid mode samples absolute
generalized winding above 0.5; orientation determines occupied regions and cavities.
Shell mode builds a two-sided unsigned-distance envelope around open or crossing
panels, with thickness at least three voxel sizes. Output must pass closed topology,
vertex-link and nonadjacent intersection checks before publication. Grid resolution
changes shape and can remove small details or merge nearby sheets. UV/colors are
cleared. Grid, comparison, memory, geometry and time limits can reject a repair.
Existing `mesh.remesh` still requires closed oriented input.

Thickness inspection bounds whole face-normal chord domains on arbitrary closed
triangulated walls, including curved panels and inward cavity surfaces. Exact rational
partitions locate first exits and thin regions between sample points. Select source
faces and mark rim/end-cap faces explicitly when they lie outside the wall measurement.
The report states excluded first-rim-exit areas, coverage and rounded global bounds.
A pass requires complete coverage and sufficient lower bounds. Sharp corner limits
can have zero thickness. Open, invalid or unverified walls remain inconclusive, and
time/memory/comparison/partition limits can prevent certification. This measures the
actual planar mesh along face normals, not an ideal smooth wall in all directions.

Native text geometry samples FreeType vector contours and extrudes them with Manifold,
including glyph holes and overlapping strokes. Built-in ASCII faces and workspace Unicode
TTF/OTF files are supported. Complex shaping, right-to-left text and font collections are not.

Delivery supports subtree selection, export-only affine placement/root naming, material
consolidation, separate part files and VTK-generated LODs with actual face reports.
STL includes every placed instance. PLY is binary geometry with normals/colors and UV
properties; it omits texture images and PBR. FBX, DAE and USDZ include hierarchy,
materials and texture assets, with format-specific limits described in [the API](api.md).
Static FBX exports Y-up. DAE and USDZ export Z-up.

Timeouts apply to plugin workers and costly geometry backends; bounded native NumPy
operations run in the main process. POSIX plugin workers have memory/file limits; Windows
uses timeout/output/geometry limits without a hard OS memory sandbox. Plugin packages
retain the operator's OS permissions and are enabled when the workspace opens. See
[security](security.md).

## Included geometry backends

Native import reads local OBJ/STL/GLB/PLY/FBX through the timed geometry child. It preserves
hierarchy, geometry, UV, normals, colors and supported PBR channels. Remote and escaped
sidecars are rejected. GLB converts Y-up to Z-up. Binary/ASCII FBX uses ufbx to retain
static geometry, material bindings and embedded images, and converts declared axes/units
to right-handed Z-up scene units. Phong materials are approximated as PBR; shader graphs,
texture transforms, additional texture UV sets and polygon holes require prior baking or
triangulation. See [import behavior and limits](api.md#imported-assets-and-image-planes).
Reference image planes support measured
size and world placement. Cameras and lights are not rendered by the imported scene view.
The bind-pose view is static; original binary FBX rig/animation documents can be retained.

Native image tools draw labels, compose layers, resize, crop, rotate and export managed
textures with pixel/file/memory bounds. Image sources are retained. Materials include
emissive RGB factors plus emissive and occlusion textures. glTF exports those channels and
fresh angle-weighted tangents for normal maps. Tangents are not MikkTSpace. Previews shade
base colour, emissive and base-colour textures; normal, metallic-roughness and occlusion
images are export-only channels.
Native atlas packing remaps aligned
PBR images and UV and can combine compatible leaf meshes to reduce draw estimates.

A standard installation includes all built-in operations:

- `manifold3d`: Boolean union, difference and intersection.
- `xatlas`: advanced UV generation and controlled atlas unwrapping.
- `VTK`: mesh simplification, organic union, closed-volume reconstruction and topology repair.
- `ufbx`: binary/ASCII FBX reading, including axes, units, static hierarchy and embedded images.
  This required reader avoids depending on Blender or an external conversion executable.

Use `uv sync` and `uv run scissors info`; no extra flags are required.
Geometry libraries run in CPU child workers and need no display.
Unsupported platforms must resolve installation support rather than omit tools.

For detailed operation parameters, see [the API](api.md),
[mesh simplification](mesh-simplify.md) and [anatomical modeling](anatomical-modeling.md).
