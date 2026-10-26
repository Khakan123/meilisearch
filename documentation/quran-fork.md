# Qur’an engine foundation

## Build provenance

Starting commits (before local changes):
- Charabia 0.10.0: `bc63b9860434f06cf78b51bb0eab00aaefb69f15`
- Meilisearch 1.55.0: `7b6f9f39bd91b04d4551673780cfeb31cb3f5e7b`

Use Rust 1.98.1 and keep the repositories as siblings:

```text
jamia-ms/
  charabia/charabia/Cargo.toml
  meilisearch/Cargo.toml
```

The workspace Cargo patch points to `../charabia/charabia`. Its companion
`irg-kvariants` package also resolves locally. `Cargo.lock` pins the other
Meilisearch dependencies. Record both final fork commit IDs when committing or
publishing; the starting IDs above are provenance, not the modified release IDs.
No remote pushes, production index changes or portal changes are part of this work.

```powershell
# In charabia
cargo +1.98.1 test -p charabia --no-default-features
cargo +1.98.1 clippy -p charabia --no-default-features --all-targets -- -D warnings
cargo +1.98.1 fmt --all -- --check
# In meilisearch
cargo tree -i charabia --locked --depth 1
cargo build --release -p meilisearch --locked
cargo test --release -p meilisearch-types quran_locale_round_trip --locked
cargo test --release -p meilisearch --test integration search::locales --locked
python scripts/verify-quran.py target/release/meilisearch.exe
```

On Linux use `target/release/meilisearch` instead. The Python harness owns a fresh
loopback server and temporary database, removes inherited MEILI environment
settings, checks original text, matches, updates and restart persistence, then
prints indexing/median/p95 timings. It never contacts an existing search service.
These tiny-fixture timings do not predict full-corpus throughput or relevance.

## API use

Set `localizedAttributes` on every Qur’an searchable field:

```json
{
  "searchableAttributes": ["v_manzoor", "v_uthmani"],
  "localizedAttributes": [
    {"attributePatterns": ["v_manzoor", "v_uthmani"], "locales": ["qur"]}
  ],
  "typoTolerance": {"enabled": false},
  "prefixSearch": "disabled"
}
```

Search with `{"q":"كتاب","locales":["qur"],"attributesToHighlight":["v_manzoor"]}`.
Only a sole explicit `qur` selection activates the specialised pipeline; mixed
locale lists use ordinary automatic detection excluding Qur’an as a candidate.
Existing Arabic/Urdu processing stays on the ordinary pipeline. Stored text is
not rewritten. `qur-loose` is deliberately unsupported.

## Rules and limitations

Qur’an tokenisation preserves initial ال, NBSP joins and invisible internal
characters until original offsets are recorded. Ayah annotations, numeric-only
and ornament-only tokens are not indexed as words. Narrow/thin/ideographic spaces
are separators. Ordinary spaces remain boundaries: vocative joins are a later
application concern.

Normalisation folds keyboard variants, retains ۃ separately from ہ, and handles
dagger alif, tanween alif, hamza seats, small yeh and marks contextually. It never
removes ordinary alifs wholesale. Highlight maps retain original Unicode spans,
including deleted final marks and carriers.

U+0656 has different meanings in the two writing systems. A single `qur` locale
cannot reliably identify its source, so it is retained. U+0657 is removed as a
mark but is not used by itself to delete a following alif. These ambiguities need
source-aware corpus validation rather than a keyboard heuristic. No linguistic
accuracy claim is made beyond the fixture tests.

Prefix/suffix removal, plural mappings, lexical spelling tables, source-aware
cleaning, root search, result merging and full-corpus benchmarking remain for the
indexer/backend phase. No dictionaries or corpus-specific word lists are compiled
into Charabia. Empty normalised queries retain upstream empty-query behaviour.

## Execution record

- Baseline Arabic tests: 3 passed before changes.
- Initial Qur’an tests failed because `qur` did not exist, before implementation.
- Full minimal-feature Charabia run: 68 upstream unit tests, 9 doctests passed.
- Qur’an regressions additionally cover contextual equivalence, no loose matching,
  boundaries, explicit locale isolation, serialization, idempotence and offsets.
- Initial Windows Application Control block was resolved by the user.
- User removed the inherited Meilisearch AGENTS.md; that deletion is user-owned.
- Upstream contribution notices were inspected and left unchanged.
- Final review is a self-review; no code-review subagent is available in this session.


## Final verification results (2026-10-24)

- Final release binary built successfully with the sibling patched Charabia.
- Native locale integration tests: 16 passed, 0 failed, including
  `quran_locale_search_and_updates` and the existing locale regressions.
- Command: `cargo test --release -j 1 -p meilisearch --test integration search::locales --locked`.
- The parallel test build exhausted memory. The single-job retry succeeded;
  Cargo reported 628m 18s elapsed for compilation, then 3.66s for the 16 tests.
- Charabia verification: 68 upstream unit tests, 8 Quran tests and 9 doctests passed.
- Final-binary HTTP fixtures passed: 14 documents, 120 benchmark searches,
  original-text highlighting, document updates and restart persistence verified.
  Measured indexing: 130.32 ms; request median: 5.00 ms; p95: 25.44 ms.
  These small-fixture timings are not full-corpus performance guarantees.
- Strict Charabia Clippy encountered an existing lint in
  `normalizer/nonspacing_mark.rs` (`chunks_exact_to_as_chunks`). It passed with
  that specific lint allowed; formatting checks passed.


## Optional leading-ال alternatives (2026-10-25)

`quranArticleForms` is a query-only index setting, default `[]`. Each entry has
`withArticle` and `withoutArticle` strings. Both are strictly normalized with
`qur`, must be one complete word, differ by exactly one leading ال, and fit
milli's existing UTF-8 word-size limit. Invalid pairs are rejected; duplicates
are removed. PATCH all settings or GET/PUT/DELETE
`/indexes/{indexUid}/settings/quran-article-forms`; null/empty resets the feature.
It survives restart and dump/import; old indexes default to no alternatives.

Alternatives use existing full-word postings at the original query position.
The original query form remains the exact term; article alternatives are
zero-typo one-word derivations. Preserve the approved ranking precedence
`words`, `typo`, `exactness`, `proximity`, then the remaining rules. Ranking
configuration is not silently replaced: an index configured to rank position or
proximity before exactness will honor that configuration. Complete word coverage
still ranks before partial matches. Document text, token spans and highlighting
source maps are unchanged, and applying this setting does not reindex documents.

Expansion requires a sole effective `qur` locale and every searched field
localized exclusively as `qur`. It does not expand translations, mixed locales,
attached particles, contractions, suffixes, conjugations or unknown words.
Validated per-word alternatives are prepared in the settings write transaction
and read through point lookups. Queries do not normalize the entire rule set,
and an old read transaction retains its correct rule version during reset/update.

No Corpus dictionary is embedded in Charabia or Meilisearch. External generation
and verification tools are delivered in the search-engine repository under
`artifacts/quran-leading-al/`. Original Corpus v0.4 bytes, hashes, read-only
Directus snapshots, global-index provenance and exclusion reports are retained.
The current conservative set contains 809 canonical pairs. Ambiguous mappings,
lexical/protected endpoints, invalid verse spans and shared article/stem lam
spellings are excluded; original text is never repaired by the generator.

Build/test results for this extension are recorded separately in that artifact
folder. Earlier foundation results above refer to the previous binary.
