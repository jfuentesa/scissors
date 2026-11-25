# Developing Scissors

Scissors is a local CPU/headless 3D engine for external agents, with no LLM.
Its differentiator is reusable Python plugins and runtime capability discovery.

## Git repository

The project is a Git repository whose history can be consulted to review its latest
changes.

All commit messages must be written in English and include a summary of the changes
introduced on the branch.

## Main language

Main language is English, write everything (code, comments, docs) in English.

## Communication with the user

All communication with the user, both in conversations and in generated
documentation, must use clear language and simple technical vocabulary. Apply
the following rules:

- Use short, direct sentences with one idea per sentence.
- Prefer active voice and common words over jargon.
- Define and maintain a glossary of stable terms. Always use the same term for
  the same concept.
- Avoid ambiguity and convoluted phrasing.
- In brief responses, prioritize clarity over completeness.
- End every response with a coherent question relevant to the topic being discussed.

## Architecture and ownership

Python `Scissors.call`, REST and MCP → `OperationRegistry.execute` → native operations
or PluginManager → Engine. Never duplicate geometry logic in transport adapters.

- `src/scissors/core`: versioned scene/mesh/PBR models, NumPy/Trimesh geometry, textures,
  UV, preview rendering (VTK/Pillow), export, atomic persistence and workspace locking.
- `src/scissors/api`: public facade, central schemas/catalog, structured errors and
  transaction handling. Registry serializes calls, validates parameters/results, restores
  state/catalog on failure, and checkpoints successful mutations.
- `src/scissors/mcp`: SDK 2.x callbacks, direct dynamic tools, resources and notifications.
- `src/scissors/http`: REST and MCP share one engine; auth/host/origin/body protections.
- `src/scissors/plugins`: static manifests, automatic enablement, child workers and public
  PluginContext. Parent applies scoped staged changes, recalculates normals and validates.
- `cli.py`, `config.py`: local operator commands and validated workspace/resource settings.
- `plugins/examples/twist_mesh`: independent plugin using only the public context, with tests.
- `skill/scissors`: distributable operating skill for agents consuming Scissors.
- `scripts`, `docs`, `examples`, `tests`: tooling, contracts, workflows and checks.

These instructions govern engine development and maintenance of the distributable skill.
The operating skill governs modeling and independent plugins through public APIs; it
should not direct consumers to modify the engine, public contracts or the skill itself.

Workspaces are relocatable directories. Versioned atomic `state.json` holds scenes, relative
texture references and plugin enablement. Scene snapshots keep stable IDs.
FileLock rejects a second owning process; RLock serializes public mutations. Connect clients
to HTTP when it owns a workspace; do not start stdio against it. See [architecture](docs/architecture.md).

## Developer rules

1. Read AGENTS.md and affected modules before modifying code.
2. Discover existing operations/plugins before implementing a capability.
3. Prefer plugins for independent procedural geometry and deformations.
4. Change core for fundamental contracts or shared infrastructure.
5. Keep all interfaces using the same service/registry.
6. Register new operations centrally with schemas, descriptions, ownership and permissions.
7. Keep public contracts consistent. Preserve compatibility only when explicitly required.
8. Add meaningful tests for new features, errors and state invariants.
9. Preserve useful comments unless inaccurate or obsolete.
10. Document every project change by updating the relevant description of the current
    behavior. Replace obsolete descriptions. Follow the documentation rules below.
    Update the distributable skill when public workflows change.
11. Justify new dependencies. Built-in geometry backends are required dependencies;
    new optional capabilities must be justified separately.
12. Run lint, types and the tests that cover the change before finishing; report actual
    results. Skip the full suite when no executable behavior changed.

## Documentation

- Keep published documentation limited to official project guides, API references,
  supported workflows, current behavior and known limitations.
- Describe the current implementation. Replace obsolete descriptions when behavior changes.
- Do not include decision dates, dated verification notes, implementation origins or
  history, development stages, session notes or internal audit reports.
- Do not reference documents or other files under `temp/`.
- Put information needed by users in the relevant official document. Keep temporary
  notes and development traces out of published documentation.
- Keep local documentation links valid. Preserve relevant external technical sources.
- Update the distributable skill when public workflows change.

## Stable contracts

Public: Scissors, Settings, app.call, app.transaction, namespace keyword methods, export
methods, Operation,
OperationRegistry, ScissorsError, PluginManifest API 1.0 and PluginContext.
Scene coordinates are right-handed Z-up. glTF, GLB and static FBX export Y-up and
name nodes after objects. Transforms are baked into vertices; the cumulative
matrix is recorded for diagnostics and must not be applied twice. IDs are independent of
object order. Render vertices can split at seams; topology diagnostics weld exact positions.

Internal: mutable Engine dictionaries, worker/runtime bookkeeping and transport internals.
Plugins must not import or mutate Engine. Do not add eval/exec dispatch or public tools
accepting executable code. Packages live in the application plugin store, shared by all workspaces:
Settings.plugins_dir, --plugins-dir or SCISSORS_PLUGINS_DIR (default ~/.scissors/plugins).
Keep this directory separate from workspaces. Installation and uninstallation stay local;
only enable/disable/reload are public. Activation belongs to each workspace and an explicit
disable is remembered in state. New sessions discover shared packages automatically.
A separate FileLock serializes package changes and worker access across processes.
Subprocesses provide failure containment, never advertised as a full sandbox.

Registry errors use stable codes/message/details; app.call raises ScissorsError.
Atomic batches roll back scene changes and reject filesystem/plugin lifecycle effects.
No nested batches. More detail: [API](docs/api.md), [plugins](docs/plugins.md), [security](docs/security.md).

## Run, extend and debug

```bash
uv sync
uv run scissors --help
uv run python examples/full_workflow.py
uv run scissors --workspace workspaces/development mcp stdio
uv run scissors --workspace workspaces/agents serve --host 127.0.0.1 --port 8765
uv run ruff check src tests examples plugins scripts
uv run ruff format --check src tests examples plugins scripts
uv run mypy src
uv run pytest -q
```

Use `python -m uv` if needed. Keep MCP stdout protocol-only, logs on stderr.
Inspect error envelopes and `plugins list` load errors; reproduce failures in temporary
workspaces. Never delete a running workspace's lock. Transport changes need both real
stdio and HTTP integration tests. Export changes need artifact reopening.

Match checks to the change. A documentation or skill-only edit needs the skill test
(`uv run pytest -q tests/test_skill.py`), Ruff and mypy. Run the full suite when code,
contracts, plugins, transports or exports change, or when no focused test covers the
risk. State which checks ran and which did not. Do not repeat a check that already
passed on the same unmodified files.

Plugin workflow: prepare manifest/code/tests under workspace staging; validate without
execution; install, which enables the package; run tests; describe/invoke; verify dynamic
discovery and restart persistence. See docs/plugins.md for complete commands.
No dependency auto-install. Register public operations with Operation/registry.register or
native add_function; describe side effects truthfully. Regenerate manifest JSON Schema after
contract changes. Publishing here means updating the catalog, not implicitly uploading a repo.

## Completion checklist

Use this checklist to verify that a change is ready to be considered complete.
Report the results of these checks and any remaining limitations.

- [ ] Shared registry behavior and accurate schemas/permissions/errors.
- [ ] Failure restores state; resource/path checks and reserved plugin paths remain enforced.
- [ ] Relevant tests and examples run, including reopening generated artifacts.
- [ ] Ruff check, format --check and mypy src pass, plus the tests that cover the change;
      a documentation or skill-only edit skips the full pytest suite.
- [ ] Built-in geometry backends work in the default installation without feature selectors.
- [ ] Docs and distributable skill updated for changed public workflows.
- [ ] Actual outcomes/limitations documented, with no simulated features or placeholders.
