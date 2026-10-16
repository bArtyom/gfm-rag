from __future__ import annotations

import importlib.metadata
import importlib.util
import inspect
import os
import sys
import traceback
from pathlib import Path

from gfmrag_p1_common import load_official_qwen3_class


PROJECT_ROOT = Path(__file__).resolve().parents[1]
UPSTREAM_ROOT = PROJECT_ROOT / "upstream" / "gfm-rag"
sys.path.insert(0, str(UPSTREAM_ROOT))

print(f"python={sys.version.split()[0]}")
print(f"executable={sys.executable}")
print(f"cuda_visible_devices={os.environ.get('CUDA_VISIBLE_DEVICES')}")
print(f"local_rank={os.environ.get('LOCAL_RANK')}")
for package in (
    "torch",
    "vllm",
    "transformers",
    "openai",
    "sentence-transformers",
    "datasets",
):
    try:
        version = importlib.metadata.version(package)
    except importlib.metadata.PackageNotFoundError:
        version = "MISSING"
    print(f"package.{package}={version}")

try:
    import torch

    print(f"torch.version.cuda={torch.version.cuda}")
    print(f"torch.cuda.is_available={torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"torch.cuda.device_count={torch.cuda.device_count()}")
        for device_id in range(torch.cuda.device_count()):
            print(f"torch.cuda.device.{device_id}={torch.cuda.get_device_name(device_id)}")
except Exception as exc:  # report the environment failure without changing it
    print(f"torch.cuda.error={type(exc).__name__}: {exc}")

for module in ("vllm", "sentence_transformers", "datasets"):
    try:
        spec = importlib.util.find_spec(module)
        print(f"module.{module}={'FOUND' if spec else 'MISSING'}")
    except Exception as exc:
        print(f"module.{module}=ERROR {type(exc).__name__}: {exc}")

try:
    from vllm import LLM, PoolingParams

    print(f"vllm.api.LLM={LLM.__module__}.{LLM.__name__}")
    print(f"vllm.api.PoolingParams={PoolingParams.__module__}.{PoolingParams.__name__}")
except Exception as exc:
    print(f"vllm.api.error={type(exc).__name__}: {exc}")

try:
    from gfmrag.text_emb_models.qwen3_model import Qwen3TextEmbModel

    print(
        "gfmrag.qwen3.import=OK "
        f"({Qwen3TextEmbModel.__module__}.{Qwen3TextEmbModel.__name__})"
    )
except Exception as exc:
    print(f"gfmrag.qwen3.import=ERROR {type(exc).__name__}: {exc}")
    traceback.print_exc(file=sys.stdout, limit=12)

try:
    qwen3_class = load_official_qwen3_class()
    print(
        "gfmrag.qwen3.selective_import=OK "
        f"({qwen3_class.__module__}.{qwen3_class.__name__}) "
        f"source={inspect.getfile(qwen3_class)}"
    )
except Exception as exc:
    print(
        "gfmrag.qwen3.selective_import=ERROR "
        f"{type(exc).__name__}: {exc}"
    )
    traceback.print_exc(file=sys.stdout, limit=12)

model_path = Path("/mnt/liansp3/sources/models/qwen3-embedding-0.6b")
print(f"model_path.exists={model_path.exists()}")
if model_path.exists():
    print(f"model_path.target={model_path.resolve()}")

print("model_loaded=false")
