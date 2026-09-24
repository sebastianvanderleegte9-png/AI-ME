"""Page templates (Component 7). Three shapes, each with:
  keyword_rule   how the target query is formed
  requires       data the page must have, or it is not generated
  sections       the order of blocks the renderer lays out
A page with no real data point is not a page; it is a thin doorway, and search engines
and readers both treat it as such."""

TEMPLATES = {
    "product_for_segment": {
        "keyword_rule": "{product} for {segment}",
        "requires": ["segment", "data_point", "proof"],
        "sections": ["hero", "data_point", "how_it_works", "proof", "faq", "cta"],
        "title": "{product} for {segment}",
        "description": "How {segment} use {product}: {data_point_short}.",
    },
    "competitor_alternative": {
        "keyword_rule": "{competitor} alternative",
        "requires": ["competitor", "data_point", "differences"],
        "sections": ["hero", "comparison", "data_point", "who_should_switch", "faq", "cta"],
        "title": "{competitor} alternative for {segment}: {product}",
        "description": "{product} vs {competitor} for {segment}: {data_point_short}.",
    },
    "use_case_with_data": {
        "keyword_rule": "{use_case} {segment}",
        "requires": ["use_case", "data_point", "steps"],
        "sections": ["hero", "data_point", "steps", "example", "faq", "cta"],
        "title": "{use_case} for {segment}: what the data shows",
        "description": "{data_point_short}. How {segment} do {use_case} with {product}.",
    },
}

MIN_WORDS = 350          # below this the page is not published
MAX_PAGES_PER_BATCH = 50
