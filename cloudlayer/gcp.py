"""GCP adapter. Implements upload/download/push_image for Lab 1.

SDK:  pip install google-cloud-storage google-cloud-aiplatform
Docs: storage.Client for GCS; Artifact Registry push goes through `docker push` after
      `gcloud auth configure-docker <region>-docker.pkg.dev`.

Layer 2 rules this file obeys:
  * BLOB_URI looks like gs://bucket/prefix — parsed here, never in src/.
  * Artifact Registry paths are region-scoped:
        <region>-docker.pkg.dev/<project>/<repo>/<image>
    A common first failure is pushing to gcr.io out of habit; it is a different service.
  * push_image returns the digest reference, not the tag.
  * GCP calls them labels, not tags, and they must be lowercase with no spaces.
    cfg.tags(1) already satisfies that constraint — the values are used as they stand.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from cloudlayer.base import CloudAdapter


def _split_gs_uri(uri: str) -> tuple[str, str]:
    """gs://bucket/some/prefix -> ('bucket', 'some/prefix'). Prefix may be empty."""
    if not uri.startswith("gs://"):
        raise ValueError(f"Not a GCS URI: {uri!r}. Expected gs://bucket[/prefix].")
    bucket, _, prefix = uri[len("gs://"):].partition("/")
    if not bucket:
        raise ValueError(f"No bucket in {uri!r}.")
    return bucket, prefix.strip("/")


def _run(cmd: list[str]) -> str:
    out = subprocess.run(cmd, capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)} failed:\n{out.stderr.strip()}")
    return out.stdout.strip()


class GcpAdapter(CloudAdapter):
    def _bucket(self):
        from google.cloud import storage

        bucket_name, prefix = _split_gs_uri(self.cfg.blob_uri)
        client = storage.Client(project=self.cfg.project_id)
        return client.bucket(bucket_name), prefix

    def upload(self, local_path: str, key: str) -> str:
        bucket, prefix = self._bucket()
        blob_name = f"{prefix}/{key.lstrip('/')}" if prefix else key.lstrip("/")
        blob = bucket.blob(blob_name)
        blob.upload_from_filename(local_path)
        return f"gs://{bucket.name}/{blob_name}"

    def download(self, uri: str, local_path: str) -> None:
        from google.cloud import storage

        bucket_name, blob_name = _split_gs_uri(uri)
        if not blob_name:
            raise ValueError(f"No object path in {uri!r}.")
        target = Path(local_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        client = storage.Client(project=self.cfg.project_id)
        client.bucket(bucket_name).blob(blob_name).download_to_filename(str(target))

    def push_image(self, local_tag: str) -> str:
        registry = self.cfg.container_registry.rstrip("/")
        host = registry.split("/", 1)[0]
        remote = f"{registry}/{local_tag.rsplit('/', 1)[-1]}"

        # Idempotent, and cheap if the helper is already configured.
        _run(["gcloud", "auth", "configure-docker", host, "--quiet"])
        _run(["docker", "tag", local_tag, remote])
        _run(["docker", "push", remote])

        # The tag we just pushed can be moved later; the digest cannot. Read it back
        # from the registry rather than trusting the local daemon's view.
        repo = remote.rsplit(":", 1)[0]
        digest = _run([
            "gcloud", "artifacts", "docker", "images", "describe", remote,
            "--project", self.cfg.project_id, "--format", "value(image_summary.digest)",
        ])
        return f"{repo}@{digest}"

    # submit_training / register_model  -> Lab 2 (Vertex custom training + Model Registry)
    # deploy / invoke                   -> Lab 3 (Vertex Endpoint)
    # emit_metric                       -> Lab 4 (Cloud Monitoring time series)
    # generate                          -> Lab 5 (managed LLM endpoint; read usageMetadata for tokens)
    # teardown                          -> Lab 5 (filter resources by label)
