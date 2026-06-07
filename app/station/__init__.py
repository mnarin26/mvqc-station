"""MVQC production-station application package.

Runs on the CM5 (cm5-101): camera acquisition, barcode reading, ROI extraction,
ONNX presence inference, OK/NOK decision, data collection and archiving, behind a
remote web HMI. All model training happens off-station on the training server.
"""

__version__ = "1.0.0"
