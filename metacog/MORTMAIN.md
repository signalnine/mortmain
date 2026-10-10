# metacog, Mortmain build

Copied from metacog v6.12.0 (`~/metacog`, source only). Version string: `6.12.0-mortmain`. Upstream is not modified.

## Differences from upstream v6.12

### Stratagems are rites on disk
- The compiled-in `Stratagems` map is gone. All 35 upstream stratagems are removed from the binary.
- Rites are JSON files `<name>.json`: `{"name": "fool", "title": "THE FOOL", "steps": [{"kind": "become", "text": "..."}]}`.
- Validation (`rites.go`, `ParseRite`): file <= 8192 bytes; regular file; `name` matches `^[a-z][a-z0-9-]{0,31}$` and equals the filename stem; `title` is `[A-Z ]`, 1..48 chars; 1..12 steps; `kind` is one of the 18 primitives, `THINK` or `ACTION`; `text` is printable ASCII, 1..400 chars; unknown fields and trailing data are rejected. An invalid file prints one `metacog: skipping rite <path>: <reason>` line on stderr and is never used. Rite text is only printed, never executed.
- Search path, first valid match by name wins: `$METACOG_RITES` (colon-separated) if set, else `~/rites`, `/library/inner`, `/library/outer`, `/usr/share/metacog/rites`. Flat directories only. Unreadable directories are skipped silently.
- `stratagem start` copies the title and full step list into `state.json` (`stratagem.title`, `stratagem.steps`, additive and omitempty, schema stays v1). A rite burned mid-session does not break it. State from an older build without `steps` falls back to the search path; if the rite is gone, `next` says to `abort`.
- `stratagem list` lists every loadable rite. Shell completion of `stratagem start` is dynamic.
- `reflect` lists completions of rites that are no longer loadable in addition to the loadable ones.

### No built-in stance pools
- `cmd/metacog/stances/*.json` (78 pools) and the `go:embed` are deleted. `LoadStancePools` returns an empty map.
- `inspire` draws only from the personal pool (`$METACOG_HOME/stances/personal.json`) and, in monastery mode, the ancestors pool.

### Monastery mode
Enabled when `/etc/metacog/monastery` exists (`METACOG_MONASTERY_FLAG` overrides the path).
- Ancestors pool: `inspire` gains a pool `ancestors`, read from `/var/lib/mortmain/ancestors.json` (`METACOG_ANCESTORS`), a JSON array of `{who, where, lens, ...}` (extra fields ignored, entries without `who` dropped). Missing or unreadable file means an empty pool. The binary never writes it.
- `inspire --save` writes no local file. It submits `{"v":1,"cmd":"save-stance","args":{"who","where","lens"},"cwd":...}` to `/var/spool/mortmain/req/<uuid>.json` (`METACOG_SPOOL` overrides the spool root; temp file `.<uuid>.json.tmp` + rename, mode 0600), polls `resp/<uuid>.json` every 200ms for up to 120s (`METACOG_SPOOL_TIMEOUT`, seconds, for tests), prints `out` to stdout and `err` to stderr, and exits 1 when `ok` is false. It tries to remove the response file afterwards and ignores failure.
- Event hook: every invocation writes `events/<uuid>.json` under the spool root: `{"v":1,"argv":[...],"exit":N,"ts":RFC3339,"stratagem":name|null,"step":n|null}`. `argv` excludes the program name. `stratagem` and `step` come from `state.json` after the command; if the command ended the stratagem (final `next`, `abort`, forced replace), they come from the state before it. `step` is 1-based (the step being worked, as `status` shows it). Write failures are silent.
- Outside monastery mode none of this happens and the personal pool works as upstream.

Per-monk state is upstream behaviour: `$METACOG_HOME` or `~/.metacog`, so each cell holds its own state.

### Output text
- `version` prints `metacog 6.12.0-mortmain`, the schema and the primitives. No stratagem list (also gone from `--json`).
- The default cobra `completion` command is disabled (its help names shells and operating systems).
- All non-ASCII output replaced: status markers `x`/`>` (were check mark and arrow), ` -- ` for em dashes in step headers and `reflect`, `x` in `counterfactual` pruned branches, `o` in the `meditate` figure.
- Proper nouns and tradition terms removed from help and output: `apophasis` long help (named theologians and a tradition), `witness` long help (named authors and a book), `meditate` output and `--focus` help (a tradition's term for objectless sitting).

### Tests
- `rites_fixture_test.go`: `TestMain` writes fixture rites to a temp dir and sets `METACOG_RITES`, pins monastery mode off and the spool to a temp dir. Integration tests inherit this environment.
- New: `rites_test.go` (schema, limits, search order, invalid-file fallthrough, unreadable dirs, captured steps, seed rites in `../seed/rites` all validate), `monastery_test.go`, `monastery_integration_test.go`.
- Removed: `empirical_stratagems_test.go` (tested compiled stratagems that no longer exist).

## Build

```
go build -o metacog ./cmd/metacog/
go test ./cmd/metacog/ && go test ./cmd/metacog/ -tags integration
CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -trimpath -ldflags="-s -w" -o metacog-linux-amd64 ./cmd/metacog/
```
