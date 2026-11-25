import importlib.util
from typing import Annotated, Any, Literal, cast

import numpy as np
import trimesh
from pydantic import Field

from scissors.api.errors import ScissorsError
from scissors.api.modeling import register_modeling
from scissors.api.registry import OperationRegistry
from scissors.api.selections import GeometrySelection
from scissors.core.engine import Engine, identifier
from scissors.core.export import artifact, preview
from scissors.core.materials import Material
from scissors.core.mesh import compute_normals, topology_mesh
from scissors.core.persistence import atomic_write, json_bytes, read_json
from scissors.core.rendering_fast import vtk_capability
from scissors.core.scene import Scene
from scissors.core.simplification import available as simplification_available
from scissors.core.simplification import simplify_mesh
from scissors.core.solids import orient
from scissors.core.textures import checker, load_image
from scissors.core.uv import generate_uv, uv_distortion
from scissors.core.uv_density import density_report, fit_density, prepare_density_uv
from scissors.core.validation import validate_mesh

Positive = Annotated[float, Field(gt=0, allow_inf_nan=False)]
Finite = Annotated[float, Field(allow_inf_nan=False)]
Segments = Annotated[int, Field(ge=3, le=512)]
Color = Annotated[list[Annotated[float, Field(ge=0, le=1)]], Field(min_length=4, max_length=4)]
RGB = Annotated[list[Annotated[float, Field(ge=0, le=1)]], Field(min_length=3, max_length=3)]
ByteColor = Annotated[list[Annotated[int, Field(ge=0, le=255)]], Field(min_length=4, max_length=4)]
Dimension = Annotated[int, Field(ge=1, le=4096)]


def register_native(registry: OperationRegistry, engine: Engine) -> None:
    def add(
        name: str,
        fn: Any,
        description: str,
        write: bool = True,
        permissions: list[str] | None = None,
    ) -> None:
        registry.add_function(name, fn, description, write, permissions)

    def budget(vertices: int, faces: int) -> None:
        if vertices > engine.settings.max_vertices or faces > engine.settings.max_faces:
            raise ScissorsError("RESOURCE_LIMIT", "Requested geometry exceeds configured limits")
        if vertices * 384 + faces * 192 > engine.settings.max_memory_bytes:
            raise ScissorsError(
                "RESOURCE_LIMIT", "Requested geometry exceeds estimated memory budget"
            )

    def info() -> dict[str, Any]:
        return {
            "name": "Scissors",
            "version": "0.1.0",
            "api_version": "1.0",
            "workspace": str(engine.root),
            "plugins_dir": str(engine.settings.plugins_dir.expanduser().resolve()),
            "coordinates": "right-handed Z-up",
            "limits": engine.settings.model_dump(mode="json"),
            "backends": {
                "boolean": importlib.util.find_spec("manifold3d") is not None,
                "xatlas": importlib.util.find_spec("xatlas") is not None,
                "simplify": simplification_available(),
                "import_fbx": importlib.util.find_spec("ufbx") is not None,
                "preserve_fbx_rig": importlib.util.find_spec("ufbx") is not None,
                "organic": simplification_available(),
                "preview_vtk": vtk_capability()[0],
                "preview_fallback": "pillow",
            },
            "operation_count": len(registry.operations),
            "plugin_isolation": "subprocess; NOT an OS security sandbox",
        }

    def scene_create(
        name: str = "Untitled",
        units: Literal["meters", "millimeters", "centimeters"] = "meters",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return engine.create_scene(name, units, metadata)

    def scene_list() -> dict[str, Any]:
        return {
            "scenes": [
                {"id": s.id, "name": s.name, "object_count": len(s.objects)}
                for s in engine.scenes.values()
            ]
        }

    def scene_inspect(scene_id: str) -> dict[str, Any]:
        return engine.scene(scene_id).summary()

    def scene_delete(scene_id: str) -> dict[str, Any]:
        engine.scene(scene_id)
        del engine.scenes[scene_id]
        return {"deleted": scene_id}

    def scene_clear(scene_id: str) -> dict[str, Any]:
        scene = engine.scene(scene_id)
        scene.objects.clear()
        scene.materials.clear()
        scene.fbx_documents.clear()
        return scene.summary()

    def scene_save(scene_id: str, output: str | None = None) -> dict[str, Any]:
        scene = engine.scene(scene_id)
        path = engine.artifact_path(output or f"scenes/{scene_id}.json")
        data = {"format_version": 1, "scene": scene.model_dump(), "textures": engine.textures}
        atomic_write(path, json_bytes(data), engine.settings.max_file_bytes)
        return artifact(path, "scissors-scene")

    def scene_load(path: str) -> dict[str, Any]:
        data = read_json(engine.path(path), engine.settings.max_file_bytes)
        if data.get("format_version") != 1 or data["scene"].get("format_version") != 1:
            raise ScissorsError("INCOMPATIBLE_FORMAT", "Unsupported scene version")
        scene = Scene.model_validate(data["scene"])
        engine.scenes[scene.id] = scene
        engine.textures.update(data.get("textures", {}))
        engine.check_state()
        return scene.summary()

    def scene_export(
        scene_id: str,
        output: str,
        format: Literal["glb", "gltf", "obj", "stl", "ply", "dae", "usdz", "fbx"] = "glb",
        only_object_ids: Annotated[list[str], Field(min_length=1, max_length=4096)] | None = None,
        exclude_object_ids: Annotated[list[str], Field(max_length=4096)] | None = None,
        export_transform: Annotated[
            list[Annotated[list[Finite], Field(min_length=4, max_length=4)]],
            Field(min_length=4, max_length=4),
        ]
        | None = None,
        root_name: str | None = None,
        split_materials: bool = False,
        lod_reductions: Annotated[
            list[Annotated[float, Field(gt=0, lt=100, allow_inf_nan=False)]], Field(max_length=8)
        ]
        | None = None,
        lod_max_error_relative: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)] = 0.01,
        lod_require_target: bool = False,
    ) -> dict[str, Any]:
        from scissors.core.delivery import export_delivery

        return export_delivery(
            engine,
            scene_id,
            output,
            format,
            only_object_ids,
            exclude_object_ids,
            export_transform,
            root_name,
            split_materials,
            lod_reductions,
            lod_max_error_relative,
            lod_require_target,
        )

    def scene_preview(
        scene_id: str,
        output: str = "previews/scene.png",
        width: Dimension = 512,
        height: Dimension = 512,
        wireframe: bool = False,
        azimuth_degrees: Finite = 35,
        elevation_degrees: Finite = 65,
        zoom: Annotated[float, Field(gt=0, le=20, allow_inf_nan=False)] = 1,
        offset_x: Annotated[float, Field(ge=-2, le=2, allow_inf_nan=False)] = 0,
        offset_y: Annotated[float, Field(ge=-2, le=2, allow_inf_nan=False)] = 0,
        clip_axis: Literal["x", "y", "z"] | None = None,
        clip_position: Finite | None = None,
        clip_keep: Literal["positive", "negative"] = "positive",
        only_object_ids: list[str] | None = None,
        exclude_object_ids: list[str] | None = None,
        sample_textures: bool = False,
        projection: Literal["orthographic", "perspective"] | None = None,
        camera_position: Annotated[list[Finite], Field(min_length=3, max_length=3)] | None = None,
        camera_target: Annotated[list[Finite], Field(min_length=3, max_length=3)] | None = None,
        camera_up: Annotated[list[Finite], Field(min_length=3, max_length=3)] | None = None,
        fov: Annotated[float, Field(gt=1, lt=179, allow_inf_nan=False)] = 45,
        near: Positive = 0.001,
        far: Positive | None = None,
        light_direction: Annotated[list[Finite], Field(min_length=3, max_length=3)] | None = None,
        ambient: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)] = 0.35,
        light_strength: Annotated[float, Field(ge=0, le=10, allow_inf_nan=False)] = 0.65,
        transparent: bool = False,
        background: RGB | None = None,
        renderer: Literal["auto", "vtk", "pillow"] = "auto",
        render_pass: Literal["color", "depth", "normal"] = "color",
        orthographic_scale: Positive | None = None,
        highlights: Annotated[list[GeometrySelection], Field(max_length=64)] | None = None,
    ) -> dict[str, Any]:
        return preview(
            engine,
            scene_id,
            output,
            width,
            height,
            wireframe,
            azimuth_degrees=azimuth_degrees,
            elevation_degrees=elevation_degrees,
            zoom=zoom,
            offset_x=offset_x,
            offset_y=offset_y,
            clip_axis=clip_axis,
            clip_position=clip_position,
            clip_keep=clip_keep,
            only_object_ids=only_object_ids,
            exclude_object_ids=exclude_object_ids,
            sample_textures=sample_textures,
            projection=projection,
            camera_position=camera_position,
            camera_target=camera_target,
            camera_up=camera_up,
            fov=fov,
            near=near,
            far=far,
            light_direction=light_direction,
            ambient=ambient,
            light_strength=light_strength,
            transparent=transparent,
            background=background,
            renderer=renderer,
            render_pass=render_pass,
            orthographic_scale=orthographic_scale,
            highlights=[
                GeometrySelection.model_validate(value).model_dump() for value in highlights
            ]
            if highlights is not None
            else None,
        )

    def cube(
        scene_id: str,
        size: Positive = 1.0,
        name: str = "Cube",
        capped: bool = True,
        axis: Literal["x", "y", "z"] = "z",
        pivot: Literal["base", "center"] = "center",
    ) -> dict[str, Any]:
        budget(8, 12)
        mesh = trimesh.creation.box(extents=[size] * 3)
        if not capped:
            mesh.update_faces(np.abs(mesh.face_normals[:, 2]) < 0.9)
            mesh.remove_unreferenced_vertices()
        return engine.add_mesh(scene_id, orient(mesh, axis, pivot), name, "cube")

    def sphere(
        scene_id: str,
        radius: Positive = 1.0,
        subdivisions: Annotated[int, Field(ge=0, le=6)] = 3,
        name: str = "Sphere",
        segments: Segments | None = None,
        axis: Literal["x", "y", "z"] = "z",
        pivot: Literal["base", "center"] = "center",
        capped: bool = True,
    ) -> dict[str, Any]:
        if segments is None:
            budget(10 * 4**subdivisions + 2, 20 * 4**subdivisions)
            mesh = trimesh.creation.icosphere(subdivisions, radius)
        else:
            if subdivisions != 3:
                raise ValueError("Choose either segments or nondefault subdivisions")
            # Trimesh uses twice the supplied longitude count; budget before allocation.
            budget(2 * (segments + 2) ** 2, 4 * (segments + 2) ** 2)
            mesh = trimesh.creation.uv_sphere(radius=radius, count=[segments, segments])
        if not capped:
            from scissors.core.solids import open_poles

            mesh = open_poles(mesh)
        return engine.add_mesh(scene_id, orient(mesh, axis, pivot), name, "sphere")

    def cylinder(
        scene_id: str,
        radius: Positive = 1.0,
        height: Positive = 2.0,
        sections: Segments = 64,
        height_segments: Annotated[int, Field(ge=1, le=256)] = 8,
        name: str = "Cylinder",
        segments: Segments | None = None,
        capped: bool = True,
        axis: Literal["x", "y", "z"] = "z",
        pivot: Literal["base", "center"] = "center",
    ) -> dict[str, Any]:
        if segments is not None:
            if sections != 64 and sections != segments:
                raise ValueError("sections and segments must agree")
            sections = segments
        # Revolved profile gives enough vertical rings for progressive deformations.
        budget(sections * (height_segments + 1) + 2, sections * (height_segments + 1) * 2)
        profile = [[0, -height / 2], [radius, -height / 2]]
        profile += [
            [radius, z] for z in np.linspace(-height / 2, height / 2, height_segments + 1)[1:]
        ]
        profile.append([0, height / 2])
        mesh = trimesh.creation.revolve(profile, sections=sections)
        if not capped:
            mesh.update_faces(np.abs(mesh.face_normals[:, 2]) < 0.9)
            mesh.remove_unreferenced_vertices()
        return engine.add_mesh(scene_id, orient(mesh, axis, pivot), name, "cylinder")

    def cone(
        scene_id: str,
        radius: Positive = 1.0,
        height: Positive = 2.0,
        sections: Segments = 64,
        name: str = "Cone",
        segments: Segments | None = None,
        capped: bool = True,
        axis: Literal["x", "y", "z"] = "z",
        pivot: Literal["base", "center"] = "base",
    ) -> dict[str, Any]:
        if segments is not None:
            if sections != 64 and sections != segments:
                raise ValueError("sections and segments must agree")
            sections = segments
        budget(sections + 2, sections * 2)
        mesh = trimesh.creation.cone(radius, height, sections)
        if not capped:
            mesh.update_faces(mesh.face_normals[:, 2] > -0.9)
            mesh.remove_unreferenced_vertices()
        return engine.add_mesh(scene_id, orient(mesh, axis, pivot), name, "cone")

    def plane(
        scene_id: str,
        size: Positive = 2.0,
        name: str = "Plane",
        axis: Literal["x", "y", "z"] = "z",
        pivot: Literal["base", "center"] = "center",
        capped: Literal[True] = True,
    ) -> dict[str, Any]:
        budget(4, 2)
        h = size / 2
        mesh = trimesh.Trimesh(
            vertices=[[-h, -h, 0], [h, -h, 0], [h, h, 0], [-h, h, 0]],
            faces=[[0, 1, 2], [0, 2, 3]],
            process=False,
        )
        return engine.add_mesh(scene_id, orient(mesh, axis, pivot), name, "plane")

    def torus(
        scene_id: str,
        major_radius: Positive = 1.0,
        minor_radius: Positive = 0.25,
        major_sections: Segments = 64,
        minor_sections: Segments = 24,
        name: str = "Torus",
        arc: Annotated[float, Field(gt=0, le=360, allow_inf_nan=False)] = 360,
        twist: Annotated[int, Field(ge=0, le=31)] = 0,
        capped: bool = True,
        axis: Literal["x", "y", "z"] = "z",
        pivot: Literal["base", "center"] = "center",
    ) -> dict[str, Any]:
        if minor_radius >= major_radius:
            raise ValueError("minor_radius must be smaller than major_radius")
        n = major_sections + (1 if arc != 360 else 0)
        cap_vertices = 2 if arc != 360 and capped else 0
        cap_faces = 2 * minor_sections if arc != 360 and capped else 0
        strands = 2 if twist and twist % 2 == 0 else 1
        budget(
            strands * (n * minor_sections + cap_vertices),
            strands * (major_sections * minor_sections * 2 + cap_faces),
        )
        if arc != 360 or twist:
            from scissors.core.solids import orient
            from scissors.core.solids import torus as torus_geometry

            mesh = torus_geometry(
                major_radius, minor_radius, major_sections, minor_sections, arc, twist, capped
            )
            return engine.add_mesh(scene_id, orient(mesh, axis, pivot), name, "torus")
        if axis != "z" or pivot != "center":
            from scissors.core.solids import orient

            mesh = trimesh.creation.torus(
                major_radius,
                minor_radius,
                major_sections=major_sections,
                minor_sections=minor_sections,
            )
            return engine.add_mesh(scene_id, orient(mesh, axis, pivot), name, "torus")
        return engine.add_mesh(
            scene_id,
            trimesh.creation.torus(
                major_radius,
                minor_radius,
                major_sections=major_sections,
                minor_sections=minor_sections,
            ),
            name,
            "torus",
        )

    def custom(
        scene_id: str, vertices: list[list[Finite]], faces: list[list[int]], name: str = "Mesh"
    ) -> dict[str, Any]:
        if len(vertices) > engine.settings.max_vertices or len(faces) > engine.settings.max_faces:
            raise ScissorsError("RESOURCE_LIMIT", "Mesh exceeds limits")
        if (
            not vertices
            or not faces
            or any(len(v) != 3 for v in vertices)
            or any(len(f) != 3 for f in faces)
        ):
            raise ScissorsError("GEOMETRY_ERROR", "Vertices and triangular faces are required")
        if min(min(f) for f in faces) < 0 or max(max(f) for f in faces) >= len(vertices):
            raise ScissorsError("GEOMETRY_ERROR", "Face index outside vertex array")
        return engine.add_mesh(
            scene_id, trimesh.Trimesh(vertices=vertices, faces=faces, process=False), name
        )

    def inspect_mesh(object_id: str) -> dict[str, Any]:
        return engine.object(object_id)[1].summary()

    def mesh_data(
        object_id: str,
        offset: Annotated[int, Field(ge=0)] = 0,
        limit: Annotated[int, Field(ge=1, le=5000)] = 100,
    ) -> dict[str, Any]:
        obj = engine.object(object_id)[1]
        return {
            "object_id": obj.id,
            "vertices": obj.vertices[offset : offset + limit],
            "faces": obj.faces[offset : offset + limit],
            "normals": obj.normals[offset : offset + limit],
            "uv": obj.uv[offset : offset + limit] if obj.uv is not None else None,
            "offset": offset,
            "limit": limit,
            "transform": obj.transform,
        }

    def delete(
        object_id: str | None = None,
        object_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Delete one object or a batch wrapped in a single rollback point."""
        if (object_id is None) == (object_ids is None):
            raise ValueError("Provide object_id or object_ids, not both")
        ids = [object_id] if object_id is not None else list(object_ids or [])
        if not ids:
            raise ValueError("object_ids must not be empty")
        grouped: dict[str, list[str]] = {}
        for oid in ids:
            scene, _ = engine.object(oid)
            grouped.setdefault(scene.id, []).append(oid)
        deleted: list[str] = []
        for scene_id, members in grouped.items():
            deleted.extend(engine.remove_objects(scene_id, members))
        return {
            "deleted": object_id if object_id is not None else deleted,
            "deleted_object_ids": deleted,
        }

    def duplicate(object_id: str, name: str | None = None) -> dict[str, Any]:
        return engine.clone_object(object_id, name).summary()

    def translate(object_id: str, x: Finite = 0, y: Finite = 0, z: Finite = 0) -> dict[str, Any]:
        return engine.transform(object_id, trimesh.transformations.translation_matrix([x, y, z]))

    def rotate(
        object_id: str, axis: Literal["x", "y", "z"] = "z", angle_degrees: Finite = 0
    ) -> dict[str, Any]:
        vector = np.eye(3)["xyz".index(axis)]
        return engine.transform(
            object_id,
            trimesh.transformations.rotation_matrix(
                np.radians(angle_degrees), vector, engine.object(object_id)[1].pivot
            ),
        )

    def scale(object_id: str, x: Positive = 1, y: Positive = 1, z: Positive = 1) -> dict[str, Any]:
        return engine.transform(object_id, np.diag([x, y, z, 1]))

    def mirror(
        object_id: str,
        axis: Literal["x", "y", "z"] = "x",
        plane: Finite = 0,
        duplicate: bool = True,
        name: str | None = None,
        copy_material: bool = True,
        normal: Annotated[list[Finite], Field(min_length=3, max_length=3)] | None = None,
        point: Annotated[list[Finite], Field(min_length=3, max_length=3)] | None = None,
    ) -> dict[str, Any]:
        from scissors.core.placement import reflection, unit

        # Reflection inverts orientation; the shared transform reverses face winding.
        scene, source = engine.object(object_id)
        direction = unit(np.asarray(normal)) if normal is not None else np.eye(3)["xyz".index(axis)]
        origin = np.asarray(point) if point is not None else direction * plane
        matrix = reflection(direction, origin)
        obj = (
            engine.clone_object(object_id, name or f"{source.name} mirrored")
            if duplicate
            else source
        )
        if duplicate and not copy_material:
            for target in [obj, *engine.descendants(scene, obj.id)]:
                target.material_id = None
        engine.transform(obj.id, matrix)
        if name is not None:
            obj.name = name
        warnings = [
            "Mirroring reverses face winding so normals stay outward. UV is copied "
            "unchanged, so text and asymmetric textures read mirrored on the result."
        ]
        return {
            **obj.summary(),
            "mirrored_object_id": obj.id,
            "source_object_id": source.id,
            "axis": axis,
            "plane": plane,
            "duplicated": duplicate,
            "plane_normal": direction.tolist(),
            "plane_point": origin.tolist(),
            "warnings": warnings,
        }

    def normals(object_id: str) -> dict[str, Any]:
        _, obj = engine.object(object_id)
        obj.normals = compute_normals(obj.geometry()).tolist()
        obj.metadata.pop("normal_method", None)
        obj.metadata.pop("normal_angle_degrees", None)
        return obj.summary()

    def merge(
        scene_id: str, object_ids: Annotated[list[str], Field(min_length=1)], name: str = "Merged"
    ) -> dict[str, Any]:
        objs = [engine.object(oid) for oid in object_ids]
        if any(s.id != scene_id for s, _ in objs):
            raise ValueError("All objects must belong to the destination scene")
        result = engine.add_mesh(
            scene_id,
            cast(trimesh.Trimesh, trimesh.util.concatenate([o.geometry() for _, o in objs])),
            name,
        )
        result["warnings"] = ["Merge creates geometry only; regenerate UV and assign material"]
        return result

    def subdivide(
        object_id: str, iterations: Annotated[int, Field(ge=1, le=4)] = 1
    ) -> dict[str, Any]:
        _, obj = engine.object(object_id)
        if len(obj.faces) * 4**iterations > engine.settings.max_faces:
            raise ScissorsError("RESOURCE_LIMIT", "Subdivision exceeds face limit")
        mesh = obj.geometry()
        for _ in range(iterations):
            mesh = mesh.subdivide()
        obj.replace(mesh)
        engine.checked(obj)
        return {**obj.summary(), "warnings": ["Subdivision clears UV; regenerate before texturing"]}

    def simplify(
        object_id: str,
        reduction_percent: Annotated[float, Field(gt=0, lt=100, allow_inf_nan=False)],
        uv_policy: Literal["preserve", "discard"] = "preserve",
        max_error_relative: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)] = 0.01,
        require_target: bool = False,
    ) -> dict[str, Any]:
        return simplify_mesh(
            engine.object(object_id)[1],
            engine.settings,
            reduction_percent,
            uv_policy,
            max_error_relative,
            require_target,
        )

    def validate(
        object_id: str,
        require_closed: bool = False,
        require_connected: bool = False,
        check_self_intersections: bool = False,
        include_selections: bool = False,
    ) -> dict[str, Any]:
        return validate_mesh(
            engine.object(object_id)[1],
            engine.settings,
            require_closed,
            require_connected,
            check_self_intersections,
            include_selections,
        )

    def uv_generate(
        object_id: str | None = None,
        method: Literal["auto", "box", "planar", "cylindrical", "spherical", "xatlas"] = "auto",
        object_ids: Annotated[list[str], Field(min_length=1, max_length=4096)] | None = None,
        pixels_per_meter: Positive | None = None,
        texture_resolution: Annotated[list[Dimension], Field(min_length=2, max_length=2)]
        | None = None,
        density_mode: Literal["atlas", "repeat"] = "atlas",
        atlas_region: Annotated[
            list[Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]],
            Field(min_length=4, max_length=4),
        ]
        | None = None,
        padding: Annotated[int, Field(ge=0, le=64)] = 0,
        preserve_uv: bool = False,
    ) -> dict[str, Any]:
        if (object_id is None) == (object_ids is None):
            raise ValueError("Provide object_id or object_ids, not both")
        if pixels_per_meter is not None:
            if texture_resolution is None:
                raise ValueError("Density targets require texture_resolution [width,height]")
            ids = object_ids if object_ids is not None else [cast(str, object_id)]
            if len(set(ids)) != len(ids):
                raise ValueError("Density object IDs must be unique")
            pairs = [engine.object(oid) for oid in ids]
            if len({scene.id for scene, _ in pairs}) != 1:
                raise ValueError("Density objects must belong to one scene")
            if any(obj.kind != "mesh" for _, obj in pairs):
                raise ValueError("Density targets require mesh objects")
            if (
                sum(len(obj.vertices) * 768 + len(obj.faces) * 4608 for _, obj in pairs)
                > engine.settings.max_memory_bytes
            ):
                raise ScissorsError("RESOURCE_LIMIT", "UV density selection exceeds memory budget")
            objects = [obj.model_copy(deep=True) for _, obj in pairs]
            for obj in objects:
                if not preserve_uv:
                    budget(len(obj.faces) * 3, len(obj.faces))
                    prepare_density_uv(obj, method, texture_resolution, engine.settings)
            result = fit_density(
                objects,
                pairs[0][0].units,
                texture_resolution,
                pixels_per_meter,
                density_mode,
                atlas_region or [0, 0, 1, 1],
                padding,
                engine.settings,
            )
            for obj in objects:
                engine.checked(obj)
            for obj in objects:
                pairs[0][0].objects[obj.id] = obj
            return {
                "scene_id": pairs[0][0].id,
                "density": result,
                "object_ids": ids,
                "geometry_positions_preserved": True,
            }
        if (
            object_ids is not None
            or texture_resolution is not None
            or atlas_region is not None
            or padding
            or preserve_uv
            or density_mode != "atlas"
        ):
            raise ValueError("Density options require pixels_per_meter")
        assert object_id is not None
        _, obj = engine.object(object_id)
        if method != "planar" and obj.metadata.get("primitive") != "plane":
            budget(len(obj.faces) * 3, len(obj.faces))
        generate_uv(obj, method, engine.settings)
        engine.checked(obj)
        return {**obj.summary(), "validation": validate_mesh(obj, engine.settings)}

    def uv_inspect(
        object_id: str,
        texture_resolution: Annotated[list[Dimension], Field(min_length=2, max_length=2)]
        | None = None,
    ) -> dict[str, Any]:
        scene, obj = engine.object(object_id)
        if texture_resolution is not None and (
            len(obj.vertices) * 384 + len(obj.faces) * 4608 > engine.settings.max_memory_bytes
        ):
            raise ScissorsError("RESOURCE_LIMIT", "Density inspection exceeds memory budget")
        return {
            "object_id": obj.id,
            "has_uv": obj.uv is not None,
            "count": len(obj.uv) if obj.uv else 0,
            "bounds": [np.min(obj.uv, axis=0).tolist(), np.max(obj.uv, axis=0).tolist()]
            if obj.uv
            else None,
            "validation": validate_mesh(obj, engine.settings),
            "distortion": uv_distortion(obj),
            **(
                {"density": density_report(obj, scene.units, texture_resolution)}
                if texture_resolution is not None
                else {}
            ),
        }

    def material_create(
        scene_id: str,
        name: str = "Material",
        base_color: Color | None = None,
        metallic: Annotated[float, Field(ge=0, le=1)] = 0,
        roughness: Annotated[float, Field(ge=0, le=1)] = 0.7,
        alpha: Annotated[float, Field(ge=0, le=1)] = 1,
        double_sided: bool = False,
        emissive: RGB | None = None,
    ) -> dict[str, Any]:
        mat = Material(
            id=identifier("mat"),
            name=name,
            base_color=base_color if base_color is not None else [0.7, 0.7, 0.7, 1],
            metallic=metallic,
            roughness=roughness,
            alpha=alpha,
            double_sided=double_sided,
            emissive=emissive if emissive is not None else [0, 0, 0],
        )
        engine.scene(scene_id).materials[mat.id] = mat
        return {**mat.model_dump(), "material_id": mat.id}

    def material_get(material_id: str) -> dict[str, Any]:
        return engine.material(material_id)[1].model_dump()

    def material_list(scene_id: str) -> dict[str, Any]:
        return {"materials": [m.model_dump() for m in engine.scene(scene_id).materials.values()]}

    def material_update(material_id: str, properties: dict[str, Any]) -> dict[str, Any]:
        scene, mat = engine.material(material_id)
        if set(properties) - {
            "name",
            "base_color",
            "metallic",
            "roughness",
            "alpha",
            "double_sided",
            "emissive",
        }:
            raise ValueError("Unsupported material properties; use texture.assign for textures")
        updated = Material.model_validate({**mat.model_dump(), **properties})
        if any(c < 0 or c > 1 for c in [*updated.base_color, *updated.emissive]):
            raise ValueError("Colors must be between zero and one")
        scene.materials[mat.id] = updated
        return updated.model_dump()

    def material_assign(object_id: str, material_id: str) -> dict[str, Any]:
        scene, obj = engine.object(object_id)
        if engine.material(material_id)[0].id != scene.id:
            raise ValueError("Material and object must belong to the same scene")
        obj.material_id = material_id
        return obj.summary()

    def texture_checker(
        width: Dimension = 256,
        height: Dimension = 256,
        cells: Annotated[int, Field(ge=1, le=256)] = 8,
        color_a: ByteColor | None = None,
        color_b: ByteColor | None = None,
        output: str | None = None,
    ) -> dict[str, Any]:
        return checker(
            engine,
            width,
            height,
            cells,
            color_a if color_a is not None else [255, 255, 255, 255],
            color_b if color_b is not None else [40, 70, 150, 255],
            output,
        )

    def texture_load(path: str) -> dict[str, Any]:
        return load_image(engine, path)

    def texture_assign(
        material_id: str,
        texture_id: str,
        slot: Literal[
            "base_color", "normal", "metallic_roughness", "emissive", "occlusion"
        ] = "base_color",
    ) -> dict[str, Any]:
        if texture_id not in engine.textures:
            raise ScissorsError("TEXTURE_NOT_FOUND", "Texture does not exist")
        _, mat = engine.material(material_id)
        setattr(mat, f"{slot}_texture", texture_id)
        return mat.model_dump()

    def batch(operations: list[dict[str, Any]], atomic: bool = True) -> dict[str, Any]:
        return registry.batch(operations, atomic)

    add("modeler.info", info, "Runtime capabilities, limits and backend availability.", False)
    add("scene.create", scene_create, "Create a right-handed Z-up scene with stable ID.")
    add("scene.list", scene_list, "List scene identifiers without large mesh arrays.", False)
    for name in ("get", "inspect"):
        add(f"scene.{name}", scene_inspect, "Inspect scene objects and materials compactly.", False)
    add("scene.delete", scene_delete, "Delete a scene and its objects.")
    add("scene.clear", scene_clear, "Remove all objects and materials from a scene.")
    add(
        "scene.save",
        scene_save,
        "Save a versioned scene snapshot; texture paths stay workspace relative.",
        True,
        ["filesystem.write"],
    )
    add(
        "scene.load",
        scene_load,
        "Load a scene snapshot from this workspace, preserving identifiers.",
    )
    add(
        "scene.export",
        scene_export,
        "Export GLB/glTF/OBJ/STL/PLY/DAE/USDZ/binary FBX with selection, root transform and LODs. "
        "Static FBX exports Y-up. "
        "Retained FBX rigs require complete FBX export, unchanged placement/materials, "
        "and no split, root rename, LODs or export transform.",
        True,
        ["filesystem.write"],
    )
    add(
        "scene.preview",
        scene_preview,
        "Render a PNG preview with the fast backends. Camera keeps world +Z as screen up and "
        "never rolls: azimuth 0 looks along -Y, 90 along +X, 180 along +Y, 270 along -X, and "
        "elevation 90 looks straight down. zoom and panel offsets frame the subject. "
        "Optional axis-aligned section hides clipped triangles without changing framing, and "
        "only_object_ids or exclude_object_ids narrow the render. sample_textures draws "
        "base-colour textures so labels and screen pages are readable; alpha is not blended. "
        "renderer=auto uses the VTK offscreen renderer when an OpenGL context exists and the "
        "Pillow painter otherwise; vtk or pillow force one backend. The result reports the "
        "backend in renderer. render_pass=depth writes a 16-bit grayscale PNG and a "
        ".depth.npz sidecar with float32 camera distance, coverage, near and far; "
        "render_pass=normal writes world normals encoded as (normal+1)/2 in RGB. Both "
        "diagnostic passes need the VTK backend.",
        False,
        ["filesystem.write"],
    )
    registry.operations["scene.preview"].examples = [
        {"scene_id": "SCENE_ID_FROM_PREVIOUS_RESULT", "output": "previews/front.png"},
        {
            "scene_id": "SCENE_ID_FROM_PREVIOUS_RESULT",
            "output": "previews/section.png",
            "azimuth_degrees": 180,
            "elevation_degrees": 0,
            "clip_axis": "y",
            "clip_keep": "negative",
        },
    ]
    for name, function in {
        "cube": cube,
        "sphere": sphere,
        "cylinder": cylinder,
        "cone": cone,
        "plane": plane,
        "torus": torus,
    }.items():
        add(
            f"mesh.create_{name}",
            function,
            f"Create a {name} primitive; returns compact statistics.",
        )
    add("mesh.create", custom, "Create a triangular mesh from explicit arrays; prefer primitives.")
    for name in ("inspect", "stats", "bounding_box", "centroid"):
        add(
            f"mesh.{name}",
            inspect_mesh,
            "Read object bounds, centroid and geometry statistics.",
            False,
        )
    add("mesh.data", mesh_data, "Read a bounded page of vertices, faces, normals and UV.", False)
    for name, fn in {
        "delete": delete,
        "duplicate": duplicate,
        "translate": translate,
        "rotate": rotate,
        "scale": scale,
        "recalculate_normals": normals,
        "merge": merge,
        "subdivide": subdivide,
    }.items():
        add(f"mesh.{name}", fn, f"{name.replace('_', ' ').capitalize()} mesh geometry.")
    registry.operations["mesh.delete"].description = (
        "Delete one object with object_id, or many with object_ids in one call. A batch "
        "validates every ID first, deletes inside one rollback point and writes the state "
        "once, so it is far faster than one call per object. Children of a deleted object are "
        "re-parented to its parent. Unknown IDs abort the whole batch."
    )
    add(
        "mesh.mirror",
        mirror,
        "Reflect a subtree across axis/plane or a plane given by normal and point. Reverses face "
        "winding so normals stay outward. duplicate=true (default) creates a new object and "
        "keeps the source; duplicate=false mirrors in place.",
    )
    registry.operations["mesh.mirror"].examples = [
        {
            "object_id": "OBJECT_ID_FROM_PREVIOUS_RESULT",
            "axis": "x",
            "plane": 0,
            "name": "Left panel",
        }
    ]
    add(
        "mesh.simplify",
        simplify,
        "Reduce faces by percentage. Preserves topology, boundaries and UV seams. "
        "Surviving vertices retain their positions and UV. Uses the included VTK backend. "
        "May stop before the target; require_target rejects partial reduction. "
        "Error is VTK's accumulated geometric estimate. It does not guarantee texture "
        "error or maximum distance between surfaces.",
    )
    registry.operations["mesh.simplify"].examples = [
        {"object_id": "OBJECT_ID_FROM_PREVIOUS_RESULT", "reduction_percent": 50}
    ]
    registry.operations["mesh.simplify"].result_schema = {
        "type": "object",
        "required": [
            "object_id",
            "vertex_count",
            "face_count",
            "original_face_count",
            "target_face_count",
            "requested_reduction_percent",
            "actual_reduction_percent",
            "target_reached",
            "uv_policy",
            "backend",
            "warnings",
        ],
        "properties": {
            "object_id": {"type": "string"},
            "vertex_count": {"type": "integer", "minimum": 1},
            "face_count": {"type": "integer", "minimum": 1},
            "original_face_count": {"type": "integer", "minimum": 1},
            "target_face_count": {"type": "integer", "minimum": 1},
            "requested_reduction_percent": {
                "type": "number",
                "exclusiveMinimum": 0,
                "exclusiveMaximum": 100,
            },
            "actual_reduction_percent": {"type": "number", "minimum": 0, "maximum": 100},
            "target_reached": {"type": "boolean"},
            "uv_policy": {"enum": ["preserve", "discard"]},
            "backend": {"const": "vtk"},
            "warnings": {"type": "array", "items": {"type": "string"}},
        },
    }
    add(
        "mesh.validate",
        validate,
        "Report errors, warnings and topology; open meshes are permitted. "
        "include_selections returns revision-bound repair targets and preview highlight hints.",
        False,
    )
    add(
        "uv.generate",
        uv_generate,
        "Generate primitive-aware UV, splitting vertices at seams. "
        "Optionally fit one or several same-scene meshes to pixels_per_meter at an explicit "
        "texture_resolution. Atlas mode packs independent islands without reducing density; "
        "repeat mode allows UV outside [0,1]. preserve_uv fits existing islands. "
        "Capacity failure leaves all objects unchanged.",
    )
    uv_operation = registry.operations["uv.generate"]
    uv_operation.parameters["oneOf"] = [
        {
            "required": ["object_id"],
            "properties": {"object_id": {"type": "string"}, "object_ids": {"type": "null"}},
        },
        {
            "required": ["object_ids", "pixels_per_meter", "texture_resolution"],
            "properties": {
                "object_id": {"type": "null"},
                "object_ids": {"type": "array"},
                "pixels_per_meter": {"type": "number"},
                "texture_resolution": {"type": "array"},
            },
        },
    ]
    uv_operation.parameters["allOf"] = [
        {
            "if": {
                "required": ["pixels_per_meter"],
                "properties": {"pixels_per_meter": {"type": "number"}},
            },
            "then": {
                "required": ["texture_resolution"],
                "properties": {"texture_resolution": {"type": "array"}},
            },
        }
    ]
    uv_operation.examples = [
        {"object_id": "OBJECT_ID_FROM_PREVIOUS_RESULT", "method": "auto"},
        {
            "object_ids": ["OBJECT_ID_FROM_PREVIOUS_RESULT"],
            "pixels_per_meter": 128,
            "texture_resolution": [2048, 2048],
            "padding": 4,
        },
    ]
    if importlib.util.find_spec("xatlas") is None:
        operation = registry.operations["uv.generate"]
        operation.description += " Missing xatlas indicates an incomplete Scissors installation."
        method_schema = operation.parameters["properties"]["method"]
        method_schema["enum"].remove("xatlas")
        method_schema["x-unavailable-values"] = {
            "xatlas": {"backend": "xatlas", "requirement": "Scissors standard installation"}
        }
    add(
        "uv.inspect",
        uv_inspect,
        "Inspect UV coverage and basic validity. With "
        "texture_resolution, measure area-based pixels per meter and pixel-space anisotropy.",
        False,
    )
    add("material.create", material_create, "Create a basic PBR material in a scene.")
    add("material.get", material_get, "Read PBR material properties.", False)
    add("material.list", material_list, "List scene materials.", False)
    add("material.update", material_update, "Update validated PBR properties.")
    add("material.assign", material_assign, "Assign a scene material to an object.")
    for name in ("create", "generate_checker"):
        add(
            f"texture.{name}",
            texture_checker,
            "Generate a deterministic RGBA checker PNG.",
            True,
            ["filesystem.write"],
        )
    add(
        "texture.load",
        texture_load,
        "Import an image inside the workspace as a managed PNG.",
        True,
        ["filesystem.write"],
    )
    add(
        "texture.assign",
        texture_assign,
        "Assign base color, normal, metallic/roughness, emissive or occlusion texture.",
    )
    add("operations.batch", batch, "Execute up to 100 operations, optionally atomically.")
    register_modeling(registry, engine)

    def boolean(
        scene_id: str,
        object_ids: Annotated[list[str], Field(min_length=2, max_length=4096)],
        mode: Literal["union", "difference", "intersection"] = "union",
        name: str = "Boolean",
        preserve_attributes: bool = True,
        material_policy: Literal["first", "source"] = "first",
        cut_material_id: str | None = None,
        cut_uv: Literal["planar", "cutter"] = "planar",
        uv_scale: Positive = 1,
        delete_inputs: bool = False,
    ) -> dict[str, Any]:
        from scissors.core.geometry import run_boolean

        engine.scene(scene_id)
        if importlib.util.find_spec("manifold3d") is None:
            raise ScissorsError(
                "BACKEND_UNAVAILABLE",
                "Repair the Scissors installation to restore the manifold3d backend",
                {"backend": "manifold3d", "requirement": "Scissors standard installation"},
            )
        if len(set(object_ids)) != len(object_ids):
            raise ValueError("Boolean operands must contain unique object IDs")
        if any(engine.object(oid)[0].id != scene_id for oid in object_ids):
            raise ValueError("Boolean operands must belong to the selected scene")
        if any(engine.object(oid)[1].kind != "mesh" for oid in object_ids):
            raise ValueError("Boolean operands must be meshes")
        meshes = [topology_mesh(engine.object(oid)[1].geometry()) for oid in object_ids]
        if not all(m.is_volume for m in meshes):
            raise ScissorsError("GEOMETRY_ERROR", "Boolean requires closed, oriented volumes")
        if preserve_attributes:
            from scissors.api.boolean import boolean_with_attributes

            result = boolean_with_attributes(
                engine,
                scene_id,
                object_ids,
                mode,
                name,
                material_policy,
                cut_material_id,
                cut_uv,
                uv_scale,
            )
        else:
            if (
                material_policy != "first"
                or cut_material_id is not None
                or cut_uv != "planar"
                or uv_scale != 1
            ):
                raise ValueError("Attribute policies require preserve_attributes=true")
            mesh = run_boolean(meshes, mode, engine.settings)
            result = engine.add_mesh(scene_id, mesh, name)
        if delete_inputs:
            result["deleted_object_ids"] = engine.remove_objects(scene_id, object_ids)
        return result

    add(
        "mesh.boolean",
        boolean,
        "Manifold boolean preserving UV/color/normals and first/source material on closed "
        "volumes. delete_inputs=true consumes the operands and reports deleted_object_ids.",
    )
    from scissors.api.design import register_design

    register_design(registry, engine)
    from scissors.api.figures import register_figures

    register_figures(registry, engine)
    from scissors.api.repair import register_repair

    register_repair(registry, engine)
    from scissors.api.mechanical import register_mechanical

    register_mechanical(registry, engine)
    from scissors.api.solids import register_solids

    register_solids(registry, engine)
    from scissors.api.editing import register_editing

    register_editing(registry, engine)

    from scissors.api.images import register_images

    register_images(registry, engine)

    from scissors.api.workflow import register_workflow

    register_workflow(registry, engine)
    from scissors.api.cut_volume import register_cut_volume

    register_cut_volume(registry, engine)
    from scissors.api.frame_opening import register_frame_opening

    register_frame_opening(registry, engine)
    from scissors.api.visibility import register_visibility

    register_visibility(registry, engine)
    from scissors.api.resize import register_resize

    register_resize(registry, engine)
    from scissors.api.components import register_components

    register_components(registry, engine)

    from scissors.api.imports import register_imports

    register_imports(registry, engine)

    from scissors.api.rendering import register_rendering

    register_rendering(registry, engine)

    from scissors.api.surfaces import register_surfaces

    register_surfaces(registry, engine)

    from scissors.api.delivery import register_delivery

    register_delivery(registry, engine)

    from scissors.api.text import register_text

    register_text(registry, engine)

    from scissors.api.bevel import register_bevel

    register_bevel(registry, engine)

    from scissors.api.inspection import register_inspection

    register_inspection(registry, engine)
