# Operate the anatomical surface tools

Discover and describe operations before use. Check `modeler.info` for `backends.organic`
and `backends.xatlas`. All built-in geometry backends are part of the standard
installation. Missing backends indicate an incomplete installation and return
`BACKEND_UNAVAILABLE`; ask the local operator to repair it. Do not modify the engine
or install dependencies automatically to complete a modeling request.

1. Create closed body, neck and head volumes. Move them into contact. Use
   `mesh.organic_union` with scene_id, object_ids, voxel_size and blend_radius.
   Sources remain in the scene. Inspect the result before deleting them. The union
   creates new geometry without UV or material. Smaller voxel size costs more resources;
   details near that size can disappear. Separate inputs can remain separate components.
2. Use `deform.local` with object_id, center and radius to change proportions. Optional
   displacement, scale, axis and angle_degrees control a local affine edit. The falloff
   is smooth at the radius. Coordinates are world coordinates; transforms are already baked.
3. Use `sculpt.brush` for inflate, deflate, move, smooth or sharpen. Inflate/deflate strength
   is a positive distance. Smooth/sharpen strength is in (0,1]. Move uses displacement.
   Brushes preserve UV seams and triangle topology. Subdivide before small features.
   Keep strokes small; large strokes can cause self-intersections or affect both sides
   of a thin surface. Current validation does not detect every self-intersection.
4. Duplicate before `mesh.remesh`. Choose voxel_size smaller than the details to retain.
   Optional reduction_percent uses conservative simplification. Remesh keeps ID/material
   but clears UV. It uses a uniform grid and requires closed oriented input. It is not
   an automatic repair tool for arbitrary holes or intersecting surfaces.
5. Use `uv.unwrap`. Optional face_groups must partition all current face indices.
   Group boundaries force cuts; xatlas can add more cuts. Density weights allocate
   relative texel area. Weight 4 gives roughly twice the linear density of weight 1.
   Inspect returned distortion. Anisotropy 1 means equal directional stretch.
   Set max_anisotropy to reject excessive stretch. Face order may change after unwrap.
6. Assign a dedicated material and load a workspace image with `texture.load`.
   `texture.project` requires object_id, texture_id, center, radius and size [width,height].
   Perpendicular u_axis/v_axis orient the image. It blends source alpha and opacity
   with smooth region falloff into a new managed base-color PNG. It changes the assigned
   material, including other objects sharing it. Use an atlas without overlapping regions.
   Projection has no occlusion test. front_only checks face direction, not visibility.
   Four-pixel gutters reduce filtering seams; arbitrary old seams are not repaired.
7. Use `scene.compare_reference` with a workspace-relative reference_path. Mode
   side_by_side writes two panels; overlay uses model opacity over the photo.
   Camera parameters elevation_degrees, azimuth_degrees, zoom, offset_x and offset_y
   align the solid-color orthographic preview. Offsets are fractions of panel size.
   Elevation tilts X before azimuth rotates Z. This is manual alignment, not camera
   calibration or automatic anatomy fitting. The comparison panels use a solid-colour
   preview and do not sample the projected texture; the delivery review in the build
   steps does.

Geometry edits can enter atomic batches. Texture projection and comparison write files
and cannot. After modeling, validate closure if needed, run the texture review gate with
`sample_textures=true` views from every side, then export and reopen the artifact when
file access is available. Report resolution and renderer limits instead of claiming
preservation of every small feature.
