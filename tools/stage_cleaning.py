#stage_cleaning.py

import ota, os

# Remove leftover staging artifacts
try:
    ota._rm_tree("/staging/app_new")
except Exception:
    pass

try:
    os.remove("/staging/_manifest_tmp.json")
except Exception:
    pass

print("Staging cleaned.")
