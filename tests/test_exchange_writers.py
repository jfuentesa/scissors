"""Exchange artifact contracts and independent record reopening."""

import io
import struct
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import numpy as np
import pytest
import trimesh
from PIL import Image

from scissors.api.errors import ScissorsError

NS = {"c": "http://www.collada.org/2005/11/COLLADASchema"}


def read_fbx(path):
    """Small independent reader of FBX records, including offsets and property sizes."""
    raw = Path(path).read_bytes()
    assert raw[:23] == b"Kaydara FBX Binary  \x00\x1a\x00"
    assert struct.unpack_from("<I", raw, 23)[0] == 7400

    def read(offset):
        end, count, byte_count, name_length = struct.unpack_from("<IIIB", raw, offset)
        assert offset < end <= len(raw)
        cursor = offset + 13
        name = raw[cursor : cursor + name_length].decode("ascii")
        cursor += name_length
        properties_start = cursor
        properties = []
        for _ in range(count):
            kind = chr(raw[cursor])
            cursor += 1
            if kind in "CIDL":
                format = {"C": "<?", "I": "<i", "D": "<d", "L": "<q"}[kind]
                properties.append(struct.unpack_from(format, raw, cursor)[0])
                cursor += struct.calcsize(format)
            elif kind in "SR":
                size = struct.unpack_from("<I", raw, cursor)[0]
                cursor += 4
                value = raw[cursor : cursor + size]
                properties.append(value.decode("utf-8") if kind == "S" else value)
                cursor += size
            else:
                assert kind in "di"
                size, compression, length = struct.unpack_from("<III", raw, cursor)
                assert compression == 0
                cursor += 12
                array = np.frombuffer(
                    raw[cursor : cursor + length], dtype="<f8" if kind == "d" else "<i4"
                )
                assert len(array) == size
                properties.append(array)
                cursor += length
        assert cursor - properties_start == byte_count
        children = []
        while cursor < end:
            if raw[cursor : cursor + 13] == bytes(13):
                cursor += 13
                break
            child, cursor = read(cursor)
            children.append(child)
        assert cursor == end
        return {"name": name, "properties": properties, "children": children}, end

    result, cursor = [], 27
    while raw[cursor : cursor + 13] != bytes(13):
        item, cursor = read(cursor)
        result.append(item)
    return result


def child(items, name):
    return next(item for item in items if item["name"] == name)


def dae_world_vertices(path):
    root = ET.parse(path).getroot()
    geometries = {}
    for geometry in root.findall("c:library_geometries/c:geometry", NS):
        values = geometry.find("c:mesh/c:source/c:float_array", NS)
        geometries[geometry.attrib["id"]] = np.fromstring(values.text, sep=" ").reshape(-1, 3)
    vertices = []

    def visit(node, parent):
        matrix = np.fromstring(node.find("c:matrix", NS).text, sep=" ").reshape(4, 4)
        world = parent @ matrix
        for instance in node.findall("c:instance_geometry", NS):
            points = geometries[instance.attrib["url"][1:]]
            vertices.extend(trimesh.transformations.transform_points(points, world))
        for nested in node.findall("c:node", NS):
            visit(nested, world)

    for node in root.findall("c:library_visual_scenes/c:visual_scene/c:node", NS):
        visit(node, np.eye(4))
    return root, np.asarray(vertices)


def test_dae_retains_hierarchy_subset_units_and_transform_once(app):
    scene = app.scenes.create(units="centimeters")
    cube = app.meshes.create_cube(scene_id=scene.id)
    other = app.meshes.create_cube(scene_id=scene.id)
    group = app.scenes.group(scene_id=scene.id, object_ids=[cube.id, other.id], name="Assembly")
    app.meshes.translate(object_id=group.id, x=2)
    matrix = np.eye(4)
    matrix[0, 3] = 3
    before = app.engine.snapshot()
    result = app.export.dae(
        scene.id, only_object_ids=[cube.id], export_transform=matrix.tolist(), root_name="Playable"
    )
    root, vertices = dae_world_vertices(result.path)
    np.testing.assert_allclose(
        [vertices.min(axis=0), vertices.max(axis=0)], [[4.5, -0.5, -0.5], [5.5, 0.5, 0.5]]
    )
    assert root.find("c:asset/c:unit", NS).attrib["meter"] == "0.01"
    assert root.find("c:asset/c:up_axis", NS).text == "Z_UP"
    assert root.find(".//c:node[@name='Assembly']/c:node", NS) is not None
    assert app.engine.snapshot() == before


@pytest.mark.parametrize("shear", [False, True])
def test_fbx_binary_offsets_geometry_layers_and_world_hierarchy(app, shear):
    scene = app.scenes.create()
    cube = app.meshes.create_cube(scene_id=scene.id, name="Panel")
    app.call("uv.generate", object_id=cube.id, method="box")
    group = app.scenes.group(scene_id=scene.id, object_ids=[cube.id], name="Assembly")
    app.meshes.rotate(object_id=group.id, axis="x", angle_degrees=28)
    app.meshes.translate(object_id=group.id, x=2, y=3, z=4)
    matrix = np.eye(4)
    if shear:
        matrix[0, 1] = 0.3
        matrix[0, 3] = 3
    result = app.export.fbx(scene.id, export_transform=matrix.tolist())
    document = read_fbx(result.path)
    axes = {
        item["properties"][0]: item["properties"][4]
        for item in child(child(document, "GlobalSettings")["children"], "Properties70")["children"]
    }
    assert (axes["UpAxis"], axes["UpAxisSign"]) == (1, 1)
    assert (axes["FrontAxis"], axes["FrontAxisSign"]) == (2, 1)
    assert (axes["CoordAxis"], axes["CoordAxisSign"]) == (0, 1)
    objects = child(document, "Objects")["children"]
    models = {item["properties"][0]: item for item in objects if item["name"] == "Model"}
    geometry = child(objects, "Geometry")
    vertices = child(geometry["children"], "Vertices")["properties"][0].reshape(-1, 3)
    faces = child(geometry["children"], "PolygonVertexIndex")["properties"][0].reshape(-1, 3)
    assert np.all(faces[:, -1] < 0)
    assert child(geometry["children"], "LayerElementUV")
    connections = child(document, "Connections")["children"]
    parents = {
        item["properties"][1]: item["properties"][2]
        for item in connections
        if item["properties"][0] == "OO"
    }

    def world(model_id):
        if model_id == 0:
            return np.eye(4)
        properties = {
            item["properties"][0]: item["properties"][4:]
            for item in child(models[model_id]["children"], "Properties70")["children"]
        }
        rotation = trimesh.transformations.euler_matrix(*np.radians(properties["Lcl Rotation"]))
        local = (
            trimesh.transformations.translation_matrix(properties["Lcl Translation"])
            @ rotation
            @ np.diag([*properties["Lcl Scaling"], 1])
        )
        return world(parents[model_id]) @ local

    transformed = trimesh.transformations.transform_points(
        vertices, world(parents[geometry["properties"][0]])
    )
    source = app.engine.object(cube.id)[1]
    expected = trimesh.transformations.transform_points(source.vertices, matrix)
    np.testing.assert_allclose(transformed, expected[:, [0, 2, 1]] * [1, 1, -1], atol=1e-10)
    normal_layer = child(geometry["children"], "LayerElementNormal")
    normals = child(normal_layer["children"], "Normals")["properties"][0].reshape(-1, 3)
    transformed_normals = normals @ np.linalg.inv(world(parents[geometry["properties"][0]])[:3, :3])
    transformed_normals /= np.linalg.norm(transformed_normals, axis=1, keepdims=True)
    expected_normals = np.asarray(source.normals) @ np.linalg.inv(matrix[:3, :3])
    expected_normals /= np.linalg.norm(expected_normals, axis=1, keepdims=True)
    np.testing.assert_allclose(
        transformed_normals, expected_normals[:, [0, 2, 1]] * [1, 1, -1], atol=1e-10
    )


def test_fbx_material_writes_modern_and_legacy_shininess(app):
    scene = app.scenes.create()
    cube = app.meshes.create_cube(scene_id=scene.id)
    material = app.call("material.create", scene_id=scene.id, roughness=0.5)
    app.call("material.assign", object_id=cube.id, material_id=material["id"])
    result = app.export.fbx(scene.id)
    objects = child(read_fbx(result.path), "Objects")["children"]
    parameters = {
        item["properties"][0]: item["properties"][4]
        for item in child(child(objects, "Material")["children"], "Properties70")["children"]
    }
    expected = 2 / 0.5**4 - 2
    assert parameters["ShininessExponent"] == pytest.approx(expected)
    assert parameters["Shininess"] == pytest.approx(expected)


@pytest.mark.parametrize("format", ["fbx", "dae", "usdz"])
def test_exchange_textures_are_real_png_and_usdz_entries_are_aligned(app, format):
    scene = app.scenes.create()
    cube = app.meshes.create_cube(scene_id=scene.id)
    app.call("uv.generate", object_id=cube.id, method="box")
    texture = app.call("texture.generate_checker", width=16, height=16)
    material = app.call(
        "material.from_texture", scene_id=scene.id, texture_id=texture["texture_id"]
    )
    app.call("material.assign", object_id=cube.id, material_id=material["id"])
    result = app.call(
        "scene.export", scene_id=scene.id, output=f"exports/model.{format}", format=format
    )
    if format == "usdz":
        raw = Path(result["path"]).read_bytes()
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            entries = archive.infolist()
            assert entries[0].filename == "defaultLayer.usda"
            layer = archive.read(entries[0]).decode("utf-8")
            assert layer.startswith("#usda 1.0") and "UsdPreviewSurface" in layer
            assert "faceVertexIndices" in layer and "primvars:st" in layer
            assert "inputs:diffuseColor.connect" in layer
            for entry in entries:
                name_size, extra_size = struct.unpack_from("<HH", raw, entry.header_offset + 26)
                assert (entry.header_offset + 30 + name_size + extra_size) % 64 == 0
                assert entry.compress_type == zipfile.ZIP_STORED and not entry.flag_bits & 1
                if entry.filename.endswith(".png"):
                    with Image.open(io.BytesIO(archive.read(entry))) as image:
                        assert image.size == (16, 16)
    else:
        images = [Path(path) for path in result["files"] if path.endswith(".png")]
        assert images
        with Image.open(images[0]) as image:
            assert image.size == (16, 16)


@pytest.mark.parametrize("format", ["fbx", "dae", "usdz"])
def test_exchange_budget_rejection_writes_no_files_and_changes_no_scene(app, format):
    scene = app.scenes.create()
    app.meshes.create_cube(scene_id=scene.id)
    before = app.engine.snapshot()
    app.engine.settings.max_file_bytes = 128
    with pytest.raises(ScissorsError) as failure:
        app.call(
            "scene.export", scene_id=scene.id, output=f"exports/limited.{format}", format=format
        )
    assert failure.value.code == "RESOURCE_LIMIT"
    assert app.engine.snapshot() == before
    assert not (app.engine.root / f"exports/limited.{format}").exists()


@pytest.mark.parametrize("format", ["fbx", "dae"])
@pytest.mark.parametrize("tint", [1.0, 0.5])
def test_exchange_preserves_2048_texture_with_bounded_tint(app, format, tint):
    sid = app.call("scene.create")["id"]
    oid = app.call("mesh.create_cube", scene_id=sid)["id"]
    source = app.engine.root / "source.png"
    Image.new("RGBA", (2048, 2048), (120, 90, 60, 200)).save(source)
    texture = app.call("texture.load", path="source.png")
    mid = app.call("material.create", scene_id=sid, base_color=[tint, tint, tint, 1])["id"]
    app.call("texture.assign", material_id=mid, texture_id=texture["id"])
    app.call("material.assign", object_id=oid, material_id=mid)
    app.call("uv.generate", object_id=oid)
    before = app.engine.snapshot()
    result = app.call("scene.export", scene_id=sid, output=f"large.{format}", format=format)
    if format == "fbx":
        assert read_fbx(result["path"])
    else:
        ET.parse(result["path"])
    images = [Path(path) for path in result["files"] if path.endswith(".png")]
    assert len(images) == 1
    with Image.open(images[0]) as image:
        assert image.size == (2048, 2048)
        if tint == 1:
            assert image.getpixel((0, 0)) == (120, 90, 60, 200)
        else:
            assert image.getpixel((0, 0))[0] < 120
        assert image.getpixel((0, 0))[3] == 200
    assert app.engine.snapshot() == before
