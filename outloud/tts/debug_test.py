"""Debug test for ONNX model outputs - inspects model structure."""

import sys
import pytest
import onnxruntime as ort
from python.runfiles import runfiles


def test_onnx_model_outputs():
    """Inspect what outputs the ONNX model provides."""
    r = runfiles.Create()
    model_path = r.Rlocation("kokoro_model/file/kokoro-v1.0.onnx")

    print(f"\nModel path: {model_path}")

    sess = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])

    print("\n=== Regular Model Inputs ===")
    for inp in sess.get_inputs():
        print(f"  {inp.name}: {inp.shape} ({inp.type})")

    print("\n=== Regular Model Outputs ===")
    for out in sess.get_outputs():
        print(f"  {out.name}: {out.shape} ({out.type})")


def test_timestamped_model_outputs():
    """Verify timestamped model has durations output."""
    r = runfiles.Create()
    model_path = r.Rlocation(
        "kokoro_model_timestamped/file/kokoro-v1.0-timestamped.onnx"
    )

    print(f"\nTimestamped model path: {model_path}")

    sess = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])

    print("\n=== Timestamped Model Inputs ===")
    for inp in sess.get_inputs():
        print(f"  {inp.name}: {inp.shape} ({inp.type})")

    print("\n=== Timestamped Model Outputs ===")
    for out in sess.get_outputs():
        print(f"  {out.name}: {out.shape} ({out.type})")

    output_names = [out.name for out in sess.get_outputs()]
    print(f"\nOutput names: {output_names}")

    assert len(output_names) == 2, "Timestamped model should have 2 outputs"
    assert "durations" in output_names, "Should have durations output"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v", "-s"] + sys.argv[1:]))
