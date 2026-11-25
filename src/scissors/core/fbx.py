"""Native FBX 7.4 binary static-scene writer, with bounded arrays and external PNG media."""

import io
import struct
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import trimesh

from scissors.api.errors import ScissorsError
from scissors.config import Settings
from scissors.core.exchange import ExchangeContext, mesh_colors, mesh_uv, unit_scale

VERSION = 7400
NULL = bytes(13)
# Scissors +X, +Y, +Z map to FBX +X, -Z, +Y.
Z_UP_TO_Y_UP = np.array([[1, 0, 0, 0], [0, 0, 1, 0], [0, -1, 0, 0], [0, 0, 0, 1]])


@dataclass
class Node:
    name: str
    properties: list[Any] = field(default_factory=list)
    children: list["Node"] = field(default_factory=list)


def node(name: str, *properties: Any, children: list[Node] | None = None) -> Node:
    return Node(name, list(properties), children or [])


def prop(name: str, kind: str, *values: Any, flags: str = "A") -> Node:
    return node("P", name, kind, "", flags, *values)


def binary_file(nodes: list[Node], context: ExchangeContext) -> bytes:
    buffer = io.BytesIO()

    def write(value: bytes) -> None:
        buffer.write(value)
        size = buffer.tell()
        if size + context.asset_bytes > context.settings.max_file_bytes:
            raise ScissorsError("RESOURCE_LIMIT", "FBX output exceeds file budget")
        if (
            context.geometry_bytes + context.cached_image_bytes + 4 * size + 5 * context.asset_bytes
            > context.settings.max_memory_bytes
        ):
            raise ScissorsError("RESOURCE_LIMIT", "FBX serialization exceeds memory budget")
        context.check()

    def property_bytes(value: Any) -> bytes:
        if isinstance(value, bool):
            return b"C" + bytes([int(value)])
        if isinstance(value, np.int32):
            return b"I" + struct.pack("<i", int(value))
        if isinstance(value, (int, np.integer)):
            return b"L" + struct.pack("<q", int(value))
        if isinstance(value, (float, np.floating)):
            return b"D" + struct.pack("<d", float(value))
        if isinstance(value, str):
            encoded = value.encode("utf-8")
            return b"S" + struct.pack("<I", len(encoded)) + encoded
        if isinstance(value, bytes):
            return b"R" + struct.pack("<I", len(value)) + value
        if isinstance(value, np.ndarray):
            if value.dtype.kind in "iu":
                if value.dtype.itemsize == 1:
                    code, dtype = (b"b", "|u1") if value.dtype.kind == "u" else (b"c", "|i1")
                else:
                    code, dtype = (b"l", "<i8") if value.dtype.itemsize > 4 else (b"i", "<i4")
            elif value.dtype.kind == "b":
                code, dtype = b"b", "|u1"
            elif value.dtype.kind == "f":
                code, dtype = (b"f", "<f4") if value.dtype.itemsize <= 4 else (b"d", "<f8")
            else:
                raise TypeError("Unsupported internal FBX array dtype")
            data = np.asarray(value, dtype=dtype).reshape(-1).tobytes()
            return code + struct.pack("<III", value.size, 0, len(data)) + data
        raise TypeError("Unsupported internal FBX property")

    def emit(item: Node) -> None:
        name = item.name.encode("ascii")
        start = buffer.tell()
        write(bytes(13) + name)
        properties_start = buffer.tell()
        for value in item.properties:
            write(property_bytes(value))
        properties_size = buffer.tell() - properties_start
        for child in item.children:
            emit(child)
        if item.children:
            write(NULL)
        end = buffer.tell()
        buffer.seek(start)
        buffer.write(struct.pack("<IIIB", end, len(item.properties), properties_size, len(name)))
        buffer.seek(end)

    write(b"Kaydara FBX Binary  \x00\x1a\x00" + struct.pack("<I", VERSION))
    for item in nodes:
        emit(item)
    write(NULL)
    # Conventional FBX binary footer identifiers, independent of scene content.
    write(bytes.fromhex("fabcab09d0c8d466b176fb831cf7267e"))
    write(bytes(16 - buffer.tell() % 16))
    write(bytes(4) + struct.pack("<I", VERSION) + bytes(120))
    write(bytes.fromhex("f85a8c6adef5d97eece90ce3758f290b"))
    return buffer.getvalue()


def affine_parts(matrix: np.ndarray) -> list[tuple[np.ndarray, np.ndarray, np.ndarray]]:
    """Represent every nonsingular affine by one TRS node, or two nodes for local shear."""
    linear = matrix[:3, :3]
    scales = np.linalg.norm(linear, axis=0)
    rotation = linear / scales
    if np.allclose(rotation.T @ rotation, np.eye(3), atol=1e-12, rtol=1e-12):
        if np.linalg.det(rotation) < 0:
            rotation[:, -1] *= -1
            scales[-1] *= -1
        parts = [(matrix[:3, 3], rotation, scales)]
    else:
        left, scales, right = np.linalg.svd(linear)
        left_sign, right_sign = np.linalg.det(left), np.linalg.det(right)
        left[:, -1] *= left_sign
        right[-1] *= right_sign
        scales[-1] *= left_sign * right_sign
        parts = [(matrix[:3, 3], left, scales), (np.zeros(3), right, np.ones(3))]
    result = []
    for translation, rotation, scale in parts:
        basis = np.eye(4)
        basis[:3, :3] = rotation
        angles = np.degrees(trimesh.transformations.euler_from_matrix(basis, axes="sxyz"))
        result.append((translation, angles, scale))
    return result


def export_fbx(
    scene: trimesh.Scene, settings: Settings, prefix: str, units: str
) -> tuple[bytes, dict[str, bytes], list[str]]:
    meters = unit_scale(units)
    context = ExchangeContext(scene, settings, prefix)
    basis = Z_UP_TO_Y_UP[:3, :3]
    objects: list[Node] = []
    connections: list[Node] = []
    next_id = 1000

    def uid() -> int:
        nonlocal next_id
        next_id += 1
        return next_id

    def connect(child: int, parent: int, property_name: str | None = None) -> None:
        connections.append(
            node("C", "OO", child, parent)
            if property_name is None
            else node("C", "OP", child, parent, property_name)
        )

    material_ids = []
    for material in context.materials:
        context.check()
        material_id = uid()
        material_ids.append(material_id)
        has_base, has_emissive = "base" in material.images, "emissive" in material.images
        specular = (1 - material.metallic) * 0.04 + material.metallic * material.color[:3]
        properties = [
            prop("DiffuseColor", "Color", *(np.ones(3) if has_base else material.color[:3])),
            prop("DiffuseFactor", "Number", 1.0),
            prop("EmissiveColor", "Color", *(np.ones(3) if has_emissive else material.emissive)),
            prop("EmissiveFactor", "Number", 1.0),
            prop("SpecularColor", "Color", *specular),
            prop("SpecularFactor", "Number", 1.0),
            prop(
                "Shininess",
                "Number",
                float(min(128, max(0, 2 / max(material.roughness, 0.01) ** 4 - 2))),
            ),
            prop("TransparencyFactor", "Number", float(1 - material.color[3])),
            prop("ScissorsMetallic", "Number", material.metallic, flags="AU"),
            prop("ScissorsRoughness", "Number", material.roughness, flags="AU"),
            prop("ScissorsDoubleSided", "bool", material.double_sided, flags="U"),
        ]
        for slot, image in material.images.items():
            factor = (
                np.r_[material.color[:3], 1]
                if slot == "base"
                else material.emissive
                if slot == "emissive"
                else None
            )
            path = context.image(image, factor)
            video_id, texture_id = uid(), uid()
            label = f"{material_id}_{slot}"
            objects.append(
                node(
                    "Video",
                    video_id,
                    f"{label}\x00\x01Video",
                    "Clip",
                    children=[
                        node("Type", "Clip"),
                        node("UseMipMap", np.int32(0)),
                        node("Filename", path),
                        node("RelativeFilename", path),
                    ],
                )
            )
            objects.append(
                node(
                    "Texture",
                    texture_id,
                    f"{label}\x00\x01Texture",
                    "",
                    children=[
                        node("Type", "TextureVideoClip"),
                        node("Version", np.int32(202)),
                        node("TextureName", f"{label}\x00\x01Texture"),
                        node("Media", f"{label}\x00\x01Video"),
                        node("FileName", path),
                        node("RelativeFilename", path),
                        node("ModelUVTranslation", 0.0, 0.0),
                        node("ModelUVScaling", 1.0, 1.0),
                        node("Properties70", children=[prop("UVSet", "KString", "UVSet0")]),
                    ],
                )
            )
            connect(video_id, texture_id)
            target = {
                "base": "DiffuseColor",
                "normal": "NormalMap",
                "emissive": "EmissiveColor",
            }.get(slot)
            if target:
                connect(texture_id, material_id, target)
            else:
                properties.append(prop(f"Scissors{slot.title()}Image", "KString", path, flags="U"))
        objects.append(
            node(
                "Material",
                material_id,
                f"{material.name}\x00\x01Material",
                "",
                children=[
                    node("Version", np.int32(102)),
                    node("ShadingModel", "phong"),
                    node("MultiLayer", np.int32(0)),
                    node("Properties70", children=properties),
                ],
            )
        )
    geometry_ids = {}
    for key, mesh in scene.geometry.items():
        context.check()
        geometry_id = geometry_ids[key] = uid()
        faces = np.asarray(mesh.faces, dtype=np.int32).copy()
        faces[:, 2] = -faces[:, 2] - 1
        children = [
            node("GeometryVersion", np.int32(124)),
            node("Vertices", np.asarray(mesh.vertices, dtype=float) @ basis.T),
            node("PolygonVertexIndex", faces),
        ]
        layers: list[Node] = []

        def layer(
            kind: str,
            payload: list[Node],
            mapping: str = "ByVertice",
            reference: str = "Direct",
            target_children: list[Node] = children,
            target_layers: list[Node] = layers,
        ) -> None:
            full_name = f"LayerElement{kind}"
            target_children.append(
                node(
                    full_name,
                    np.int32(0),
                    children=[
                        node("Version", np.int32(101)),
                        node("Name", "UVSet0" if kind == "UV" else ""),
                        node("MappingInformationType", mapping),
                        node("ReferenceInformationType", reference),
                        *payload,
                    ],
                )
            )
            target_layers.append(
                node(
                    "LayerElement",
                    children=[node("Type", full_name), node("TypedIndex", np.int32(0))],
                )
            )

        layer("Normal", [node("Normals", np.asarray(mesh.vertex_normals, dtype=float) @ basis.T)])
        uv, colors = mesh_uv(mesh), mesh_colors(mesh)
        if uv is not None:
            layer("UV", [node("UV", uv)])
        if colors is not None:
            layer("Color", [node("Colors", colors)])
        layer(
            "Material",
            [node("Materials", np.asarray([0], dtype=np.int32))],
            "AllSame",
            "IndexToDirect",
        )
        children.append(
            node("Layer", np.int32(0), children=[node("Version", np.int32(100)), *layers])
        )
        objects.append(
            node("Geometry", geometry_id, f"{key}\x00\x01Geometry", "Mesh", children=children)
        )
    model_ids = {context.base: 0}
    pending = [context.base]
    used_names = {str(name) for name in scene.graph.nodes}
    while pending:
        parent = pending.pop(0)
        for name, data in context.children.get(parent, []):
            current_parent = model_ids[parent]
            # Express each local frame in the same basis as its geometry and parent.
            local = np.asarray(data["matrix"], dtype=float)
            parts = affine_parts(Z_UP_TO_Y_UP @ local @ Z_UP_TO_Y_UP.T)
            key = data.get("geometry")
            for index, (translation, angles, scale) in enumerate(parts):
                model_id = uid()
                last = index == len(parts) - 1
                label = name
                if not last:
                    label = f"{name}_Affine"
                    while label in used_names:
                        label += "_"
                    used_names.add(label)
                kind = "Mesh" if key is not None and last else "Null"
                objects.append(
                    node(
                        "Model",
                        model_id,
                        f"{label}\x00\x01Model",
                        kind,
                        children=[
                            node("Version", np.int32(232)),
                            node(
                                "Properties70",
                                children=[
                                    prop(
                                        "Lcl Translation",
                                        "Lcl Translation",
                                        *map(float, translation),
                                    ),
                                    prop("Lcl Rotation", "Lcl Rotation", *map(float, angles)),
                                    prop("Lcl Scaling", "Lcl Scaling", *map(float, scale)),
                                    prop("RotationOrder", "enum", np.int32(0), flags=""),
                                    prop("InheritType", "enum", np.int32(1), flags=""),
                                    prop("RotationActive", "bool", True, flags=""),
                                ],
                            ),
                            node("Shading", True),
                            node("Culling", "CullingOff"),
                        ],
                    )
                )
                connect(model_id, current_parent)
                current_parent = model_id
            model_ids[name] = current_parent
            if key is not None:
                connect(geometry_ids[key], current_parent)
                connect(material_ids[context.mesh_materials[key]], current_parent)
            pending.append(name)
    type_counts: dict[str, int] = {}
    for item in objects:
        type_counts[item.name] = type_counts.get(item.name, 0) + 1
    globals = [
        prop("UpAxis", "int", np.int32(1)),
        prop("UpAxisSign", "int", np.int32(1)),
        prop("FrontAxis", "int", np.int32(2)),
        prop("FrontAxisSign", "int", np.int32(1)),
        prop("CoordAxis", "int", np.int32(0)),
        prop("CoordAxisSign", "int", np.int32(1)),
        prop("UnitScaleFactor", "double", meters * 100),
        prop("OriginalUnitScaleFactor", "double", meters * 100),
    ]
    header = node(
        "FBXHeaderExtension",
        children=[
            node("FBXHeaderVersion", np.int32(1003)),
            node("FBXVersion", np.int32(VERSION)),
            node("EncryptionType", np.int32(0)),
            node(
                "CreationTimeStamp",
                children=[
                    node("Version", np.int32(1000)),
                    node("Year", np.int32(1970)),
                    node("Month", np.int32(1)),
                    node("Day", np.int32(1)),
                    node("Hour", np.int32(10)),
                    node("Minute", np.int32(0)),
                    node("Second", np.int32(0)),
                    node("Millisecond", np.int32(0)),
                ],
            ),
            node("Creator", "Scissors"),
        ],
    )
    definitions = [node("Version", np.int32(100)), node("Count", np.int32(len(objects)))]
    definitions.extend(
        node("ObjectType", kind, children=[node("Count", np.int32(count))])
        for kind, count in type_counts.items()
    )
    file_data = binary_file(
        [
            header,
            node("FileId", bytes.fromhex("28b32aebb624ccc2bfc8b02aa92bfcf1")),
            node("CreationTime", "1970-01-01 10:00:00:000"),
            node("Creator", "Scissors"),
            node(
                "GlobalSettings",
                children=[node("Version", np.int32(1000)), node("Properties70", children=globals)],
            ),
            node(
                "Documents",
                children=[
                    node("Count", np.int32(1)),
                    node("Document", 1, "Scene", "Scene", children=[node("RootNode", 0)]),
                ],
            ),
            node("References"),
            node("Definitions", children=definitions),
            node("Objects", children=objects),
            node("Connections", children=connections),
        ],
        context,
    )
    return (
        file_data,
        context.assets,
        [
            "FBX 7.4 binary exports Y-up with hierarchy, instances, UV, normals and vertex colors.",
            "Full affine placement uses RSrs inheritance and helper nodes for local shear.",
            "Phong approximates PBR. Metallic/roughness and ORM/occlusion use custom properties.",
            "Keep PNG sidecars with FBX. Vertex-color/normal-map rendering depends on importer.",
        ],
    )
