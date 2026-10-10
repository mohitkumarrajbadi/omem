# Namespaces — automatic project memory

OMem keeps **one** SQLite brain (`~/.omem/brain.db`) and partitions it by
**namespace**. Namespaces are create-on-write: the first `remember` into a name
creates it; later writes merge into the same bucket. There is no separate
`create namespace` command.

## Kinds

| Kind | Name | Purpose |
|------|------|---------|
| Project | git root basename (`trading`, `neteng-app`, …) | Default when you work in that repo |
| Bridge | `personal` (alias: `global`) | Cross-project prefs |
| Sticky | `omem use <name>` / `OMEM_NS` | Manual override |

## Resolution (active namespace)

1. `OMEM_NS` or `OMEM_NAMESPACE` env  
2. Sticky file `~/.omem/active_namespace` (`omem use`)  
3. Git root basename under `OMEM_PROJECT_ROOT` or cwd  
4. cwd basename, else `default`

**Smart project (default):** if env/sticky is only `personal` / `global` **and** you are inside a git repo, OMem uses the **git folder** as the active project namespace (prefs stay in the bridge via `--personal` / `scope=personal`). Force the old mega-bucket with `OMEM_FORCE_NAMESPACE=1`.

## Lean recall (less tokens)

- Default `k=3`, short snippets in CLI/MCP  
- Compact `context` pack for agents (`approx_tokens` in stats)  
- CLI: `omem recall "…" --full` for complete text  
- MCP: `recall(..., full=True)` only when needed

```bash
omem ns                 # where am I?
omem use trading        # sticky pin
omem use --auto         # follow git/cwd again
omem namespaces         # list (* = active)
omem console            # local GUI (same brain) — alias: omem dashboard
```

## Recall cascade

| Mode | Behavior |
|------|----------|
| Default | active → + `personal`/`global` → widen other projects only if weak |
| `--strict` | active only |
| `--all` | every namespace (hits labeled `namespace=`) |

```bash
omem remember "prefer MIS for arb"           # → active project
omem remember "I like dark mode" --personal  # → personal bridge
omem recall "charges"                        # focus cascade
omem recall "charges" --strict
```

## MCP

Prefer shared `--db-path` and **omit** `--namespace` so each workspace
auto-isolates. Cross-project prefs: `remember` with `scope=personal`.

Pinning `--namespace personal` puts every project in one bucket (legacy
multi-tool sharing). That disables auto isolation — avoid unless you want it.

See [MCP_SETUP.md](./MCP_SETUP.md).
