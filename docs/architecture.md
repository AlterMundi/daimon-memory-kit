# Architecture

DaimonMemoryKit separates durable native records, retrieval, source ingestion,
selective capture, consolidation, harness access and reviewed publication.
SQLite retains originals, history, links and source metadata. The worker keeps
processing resumable; operational alerts expose failures and recovery.

An independently authored LLM Wiki remains authoritative for its own files;
DMK can index those files for retrieval. The former generated Obsidian vault
and its exporter have been removed. Existing local notes are never deleted.
See [the memory ownership contract](memory-ownership-contract.md).

The Daimon projection is a second, explicitly marked retrieval origin inside
SQLite. Daimon Matrix owns the source event chain and policy; DMK owns only the
local index and receipts. Writes cross the closed versioned API, never raw SQL
or generic librarian mutation. See [the projection contract](daimon-projection.md).

`publish_collective.py` is deliberately outside retrieval and projection. It
reads DMK in SQLite read-only mode, accepts only dual-opted-in DMK-native
records, produces an exact review plan, and requires an independent approval
bound to that plan before writing derived Markdown to a collective-memory
corpus. See [the publication contract](collective-memory-publication.md).
