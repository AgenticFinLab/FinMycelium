# Media collection

The optional platform collector reads database settings from the working directory’s
`.env` and exported `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER` and `DB_PASSWORD`
variables. Exported values take precedence. Each child receives its own settings,
keywords and item limit. The bundled crawler writes to MySQL. The separate topic
reader also accepts PostgreSQL via `DB_DIALECT=postgresql`.

From an installed checkout, inspect the daily collector’s options with
`python -m finmy.url_collector.MediaCollector.media_get --help`. Its optional
browser and database dependencies are listed in the [upstream guide](MediaCrawler/README.md).
The [public search workflow](../../../docs/workflows/search-enhancement.md) uses its own providers.
