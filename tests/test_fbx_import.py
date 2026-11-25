"""Native FBX ingestion through the shared registry and real geometry child."""

import io
from pathlib import Path

import numpy as np
import pytest
import trimesh
from PIL import Image

from scissors.api.errors import ScissorsError
from scissors.core.exchange import ExchangeContext
from scissors.core.fbx import binary_file, node, prop

pytestmark = pytest.mark.integration


def fixture_fbx(
    app,
    *,
    embedded=False,
    filename="albedo.png",
    image_size=4,
    instances=1,
    distinct_materials=False,
):
    """Build a small FBX with a material, indexed UV seams and per-corner colors."""
    stream = io.BytesIO()
    Image.new("RGBA", (image_size, image_size), (220, 40, 10, 255)).save(stream, format="PNG")
    content = stream.getvalue()
    root = app.engine.root / "assets"
    root.mkdir(exist_ok=True)
    if not embedded and filename == "albedo.png":
        (root / filename).write_bytes(content)
    geometry = node(
        "Geometry",
        1,
        "Quad\x00\x01Geometry",
        "Mesh",
        children=[
            node("GeometryVersion", np.int32(124)),
            node("Vertices", np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]], dtype=float)),
            node("PolygonVertexIndex", np.array([0, 1, -3, 0, 2, -4], dtype=np.int32)),
            node(
                "LayerElementNormal",
                np.int32(0),
                children=[
                    node("MappingInformationType", "ByPolygonVertex"),
                    node("ReferenceInformationType", "Direct"),
                    node("Normals", np.array([[0, 0, 1]] * 6, dtype=float)),
                ],
            ),
            node(
                "LayerElementUV",
                np.int32(0),
                children=[
                    node("Name", "UVMap"),
                    node("MappingInformationType", "ByPolygonVertex"),
                    node("ReferenceInformationType", "IndexToDirect"),
                    node(
                        "UV", np.array([[0, 0], [1, 0], [1, 1], [0.25, 0.25], [0.75, 0.75], [0, 1]])
                    ),
                    node("UVIndex", np.arange(6, dtype=np.int32)),
                ],
            ),
            node(
                "LayerElementColor",
                np.int32(0),
                children=[
                    node("MappingInformationType", "ByPolygonVertex"),
                    node("ReferenceInformationType", "Direct"),
                    node(
                        "Colors",
                        np.array([[1, 0, 0, 1], [0, 1, 0, 1], [0, 0, 1, 1]] * 2, dtype=float),
                    ),
                ],
            ),
            node(
                "LayerElementMaterial",
                np.int32(0),
                children=[
                    node("MappingInformationType", "AllSame"),
                    node("ReferenceInformationType", "IndexToDirect"),
                    node("Materials", np.array([0], dtype=np.int32)),
                ],
            ),
            node(
                "Layer",
                np.int32(0),
                children=[
                    node("Version", np.int32(100)),
                    *[
                        node(
                            "LayerElement",
                            children=[
                                node("Type", "LayerElement" + kind),
                                node("TypedIndex", np.int32(0)),
                            ],
                        )
                        for kind in ("Normal", "UV", "Color", "Material")
                    ],
                ],
            ),
        ],
    )
    material = node(
        "Material",
        10,
        "Paint\x00\x01Material",
        "",
        children=[
            node("Version", np.int32(102)),
            node("ShadingModel", "Phong"),
            node(
                "Properties70",
                children=[
                    prop("DiffuseColor", "Color", 1.0, 1.0, 1.0),
                    prop("DiffuseFactor", "Number", 1.0),
                ],
            ),
        ],
    )
    texture = node(
        "Texture",
        11,
        "Paint\x00\x01Texture",
        "",
        children=[
            node("Type", "TextureVideoClip"),
            node("Version", np.int32(202)),
            node("FileName", filename),
            node("RelativeFilename", filename),
        ],
    )
    video = node(
        "Video",
        12,
        "Paint\x00\x01Video",
        "Clip",
        children=[
            node("Type", "Clip"),
            node("Filename", filename),
            node("RelativeFilename", filename),
            *([node("Content", content)] if embedded else []),
        ],
    )
    objects = [geometry, material, texture, video]
    if distinct_materials:
        objects.append(
            node(
                "Material",
                20,
                "Blue\x00\x01Material",
                "",
                children=[
                    node("Version", np.int32(102)),
                    node("ShadingModel", "Phong"),
                    node("Properties70", children=[prop("DiffuseColor", "Color", 0.0, 0.0, 1.0)]),
                ],
            )
        )
    connections = [node("C", "OP", 11, 10, "DiffuseColor"), node("C", "OO", 12, 11)]
    for index in range(instances):
        identifier = 100 + index
        objects.append(
            node(
                "Model",
                identifier,
                f"Quad {index}\x00\x01Model",
                "Mesh",
                children=[
                    node("Version", np.int32(232)),
                    node(
                        "Properties70",
                        children=[
                            prop("Lcl Translation", "Lcl Translation", index * 2.0, 0.0, 0.0),
                        ],
                    ),
                ],
            )
        )
        connections.extend(
            [
                node("C", "OO", 1, identifier),
                node("C", "OO", 20 if distinct_materials and index else 10, identifier),
                node("C", "OO", identifier, 0),
            ]
        )
    nodes = [
        node(
            "FBXHeaderExtension",
            children=[node("FBXHeaderVersion", np.int32(1003)), node("FBXVersion", np.int32(7400))],
        ),
        node(
            "GlobalSettings",
            children=[
                node("Version", np.int32(1000)),
                node(
                    "Properties70",
                    children=[
                        prop("UpAxis", "int", np.int32(2)),
                        prop("UpAxisSign", "int", np.int32(1)),
                        prop("FrontAxis", "int", np.int32(1)),
                        prop("FrontAxisSign", "int", np.int32(-1)),
                        prop("CoordAxis", "int", np.int32(0)),
                        prop("CoordAxisSign", "int", np.int32(1)),
                        prop("UnitScaleFactor", "double", 100.0),
                    ],
                ),
            ],
        ),
        node("Objects", children=objects),
        node("Connections", children=connections),
    ]
    context = ExchangeContext(trimesh.Scene(), app.engine.settings, "fixture")
    path = root / "fixture.fbx"
    path.write_bytes(binary_file(nodes, context))
    return path


def test_binary_embedded_images_uv_seams_colors_instances_and_restart(app):
    source = fixture_fbx(app, embedded=True, filename="C:/stale/albedo.png", instances=2)
    result = app.call("scene.import_mesh", path=str(source))
    assert len(result["object_ids"]) == 2
    assert len(result["texture_ids"]) == 1
    first, second = [app.engine.object(oid)[1] for oid in result["object_ids"]]
    assert first.uv is not None and first.vertex_colors is not None
    assert len(first.vertices) == 6
    assert second.metadata["instance_source"] == first.id
    np.testing.assert_allclose(np.asarray(second.vertices) - first.vertices, [[2, 0, 0]] * 6)
    material = app.engine.scene(result["scene_id"]).materials[first.material_id]
    texture = app.engine.textures[material.base_color_texture]
    with Image.open(app.engine.root / texture["path"]) as image:
        assert image.getpixel((0, 0)) == (220, 40, 10, 255)
    from scissors import Scissors

    root = app.engine.root
    app.close()
    with Scissors(root) as reopened:
        assert reopened.call("mesh.inspect", object_id=first.id)["has_uv"]
        assert reopened.engine.object(first.id)[1].vertex_colors == first.vertex_colors


def test_external_image_and_export_reopening(app):
    result = app.call("scene.import_mesh", path=str(fixture_fbx(app)))
    artifact = app.call("scene.export", scene_id=result["scene_id"], output="exports/imported.glb")
    loaded = trimesh.load(artifact["path"], force="scene", process=False)
    assert sum(len(mesh.faces) for mesh in loaded.geometry.values()) == 2
    mesh = next(iter(loaded.geometry.values()))
    assert mesh.visual.uv is not None and mesh.visual.material.baseColorTexture.size == (4, 4)


@pytest.mark.parametrize(
    "filename",
    [
        "../outside.png",
        "https://host/image.png",
        "C:/image.png",
        "../state.json",
        "../.geometry/data.png",
        "missing.png",
    ],
)
def test_external_image_failures_restore_scene_and_catalog(app, filename):
    # ../outside.png is a legal sibling path within the workspace, but missing here.
    source = fixture_fbx(app, filename=filename)
    before, catalog = app.engine.snapshot(), app.registry.list_operations()
    with pytest.raises(ScissorsError):
        app.call("scene.import_mesh", path=str(source))
    assert app.engine.snapshot() == before
    assert app.registry.list_operations() == catalog


def test_image_pixel_limit_and_mesh_limits_are_enforced(app):
    source = fixture_fbx(app, embedded=True, image_size=8)
    app.engine.settings.max_texture_pixels = 16
    with pytest.raises(ScissorsError):
        app.call("scene.import_mesh", path=str(source))
    assert app.call("scene.list")["scenes"] == []
    app.engine.settings.max_texture_pixels = 1024
    app.engine.settings.max_vertices = 3
    with pytest.raises(ScissorsError):
        app.call("scene.import_mesh", path=str(source))
    assert app.call("scene.list")["scenes"] == []


def test_malformed_fbx_and_non_fbx_content_restore_state(app):
    for content in (b"not fbx", b"v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n"):
        path = app.engine.root / "broken.fbx"
        path.write_bytes(content)
        before = app.engine.snapshot()
        with pytest.raises(ScissorsError):
            app.call("scene.import_mesh", path=str(path))
        assert app.engine.snapshot() == before


def test_catalog_and_backend_discovery(app):
    assert app.call("modeler.info")["backends"]["import_fbx"]
    description = app.registry.describe_operation("scene.import_mesh")
    assert "FBX" in description["description"]
    assert "filesystem.read" in description["permissions"]


@pytest.mark.parametrize("source_up", ["auto", "y", "z"])
def test_ascii_units_geometry_transform_hierarchy_and_axis_override(app, source_up):
    source = app.engine.root / "quad.fbx"
    source.write_bytes((Path(__file__).parent / "fixtures/fbx_scene_ascii.fbx").read_bytes())
    result = app.call(
        "scene.import_mesh", path=str(source), source_up=source_up, scale=2, position=[10, 0, 0]
    )
    obj = app.engine.object(result["object_ids"][0])[1]
    assert len(obj.faces) == 2
    assert result["source_unit_meters"] == 0.01
    if source_up in {"auto", "y"}:
        np.testing.assert_allclose(
            obj.summary()["bounds"], [[12.2, -6, 4], [14.2, -6, 6]], atol=1e-9
        )
        child = app.engine.object(result["node_ids"]["Child"])[1]
        np.testing.assert_allclose(np.asarray(child.transform)[:3, 3], [13, -6, 4], atol=1e-9)
    else:
        np.testing.assert_allclose(obj.summary()["bounds"], [[12.2, 4, 6], [14.2, 6, 6]], atol=1e-9)


def test_ascii_concave_polygon_triangulation(app):
    text = (Path(__file__).parent / "fixtures/fbx_scene_ascii.fbx").read_text(encoding="utf-8-sig")
    text = text.replace(
        "Vertices: *12 { a: 0,0,0,100,0,0,100,100,0,0,100,0 }",
        "Vertices: *15 { a: 0,0,0,200,0,0,200,200,0,100,100,0,0,200,0 }",
    )
    text = text.replace(
        "PolygonVertexIndex: *4 { a: 0,1,2,-4 }", "PolygonVertexIndex: *5 { a: 0,1,2,3,-5 }"
    )
    source = app.engine.root / "concave.fbx"
    source.write_text(text, encoding="utf-8")
    result = app.call("scene.import_mesh", path=str(source))
    obj = app.engine.object(result["object_ids"][0])[1]
    assert len(obj.faces) == 3
    assert obj.geometry().area == pytest.approx(3)


def test_instances_with_distinct_materials_keep_their_bindings(app):
    source = fixture_fbx(app, embedded=True, instances=2, distinct_materials=True)
    result = app.call("scene.import_mesh", path=str(source))
    first, second = [app.engine.object(oid)[1] for oid in result["object_ids"]]
    materials = app.engine.scene(result["scene_id"]).materials
    assert materials[first.material_id].base_color_texture
    assert materials[second.material_id].base_color_texture is None
    assert materials[second.material_id].base_color[:3] == [0, 0, 1]
    assert first.material_id != second.material_id


def test_builtin_fbx_export_import_retains_pbr_and_geometry(app):
    scene = app.scenes.create()
    cube = app.meshes.create_cube(scene_id=scene.id)
    app.meshes.translate(object_id=cube.id, x=1, y=2, z=3)
    app.call("uv.generate", object_id=cube.id, method="box")
    material = app.materials.create(scene_id=scene.id, metallic=0.25, roughness=0.6)
    app.materials.assign(object_id=cube.id, material_id=material.id)
    exported = app.call(
        "scene.export", scene_id=scene.id, output="assets/roundtrip.fbx", format="fbx"
    )
    result = app.call("scene.import_mesh", path=exported["path"])
    obj = app.engine.object(result["object_ids"][0])[1]
    imported = app.engine.scene(result["scene_id"]).materials[obj.material_id]
    assert imported.metallic == pytest.approx(0.25)
    assert imported.roughness == pytest.approx(0.6)
    assert app.call("mesh.validate", object_id=obj.id, require_closed=True)["valid"]
    np.testing.assert_allclose(
        obj.summary()["bounds"], app.engine.object(cube.id)[1].summary()["bounds"]
    )


def test_fbx_into_existing_scene_uses_destination_units(app):
    source = fixture_fbx(app, embedded=True)
    scene = app.scenes.create(units="millimeters")
    result = app.call("scene.import_mesh", path=str(source), scene_id=scene.id)
    obj = app.engine.object(result["object_ids"][0])[1]
    np.testing.assert_allclose(obj.summary()["bounds"], [[0, 0, 0], [1000, 1000, 0]])


def test_missing_required_fbx_reader_has_stable_error(app, monkeypatch):
    import importlib.util

    source = fixture_fbx(app, embedded=True)
    original = importlib.util.find_spec
    monkeypatch.setattr(
        importlib.util, "find_spec", lambda name: None if name == "ufbx" else original(name)
    )
    with pytest.raises(ScissorsError) as failure:
        app.call("scene.import_mesh", path=str(source))
    assert failure.value.code == "BACKEND_UNAVAILABLE"
    assert failure.value.details["backend"] == "import_fbx"
    assert app.call("scene.list")["scenes"] == []


def test_fbx_roundtrip_preserves_supported_pbr_image_slots(app):
    scene = app.scenes.create()
    cube = app.meshes.create_cube(scene_id=scene.id)
    app.call("uv.generate", object_id=cube.id, method="box")
    material = app.materials.create(
        scene_id=scene.id, base_color=[1, 1, 1, 1], emissive=[1, 1, 1], double_sided=True
    )
    app.materials.assign(object_id=cube.id, material_id=material.id)
    for index, slot in enumerate(
        ["base_color", "normal", "metallic_roughness", "occlusion", "emissive"]
    ):
        path = app.engine.root / f"channel_{index}.png"
        Image.new("RGB", (4, 4), (128 + index, 100, 200)).save(path)
        texture = app.call("texture.load", path=str(path))
        app.call(
            "texture.assign", material_id=material.id, texture_id=texture["texture_id"], slot=slot
        )
    exported = app.call("scene.export", scene_id=scene.id, output="assets/pbr.fbx", format="fbx")
    result = app.call("scene.import_mesh", path=exported["path"])
    obj = app.engine.object(result["object_ids"][0])[1]
    imported = app.engine.scene(result["scene_id"]).materials[obj.material_id]
    assert imported.double_sided
    for slot in ["base_color", "normal", "metallic_roughness", "occlusion", "emissive"]:
        texture_id = getattr(imported, slot + "_texture")
        assert texture_id is not None, slot
        with Image.open(app.engine.root / app.engine.textures[texture_id]["path"]) as image:
            assert image.size == (4, 4)
