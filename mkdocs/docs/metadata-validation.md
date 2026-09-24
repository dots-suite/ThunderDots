# Metadata and validation

## Metadata filtering

ThunderDots separates Dublin Core metadata from extension metadata.

```python
resource_params = {
    "metadata_dublincore": ["identifier", "title", "creator", "date", "coverage"],
    "metadata_extensions": ["dct:coverage", "dct:extend"],
}
```

`None` keeps all metadata. An empty list `[]` keeps none.

## Temporal metadata

`DotsNotice` exposes temporal helpers derived from fields such as `date`, `issued`, `created` and `coverage`.

!!! warning "EDTF compliance" 
    The temporal index is a flat dictionary. For each temporal field whose value can be parsed, it adds `<field>_start`, `<field>_end` (years as integers, astronomical numbering) and `<field>_start_iso`, `<field>_end_iso` (full ISO dates). The parser covers EDTF level 0 and the main level 1 features:

    - years and dates: `1280`, `-0500`, `1280-03`, `1280-03-04`, with the sign and four-digit padding of ISO 8601 (`-0500` is 501 BC, `0000` is 1 BC);
    - intervals: `1280/1329`, `-0500/0499`, `1157-03/1158-01`, open or unknown ends `1250/..` and `../1250`;
    - qualifiers `?`, `~` and `%`, in the level 1 position (`1280?/1329~`) or the level 2 positions (`~1455`, `2004-06~-11`), which are ignored;
    - unspecified digits: `12XX` covers 1200 to 1299, `1157-XX` the whole year;
    - long years: `Y-12000`;
    - level 2 sets, reduced to their overall span: `[1667,1668,1670..1672]` covers 1667 to 1672.

    The ISO bounds keep the precision of the value: `1280` covers `1280-01-01` to `1280-12-31`, `1200-09` covers `1200-09-01` to `1200-09-30`, `1173-05-02` covers that single day, and `-0500` covers `-0500-01-01` to `-0500-12-31`. Years written with fewer than four digits (`800`, `-50`) are not valid EDTF but are tolerated and read as the padded year. A valid date without a usable year (`XXXX-04-12`) and any non-EDTF value (`created:"1966-1998"`, `12 septembre 1399`, `XIVe siècle`) are kept raw and produce no `_start` / `_end` keys. The script `scripts/check_dates.py` tells the two cases apart and can scan a live collection for values ThunderDots cannot read.

```python
notice = td.notices()[0]
print(notice.date_start)
print(notice.date_end)
print(notice.temporal_index)
```

```json
{
"dublincore.coverage":"1280/1329",
"dublincore.coverage_start":"1280",
"dublincore.coverage_start_iso":"1280-01-01",
"dublincore.coverage_end":"1329",
"dublincore.coverage":"1280/1329",
"dublincore.coverage_start":"1280",
"dublincore.coverage_start_iso":"1280-01-01",
"dublincore.coverage_end":"1329",
"dublincore.coverage":"1280/1329",
"dublincore.coverage_start":"1280",
"dublincore.coverage_start_iso":"1280-01-01",
"dublincore.coverage_end":"1329",
"dublincore.coverage_end_iso":"1329-12-31",
"dublincore.created":"1966-1998",
"dublincore.issued":"2024",
"dublincore.issued_start":"2024",
"dublincore.issued_start_iso":"2024-01-01",
"dublincore.issued_end":"2024",
"dublincore.issued_end_iso":"2024-12-31",
"extensions.@context.dateCreated":"schema:dateCreated",
"extensions.@context.datePublished":"schema:datePublished",
"extensions.@context.temporalCoverage":"schema:temporalCoverage",
"extensions.dateCreated":"1966-1998",
"extensions.datePublished":"2024",
"extensions.datePublished_start":"2024",
"extensions.datePublished_start_iso":"2024-01-01",
"extensions.datePublished_end":"2024",
"extensions.datePublished_end_iso":"2024-12-31",
"extensions.temporalCoverage":"1280/1329",
"extensions.temporalCoverage_start":"1280",
"extensions.temporalCoverage_start_iso":"1280-01-01",
"extensions.temporalCoverage_end":"1329",
"extensions.temporalCoverage_end_iso":"1329-12-31"
}

```

## Fragment-level metadata and temporal index

Each fragment carries its own `metadata` block, built from the DTS navigation member that describes it (`dublincore`, `extensions`) and, optionally, from dates found in the TEI with `temporal_xpath` (`tei`). When `fragment_params` is given, a per-fragment `temporal` index is computed from that block only.

Two sources of dates are possible, and they can be combined:

- **DTS navigation metadata**: the `/navigation` member exposes Dublin Core or extension fields such as `date`, `coverage` or `temporalCoverage`.
- **TEI dates**: the TEI encodes a date inside each section (`<docDate>`, `<date when="...">`, `<date notBefore="..." notAfter="...">`), reachable with `temporal_xpath`.

### Example 1: dates from DTS navigation metadata

No `temporal_xpath` here: the temporal index only uses the metadata that the DTS server exposes for each citable unit. The fragment below is described by a navigation member carrying `dublinCore.date`.

```python
td = ThunderDots(
    endpoint_dts=ENDPOINT_DTS,
    collection_params={"collection_id": COLLECTION_ID},
    resource_params={"fragment_mode": "navigation"},
    fragment_params={
        "metadata_dublincore": ["title", "date"],
        "metadata_extensions": ["temporalCoverage"],
    },
)
td.fetch()

fragment = td.results()["resource_results"][0]["fragments"][4]
```

```json
{
  "id": "CART_SAMPLE_0002",
  "head": "Sentence arbitrale.",
  "content": "...",
  "metadata": {
    "dublincore": {"title": "Sentence arbitrale.", "date": "1173-05-02"}
  },
  "temporal": {
    "dublincore.date": "1173-05-02",
    "dublincore.date_start": 1173,
    "dublincore.date_start_iso": "1173-05-02",
    "dublincore.date_end": 1173,
    "dublincore.date_end_iso": "1173-05-02"
  }
}
```

A fragment whose navigation member has no temporal field gets `"temporal": {}`. This is the case for every fragment of a server that only exposes `title` in `/navigation`, such as the DoTS `cartulaires` collection: use `temporal_xpath` there (Example 2).

### Example 2: dates from the TEI with `temporal_xpath`

The XPath is evaluated relative to each fragment node in the TEI document. Matching values are stored under `metadata.tei.date` and indexed as `tei.date_*`. In the DoTS cartulaires, each act is a `<text>` whose `<front>` holds a `<docDate>`.

```python
td = ThunderDots(
    endpoint_dts="https://dev.chartes.psl.eu/dots/api/dts",
    collection_params={"collection_id": "HDPAR-HD"},
    resource_params={"fragment_mode": "navigation"},
    fragment_params={
        "metadata_dublincore": ["title", "language"],
        "metadata_extensions": ["name"],
        "temporal_xpath": ".//tei:docDate/tei:date",
    },
)
td.fetch()

fragment = td.results()["resource_results"][0]["fragments"][3]
```

```json
{
  "id": "HDPAR-HD_0001",
  "head": "1 (1157)",
  "content": "...",
  "metadata": {
    "dublincore": {"title": "1 (1157)", "language": "lat"},
    "extensions": {"name": "1 (1157)"},
    "tei": {"date": "1157"}
  },
  "temporal": {
    "tei.date": "1157",
    "tei.date_start": 1157,
    "tei.date_start_iso": "1157-01-01",
    "tei.date_end": 1157,
    "tei.date_end_iso": "1157-12-31"
  }
}
```

For a matched `<date>` element, TEI dating attributes take precedence over its text, in this order: `@when`, then `@notBefore`/`@notAfter` (stored as a `start/end` range), then `@from`/`@to`. A date located inside a descendant fragment is ignored, so a container section never takes over the dates of the acts it contains. When several values match, the first one is stored in `tei.date` and the full list in `tei.dates`.

`temporal_xpath` also works in `tei_xpath` and `document` modes, where no navigation metadata exists: the TEI is then the only source of fragment dates.

!!! note "No inheritance from the resource"
    A fragment without explicit temporal metadata gets an empty `temporal` index (`{}`). Resource-level dates such as a global `coverage` are never copied into fragments, because they do not necessarily apply to a given section. When a downstream index needs them, export them explicitly with `to_qdrant_fragment_points(include_resource_temporal=True)`: they are then added under the distinct `resource_temporal` namespace.

The same data is available as objects:

```python
notice = td.notices()[0]
for fragment in notice.fragment_objects():
    print(fragment.id, fragment.dublincore.get("title"), fragment.temporal_index)
```

## Automatic validation

```python
td = ThunderDots(
    endpoint_dts=ENDPOINT_DTS,
    collection_params={"collection_id": COLLECTION_ID},
    resource_params={"fragment_mode": "document"},
    validate=True,
)

td.fetch()
print(td.results()["validation"])
```

## Manual validation

```python
from thunderdots.validation import validate_notice, validate_many

output_report = validate_notice(td.results(), profile="output")
resource_report = validate_many(
    td.results().get("resource_results", []),
    profile="resource_result",
)

print(output_report.to_dict())
print(resource_report.summary())
```

Validation checks the JSON structure. It does not guarantee the scholarly correctness of the content.
