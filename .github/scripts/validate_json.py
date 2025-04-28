import os
import json
import sys
import importlib.util

VALIDATOR_ROOT = ".github/scripts/validators"
TARGET_ROOT = "Muninn/data"

def load_validator(folder_name):
    try:
        path = os.path.join(VALIDATOR_ROOT, f"{folder_name}.py")
        if not os.path.isfile(path):
            return None
        spec = importlib.util.spec_from_file_location(f"validators.{folder_name}", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.validate
    except Exception as e:
        print(f"[ERROR] Loading validator for '{folder_name}': {e}")
        return None

def validate_json_file(filepath, validator_fn):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return validator_fn(data, filepath)
    except Exception as e:
        print(f"[ERROR] Failed to parse {filepath}: {e}")
        return False

def walk_and_validate():
    all_valid = True
    for root, dirs, files in os.walk(TARGET_ROOT):
        folder_name = os.path.basename(root)
        validator_fn = load_validator(folder_name)
        if validator_fn is None:
            continue  # Skip folders without validators

        print(f"🔍 Validating files in: {root}")
        for file in files:
            if file.endswith(".json"):
                filepath = os.path.join(root, file)
                if not validate_json_file(filepath, validator_fn):
                    all_valid = False
    return all_valid

if __name__ == "__main__":
    success = walk_and_validate()
    if not success:
        sys.exit(1)
