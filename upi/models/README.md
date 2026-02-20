Models moved to `models/` to keep the repo clean and avoid large binaries at repo root.

Restore instructions:
- To restore a model back to the repo root, copy the file from `models/` to the project root and name it `<model_name>_model.pkl`.

Notes:
- The application now loads pickles from `models/<name>_model.pkl`.
- Keep these files out of source control if they are large or sensitive; they are ignored by `.gitignore`.