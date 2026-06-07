"""ONNX Runtime classifier wrapper for a single ROI presence model."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List

import numpy as np

from .preprocess import preprocess

logger = logging.getLogger(__name__)


@dataclass
class ClassifierResult:
    label: str
    confidence: float
    probabilities: Dict[str, float]


def _softmax(x: np.ndarray) -> np.ndarray:
    x = x - np.max(x)
    e = np.exp(x)
    return e / np.sum(e)


class OnnxClassifier:
    """Loads an ONNX model once and classifies BGR ROI crops.

    Thread-safety: ONNX Runtime sessions are thread-safe for inference, so a
    single instance is shared across requests.
    """

    def __init__(self, onnx_path: str, classes: List[str], input_spec: Dict,
                 providers: List[str] | None = None) -> None:
        import onnxruntime as ort

        self.onnx_path = onnx_path
        self.classes = classes
        self.input_spec = input_spec
        sess_options = ort.SessionOptions()
        sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        sess_options.intra_op_num_threads = 0  # let ORT pick (all cores)
        self.session = ort.InferenceSession(
            onnx_path,
            sess_options=sess_options,
            providers=providers or ["CPUExecutionProvider"],
        )
        self._input_name = self.session.get_inputs()[0].name
        self._output_name = self.session.get_outputs()[0].name

    def classify(self, crop_bgr: np.ndarray) -> ClassifierResult:
        tensor = preprocess(crop_bgr, self.input_spec)
        outputs = self.session.run([self._output_name], {self._input_name: tensor})
        logits = np.asarray(outputs[0]).reshape(-1)

        # Accept either probabilities (sum~1, all in [0,1]) or raw logits.
        if logits.min() < 0 or logits.max() > 1.0 or abs(float(logits.sum()) - 1.0) > 0.05:
            probs = _softmax(logits)
        else:
            probs = logits

        idx = int(np.argmax(probs))
        label = self.classes[idx] if idx < len(self.classes) else str(idx)
        prob_map = {
            self.classes[i] if i < len(self.classes) else str(i): float(probs[i])
            for i in range(len(probs))
        }
        return ClassifierResult(label=label, confidence=float(probs[idx]), probabilities=prob_map)
