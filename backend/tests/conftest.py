import os, sys, pathlib, tempfile
os.environ["DATABASE_URL"] = "sqlite://"                      # in-memory, shared via StaticPool
os.environ["UPLOAD_DIR"] = tempfile.mkdtemp(prefix="cascade_uploads_")
os.environ.pop("GEMINI_API_KEY", None)
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent)); sys.path.insert(0, str(pathlib.Path(__file__).parent))
