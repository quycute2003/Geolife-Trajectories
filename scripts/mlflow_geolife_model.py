"""Runnable MLflow model: user IDs in, full inference JSON out."""
import hashlib
import json
from pathlib import Path

import mlflow
import pandas as pd

from geolife_inference.config import Config
from geolife_inference.pipeline import run_pipeline
from geolife_inference.sqlite_history import SQLiteHistory


class GeoLifeModel(mlflow.pyfunc.PythonModel):
    def load_context(self, context):
        manifest = json.loads(Path(context.artifacts["manifest"]).read_text(encoding="utf-8"))
        snapshot = Path(context.artifacts["history"])
        with snapshot.open("rb") as stream:
            snapshot_sha256 = hashlib.file_digest(stream, "sha256").hexdigest()
        if snapshot_sha256 != manifest["snapshot_sha256"]:
            raise ValueError("The packaged GPS snapshot does not match the manifest.")
        self.history = SQLiteHistory(snapshot)
        if self.history.snapshot_id != manifest["data_snapshot_id"]:
            raise ValueError("The packaged GPS snapshot ID does not match the manifest.")
        self.config = Config(**manifest["config"])
        if self.config.version_metadata()["config_sha256"] != manifest["config_sha256"]:
            raise ValueError("The packaged configuration does not match the manifest.")
        self.model_version = manifest["model_version"]

    def predict(self, context, model_input, params=None):
        if not isinstance(model_input, pd.DataFrame) or list(model_input.columns) != ["user_id"]:
            raise ValueError("Send a DataFrame containing only the user_id column.")
        users = model_input["user_id"].tolist()
        if any(not isinstance(user, str) or not 1 <= len(user) <= 64 for user in users):
            raise ValueError("Each user_id must be a string containing 1..64 characters.")
        results = []
        for user_id in users:
            points = self.history.load_user(user_id)
            if points is None:
                raise ValueError(f"No GPS history for user_id={user_id!r} in this snapshot.")
            result = run_pipeline(points, user_id, self.config, self.model_version).result
            result["data_snapshot_id"] = self.history.snapshot_id
            results.append({"user_id": user_id, "model_version": self.model_version,
                            "prediction_json": json.dumps(result, allow_nan=False)})
        return pd.DataFrame(results, columns=["user_id", "model_version", "prediction_json"])


mlflow.models.set_model(GeoLifeModel())
