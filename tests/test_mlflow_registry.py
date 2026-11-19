"""Optional registry checks; run with the MLflow environment."""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys

import pytest

mlflow = pytest.importorskip("mlflow")

from geolife_inference.config import Config
from geolife_inference.sqlite_history import SCHEMA


@pytest.fixture(scope="module")
def saved_bundle(tmp_path_factory):
    directory = tmp_path_factory.mktemp("registry")
    snapshot = directory / "gps.sqlite3"
    with closing(sqlite3.connect(snapshot)) as connection:
        connection.executescript(SCHEMA)
        connection.execute("INSERT INTO snapshot VALUES ('test-registry')")
        connection.execute("INSERT INTO gps_points VALUES ('001', 'short', 1, 39.9, 116.3, NULL, 1704067200000000000)")
        connection.commit()
    with snapshot.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    config = Config()
    manifest = directory / "manifest.json"
    manifest.write_text(json.dumps({"snapshot_sha256": digest, "data_snapshot_id": "test-registry",
                                    "config": config.to_dict(), **config.version_metadata(),
                                    "model_version": "dbscan-v1"}), encoding="utf-8")
    root = Path(__file__).resolve().parents[1]
    bundle = directory / "model"
    mlflow.pyfunc.save_model(
        path=str(bundle), python_model=str(root / "scripts/mlflow_geolife_model.py"),
        code_paths=[str(root / "src/geolife_inference")],
        artifacts={"history": str(snapshot), "manifest": str(manifest)},
        pip_requirements=[f"mlflow=={mlflow.__version__}"],
    )
    # Loading must continue to work when the original source artifacts are gone.
    snapshot.unlink()
    manifest.unlink()
    return bundle


def test_bundle_predicts_in_fresh_process_after_source_artifacts_removed(saved_bundle, tmp_path):
    result = subprocess.run(
        [sys.executable, "-X", "utf8", "-c",
         "import json,sys,mlflow,pandas as pd; "
         "model=mlflow.pyfunc.load_model(sys.argv[1]); "
         "print(model.predict(pd.DataFrame({'user_id':['001']})).iloc[0]['prediction_json'])",
         str(saved_bundle)], cwd=tmp_path, capture_output=True, text=True, encoding="utf-8", timeout=60,
    )
    assert result.returncode == 0, result.stderr
    prediction = json.loads(result.stdout)
    assert prediction["user_id"] == "001"
    assert prediction["model_version"] == "dbscan-v1"
    assert prediction["data_snapshot_id"] == "test-registry"
    assert prediction["diagnostics"]["input_points"] == 1
    assert prediction["home"]["status"] == prediction["office"]["status"] == "unknown"


@pytest.mark.parametrize("artifact", ["history", "manifest"])
def test_modified_packaged_artifacts_are_rejected(saved_bundle, tmp_path, artifact):
    bundle = tmp_path / "model"
    shutil.copytree(saved_bundle, bundle)
    spec = mlflow.models.Model.load(str(bundle)).flavors["python_function"]["artifacts"]
    path = bundle / spec[artifact]["path"]
    if artifact == "history":
        with path.open("ab") as stream:
            stream.write(b"changed")
        message = "GPS snapshot does not match"
    else:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["config"]["distance_m"] = 150.0
        path.write_text(json.dumps(manifest), encoding="utf-8")
        message = "configuration does not match"
    with pytest.raises(ValueError, match=message):
        mlflow.pyfunc.load_model(str(bundle))
