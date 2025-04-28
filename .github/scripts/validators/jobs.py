def validate(data, filename):
    required_keys = {"name", "introduction", "proficiency", "results"}

    if not required_keys.issubset(data.keys()):
        print(f"[{filename}] Missing keys: {required_keys - data.keys()}")
        return False

    for stage in data.get("results", []):
        if not all(k in stage for k in ["stage", "job_title", "hourly_wage", "hourly_xp", "range", "results"]):
            print(f"[{filename}] Stage missing required fields.")
            return False
        if not isinstance(stage["results"], list):
            print(f"[{filename}] 'results' in stage {stage['stage']} must be a list.")
            return False

    return True
