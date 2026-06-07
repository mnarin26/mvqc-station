"""Model bundle sync clients.

A model bundle is a ZIP with ``manifest.json`` (ModelBundleManifest) + one ONNX
file per ROI. Import flow:
  1. read + validate manifest,
  2. match each model to a local ROI (product -> active recipe -> surface_index
     + roi_index),
  3. verify each ONNX SHA-256 against the manifest,
  4. stage the ONNX under the models dir,
  5. atomically activate (write ``models`` + ``model_deployments`` rows, keep the
     previous deployment for one-click rollback),
  6. hot-reload the model registry and flip the product to ``ready`` when fully
     covered.

``LocalUsbSyncClient`` handles a local file (USB now). ``NetworkSyncClient``
keeps the same activation path for a future pull-from-server mode.
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from ..db.repositories import (
    ModelRepository,
    ProductRepository,
    RecipeRepository,
    RoiRepository,
    SurfaceRepository,
    write_audit,
)
from ..schemas.manifest import ModelBundleManifest

logger = logging.getLogger(__name__)


class SyncError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


class LocalUsbSyncClient:
    source = "manual_usb"

    def __init__(self, settings, db, model_registry=None) -> None:
        self.settings = settings
        self.db = db
        self.model_registry = model_registry
        self.models_root = Path(settings.paths.models)

    # ------------------------------------------------------------- importing
    def import_bundle(self, bundle_path: str, deployed_by: Optional[str] = "operator") -> Dict:
        bundle_path = Path(bundle_path)
        if not bundle_path.exists():
            raise SyncError(f"bundle not found: {bundle_path}")

        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            try:
                with zipfile.ZipFile(bundle_path) as zf:
                    zf.extractall(tmp_dir)
            except zipfile.BadZipFile as exc:
                raise SyncError(f"invalid bundle archive: {exc}") from exc

            manifest_file = tmp_dir / "manifest.json"
            if not manifest_file.exists():
                raise SyncError("bundle missing manifest.json")
            manifest = ModelBundleManifest.model_validate_json(manifest_file.read_text())

            resolved, skipped = self._resolve_targets(manifest)
            to_deploy = [
                m for m in manifest.models
                if (m.surface_index, m.roi_index) in resolved
            ]
            if not to_deploy:
                raise SyncError(
                    "no manifest models match the active recipe ROIs "
                    f"(skipped {skipped})"
                )
            staged = self._verify_and_stage(to_deploy, manifest.product_name, tmp_dir, resolved)
            deployed = self._activate(manifest, staged, deployed_by)

        # Hot-reload registry + product readiness.
        if self.model_registry is not None:
            self.model_registry.load_active()
        self._update_product_readiness(manifest.product_name)

        return {
            "status": "activated",
            "product": manifest.product_name,
            "deployed": deployed,
            "count": len(deployed),
            "skipped": [{"surface_index": s, "roi_index": r} for s, r in skipped],
            "source": self.source,
        }

    def _resolve_targets(self, manifest: ModelBundleManifest) -> tuple[Dict[tuple, int], List[tuple]]:
        """Map (surface_index, roi_index) -> roi_id using the product's active recipe.

        Extra manifest entries with no matching recipe ROI are returned in
        ``skipped`` instead of failing the whole import (partial deploy).
        """
        with self.db.session() as s:
            product = ProductRepository(s).by_name(manifest.product_name)
            if not product and manifest.product_barcode:
                product = ProductRepository(s).by_barcode(manifest.product_barcode)
            if not product:
                raise SyncError(f"unknown product '{manifest.product_name}'")
            recipe = RecipeRepository(s).active_for_product(product.id)
            if not recipe:
                raise SyncError(f"product '{manifest.product_name}' has no active recipe")
            mapping: Dict[tuple, int] = {}
            for surface in recipe.surfaces:
                for roi in surface.rois:
                    mapping[(surface.surface_index, roi.roi_index)] = roi.id
        skipped = [
            (m.surface_index, m.roi_index)
            for m in manifest.models
            if (m.surface_index, m.roi_index) not in mapping
        ]
        return mapping, skipped

    def _verify_and_stage(self, models, product_name: str, tmp_dir: Path,
                          resolved: Dict[tuple, int]) -> List[Dict]:
        staged = []
        for m in models:
            src = tmp_dir / m.onnx_file
            if not src.exists():
                raise SyncError(f"onnx file missing in bundle: {m.onnx_file}")
            actual = _sha256(src)
            if actual.lower() != m.checksum_sha256.lower():
                raise SyncError(
                    f"checksum mismatch for {m.onnx_file}: "
                    f"expected {m.checksum_sha256[:12]}..., got {actual[:12]}..."
                )
            roi_id = resolved[(m.surface_index, m.roi_index)]
            dest_dir = self.models_root / product_name / f"roi_{roi_id}"
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / f"{m.version}.onnx"
            shutil.copy2(src, dest)
            staged.append({"roi_id": roi_id, "model": m, "onnx_path": str(dest), "checksum": actual})
        return staged

    def _activate(self, manifest, staged: List[Dict], deployed_by: Optional[str]) -> List[Dict]:
        deployed = []
        with self.db.session() as s:
            models = ModelRepository(s)
            for item in staged:
                m = item["model"]
                model_row = models.add_model(
                    roi_id=item["roi_id"],
                    version=m.version,
                    onnx_path=item["onnx_path"],
                    classes=json.dumps(m.classes),
                    input_spec=json.dumps(m.input_spec),
                    metrics=json.dumps(m.metrics) if m.metrics else None,
                    checksum=item["checksum"],
                    training_run_id=m.training_run_id,
                )
                models.deploy(item["roi_id"], model_row.id, self.source, deployed_by)
                deployed.append({
                    "roi_id": item["roi_id"], "version": m.version, "model_id": model_row.id,
                })
            write_audit(s, "INFO", "deploy",
                        f"imported {len(deployed)} models for {manifest.product_name}",
                        {"product": manifest.product_name, "by": deployed_by,
                         "source": self.source})
        return deployed

    def _update_product_readiness(self, product_name: str) -> None:
        with self.db.session() as s:
            product = ProductRepository(s).by_name(product_name)
            if not product:
                return
            recipe = RecipeRepository(s).active_for_product(product.id)
            if not recipe:
                return
            models = ModelRepository(s)
            all_covered = True
            for surface in recipe.surfaces:
                for roi in surface.rois:
                    if roi.inspector_type == "presence" and models.active_model(roi.id) is None:
                        all_covered = False
            ProductRepository(s).set_status(product.id, "ready" if all_covered else "teaching")

    # -------------------------------------------------------------- rollback
    def rollback_roi(self, roi_id: int, deployed_by: Optional[str] = "operator") -> Dict:
        with self.db.session() as s:
            deployment = ModelRepository(s).rollback(roi_id, deployed_by)
            if deployment is None:
                raise SyncError(f"no previous model to roll back to for ROI {roi_id}")
            write_audit(s, "WARN", "deploy", f"rolled back ROI {roi_id}",
                        {"roi_id": roi_id, "by": deployed_by})
        if self.model_registry is not None:
            self.model_registry.reload_roi(roi_id)
        return {"status": "rolled_back", "roi_id": roi_id}


class NetworkSyncClient(LocalUsbSyncClient):
    """Future networked deployment: pull bundles from a central model server.

    Reuses the import/activate path; only acquisition differs. Left as a stub so
    V1 stays simple while the seam is in place.
    """

    source = "network"

    def __init__(self, settings, db, model_registry=None, server_url: str | None = None) -> None:
        super().__init__(settings, db, model_registry)
        self.server_url = server_url

    def pull_latest(self, product_name: str) -> Dict:  # pragma: no cover - future
        raise NotImplementedError(
            "network sync is planned for V2; configure a model server and "
            "download a bundle, then call import_bundle()"
        )

    def upload_dataset(self, archive_path: str) -> Dict:  # pragma: no cover - future
        raise NotImplementedError("network dataset upload is planned for V2")
