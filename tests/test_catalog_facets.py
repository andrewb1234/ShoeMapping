from shoe_catalog_facets import build_shoe_facets


def test_build_shoe_facets_derives_roles_and_bands() -> None:
    shoes = [
        {
            "shoe_id": "road::easy",
            "terrain": "Road",
            "lab_test_results": {
                "Terrain": "Road",
                "Weight": "10.1 oz (286g)",
                "Drop": "9.0 mm",
                "Heel stack": "39.0 mm",
                "Forefoot stack": "31.0 mm",
                "Midsole softness (new method)": "18.0 HA",
                "Torsional rigidity (old method)": "4",
                "Heel counter stiffness": "4",
                "Pace": "Daily running",
            },
        },
        {
            "shoe_id": "road::fast",
            "terrain": "Road",
            "lab_test_results": {
                "Terrain": "Road",
                "Weight": "7.0 oz (198g)",
                "Drop": "4.0 mm",
                "Heel stack": "31.0 mm",
                "Forefoot stack": "27.0 mm",
                "Energy return heel": "66%",
                "Midsole softness (new method)": "24.0 HA",
                "Pace": "Tempo | Race",
            },
        },
    ]

    enrichment = build_shoe_facets(shoes)

    assert enrichment["road::easy"]["facets"]["ride_role"] == "easy"
    assert enrichment["road::easy"]["facets"]["cushion_level"] in {"high", "max"}
    assert enrichment["road::fast"]["facets"]["ride_role"] in {"race", "uptempo"}
    assert enrichment["road::fast"]["facets"]["drop_band"] == "low"
