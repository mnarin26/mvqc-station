"""SQLAlchemy ORM models mirroring the MVQC SQLite schema (eMMC / SSD-1).

These mappings are the source of truth for the schema; the migration runner in
``migrations.py`` creates them on a fresh database and tracks additive upgrades.
JSON-bearing TEXT columns are stored as strings and (de)serialized by callers /
repositories to keep the schema portable and inspectable with the sqlite3 CLI.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    ForeignKey,
    Integer,
    REAL,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)

NOW = text("(datetime('now'))")


class Base(DeclarativeBase):
    pass


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    barcode: Mapped[Optional[str]] = mapped_column(String, unique=True)
    surface_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # draft | teaching | ready | disabled
    status: Mapped[str] = mapped_column(String, nullable=False, default="draft")
    created_at: Mapped[str] = mapped_column(Text, nullable=False, server_default=NOW)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False, server_default=NOW)

    recipes: Mapped[List["Recipe"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )


class Recipe(Base):
    __tablename__ = "recipes"
    __table_args__ = (UniqueConstraint("product_id", "version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pass_rule: Mapped[str] = mapped_column(String, nullable=False, default="all_filled")
    created_at: Mapped[str] = mapped_column(Text, nullable=False, server_default=NOW)

    product: Mapped["Product"] = relationship(back_populates="recipes")
    surfaces: Mapped[List["Surface"]] = relationship(
        back_populates="recipe", cascade="all, delete-orphan"
    )


class Surface(Base):
    __tablename__ = "surfaces"
    __table_args__ = (UniqueConstraint("recipe_id", "surface_index"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    recipe_id: Mapped[int] = mapped_column(
        ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False
    )
    surface_index: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[Optional[str]] = mapped_column(String)
    reference_image_path: Mapped[Optional[str]] = mapped_column(Text)
    capture_settings: Mapped[Optional[str]] = mapped_column(Text)  # JSON

    recipe: Mapped["Recipe"] = relationship(back_populates="surfaces")
    rois: Mapped[List["Roi"]] = relationship(
        back_populates="surface", cascade="all, delete-orphan"
    )


class Roi(Base):
    __tablename__ = "rois"
    __table_args__ = (UniqueConstraint("surface_id", "roi_index"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    surface_id: Mapped[int] = mapped_column(
        ForeignKey("surfaces.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[Optional[str]] = mapped_column(String)
    roi_index: Mapped[int] = mapped_column(Integer, nullable=False)
    # presence | ocr | count | color | anomaly | wrong_component
    inspector_type: Mapped[str] = mapped_column(String, nullable=False, default="presence")
    geometry: Mapped[str] = mapped_column(Text, nullable=False)  # JSON {points:[[x,y],...]}
    params: Mapped[Optional[str]] = mapped_column(Text)  # JSON
    threshold: Mapped[float] = mapped_column(REAL, nullable=False, default=0.5)

    surface: Mapped["Surface"] = relationship(back_populates="rois")


class Model(Base):
    __tablename__ = "models"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    roi_id: Mapped[int] = mapped_column(
        ForeignKey("rois.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[str] = mapped_column(String, nullable=False)
    onnx_path: Mapped[str] = mapped_column(Text, nullable=False)
    classes: Mapped[str] = mapped_column(Text, nullable=False)  # JSON ["EMPTY","FILLED"]
    input_spec: Mapped[str] = mapped_column(Text, nullable=False)  # JSON
    metrics: Mapped[Optional[str]] = mapped_column(Text)  # JSON
    checksum: Mapped[str] = mapped_column(Text, nullable=False)
    training_run_id: Mapped[Optional[str]] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(Text, nullable=False, server_default=NOW)


class ModelDeployment(Base):
    __tablename__ = "model_deployments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    roi_id: Mapped[int] = mapped_column(
        ForeignKey("rois.id", ondelete="CASCADE"), nullable=False
    )
    model_id: Mapped[int] = mapped_column(ForeignKey("models.id"), nullable=False)
    is_active: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    source: Mapped[str] = mapped_column(String, nullable=False)  # manual_usb | network
    deployed_at: Mapped[str] = mapped_column(Text, nullable=False, server_default=NOW)
    deployed_by: Mapped[Optional[str]] = mapped_column(String)
    previous_model_id: Mapped[Optional[int]] = mapped_column(ForeignKey("models.id"))


class TeachingSession(Base):
    __tablename__ = "teaching_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    surface_id: Mapped[int] = mapped_column(
        ForeignKey("surfaces.id", ondelete="CASCADE"), nullable=False
    )
    label: Mapped[str] = mapped_column(String, nullable=False)  # EMPTY | FILLED
    status: Mapped[str] = mapped_column(String, nullable=False, default="capturing")
    created_at: Mapped[str] = mapped_column(Text, nullable=False, server_default=NOW)

    samples: Mapped[List["TeachingSample"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class TeachingSample(Base):
    __tablename__ = "teaching_samples"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("teaching_sessions.id", ondelete="CASCADE"), nullable=False
    )
    roi_id: Mapped[int] = mapped_column(
        ForeignKey("rois.id", ondelete="CASCADE"), nullable=False
    )
    label: Mapped[str] = mapped_column(String, nullable=False)
    image_path: Mapped[str] = mapped_column(Text, nullable=False)
    exposure: Mapped[Optional[float]] = mapped_column(REAL)
    gain: Mapped[Optional[float]] = mapped_column(REAL)
    lighting: Mapped[Optional[str]] = mapped_column(Text)
    captured_at: Mapped[str] = mapped_column(Text, nullable=False, server_default=NOW)

    session: Mapped["TeachingSession"] = relationship(back_populates="samples")


class InspectionCycle(Base):
    __tablename__ = "inspection_cycles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id"), nullable=False)
    barcode: Mapped[Optional[str]] = mapped_column(String)
    result: Mapped[Optional[str]] = mapped_column(String)  # PASS | FAIL
    started_at: Mapped[str] = mapped_column(Text, nullable=False, server_default=NOW)
    finished_at: Mapped[Optional[str]] = mapped_column(Text)
    operator: Mapped[Optional[str]] = mapped_column(String)
    station_id: Mapped[str] = mapped_column(String, nullable=False)

    inspections: Mapped[List["Inspection"]] = relationship(
        back_populates="cycle", cascade="all, delete-orphan"
    )


class Inspection(Base):
    __tablename__ = "inspections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cycle_id: Mapped[int] = mapped_column(
        ForeignKey("inspection_cycles.id", ondelete="CASCADE"), nullable=False
    )
    surface_id: Mapped[int] = mapped_column(ForeignKey("surfaces.id"), nullable=False)
    surface_index: Mapped[int] = mapped_column(Integer, nullable=False)
    result: Mapped[str] = mapped_column(String, nullable=False)  # PASS | FAIL
    overall_confidence: Mapped[Optional[float]] = mapped_column(REAL)
    full_image_path: Mapped[Optional[str]] = mapped_column(Text)
    roi_archive_dir: Mapped[Optional[str]] = mapped_column(Text)
    saved: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    saved_reason: Mapped[Optional[str]] = mapped_column(String)  # FAIL|LOW_CONF|RANDOM|ALL
    timestamp: Mapped[str] = mapped_column(Text, nullable=False, server_default=NOW)

    cycle: Mapped["InspectionCycle"] = relationship(back_populates="inspections")
    roi_results: Mapped[List["InspectionRoiResult"]] = relationship(
        back_populates="inspection", cascade="all, delete-orphan"
    )


class InspectionRoiResult(Base):
    __tablename__ = "inspection_roi_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    inspection_id: Mapped[int] = mapped_column(
        ForeignKey("inspections.id", ondelete="CASCADE"), nullable=False
    )
    roi_id: Mapped[int] = mapped_column(ForeignKey("rois.id"), nullable=False)
    roi_name: Mapped[Optional[str]] = mapped_column(String)
    predicted_label: Mapped[str] = mapped_column(String, nullable=False)
    confidence: Mapped[float] = mapped_column(REAL, nullable=False)
    decision: Mapped[str] = mapped_column(String, nullable=False)  # OK | WARN | NOK
    severity: Mapped[str] = mapped_column(String, nullable=False, default="ok")  # ok | warning | error
    roi_image_path: Mapped[Optional[str]] = mapped_column(Text)

    inspection: Mapped["Inspection"] = relationship(back_populates="roi_results")


class Export(Base):
    __tablename__ = "exports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    export_date: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    zip_path: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[Optional[int]] = mapped_column(Integer)
    item_count: Mapped[Optional[int]] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    created_at: Mapped[str] = mapped_column(Text, nullable=False, server_default=NOW)


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[str] = mapped_column(Text, nullable=False, server_default=NOW)
    level: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[Optional[str]] = mapped_column(Text)  # JSON
