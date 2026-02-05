import os
import glob

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
md_files = glob.glob(os.path.join(root, '*.md'))
removed = []
for f in md_files:
    try:
        os.remove(f)
        removed.append(os.path.basename(f))
    except Exception as e:
        print(f"Skipping {f}: {e}")

print("Removed .md files:", removed)
