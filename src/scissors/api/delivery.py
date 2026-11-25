"""Split export schemas shared by Python, REST and MCP."""

from typing import Annotated, Any, Literal

from pydantic import Field

from scissors.api.bundles import register_bundles
from scissors.api.registry import OperationRegistry
from scissors.core.delivery import split_export as export_parts
from scissors.core.engine import Engine

Finite = Annotated[float, Field(allow_inf_nan=False)]


def register_delivery(registry: OperationRegistry, engine: Engine) -> None:
    register_bundles(registry, engine)

    def split_export(
        scene_id: str,
        output_dir: str,
        by: Literal["object", "group", "material"] = "object",
        format: Literal["glb", "gltf", "obj", "stl", "ply", "dae", "usdz", "fbx"] = "glb",
        only_object_ids: Annotated[list[str], Field(min_length=1, max_length=4096)] | None = None,
        export_transform: Annotated[
            list[Annotated[list[Finite], Field(min_length=4, max_length=4)]],
            Field(min_length=4, max_length=4),
        ]
        | None = None,
    ) -> dict[str, Any]:
        return export_parts(
            engine, scene_id, output_dir, by, format, only_object_ids, export_transform
        )

    registry.add_function(
        "scene.split_export",
        split_export,
        "Export visible meshes by object, top-level subtree or material with separate sidecars. "
        "Static FBX exports Y-up.",
        permissions=["filesystem.write"],
    )
