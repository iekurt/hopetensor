def validate_regions(regions, vulnerability):
    for r in regions:
        if r not in vulnerability:
            raise ValueError(f"Missing vulnerability value for region: {r}")
