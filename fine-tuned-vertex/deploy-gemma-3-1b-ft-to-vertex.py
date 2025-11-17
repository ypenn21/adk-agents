# Import the necessary packages
import importlib
import os
from google.api_core.protobuf_helpers import get_messages
from typing import Tuple
from google.cloud import aiplatform

import google.auth
import openai

PROJECT_ID = os.environ['PROJECT_ID']
REGION = os.environ['REGION']
PROJECT_NUMBER = os.environ['PROJECT_NUMBER']
MODEL_PATH = os.environ['MODEL_PATH']
MODEL_NAME = os.environ['MODEL_NAME']

# Initialize Vertex AI API.
print("Initializing Vertex AI API.")
aiplatform.init(project=PROJECT_ID, location=REGION)

# Gets the default SERVICE_ACCOUNT.
SERVICE_ACCOUNT = f"{PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
print("Using this default Service Account:", SERVICE_ACCOUNT)

# ! gcloud config set project $PROJECT_ID
import vertexai

vertexai.init(
    project=PROJECT_ID,
    location=REGION,
)
# Set the model to deploy.
models, endpoints = {}, {}

# Define the GCS path for your fine-tuned model.
model_id = f"gs://the-fine-tuners{MODEL_PATH}"
model_name = MODEL_NAME

# The pre-built serving docker image.
VLLM_DOCKER_URI = "us-docker.pkg.dev/vertex-ai/vertex-vision-model-garden-dockers/pytorch-vllm-serve:20250312_0916_RC01"

# Set use_dedicated_endpoint to False
use_dedicated_endpoint = False 

# Set accelerator type, count and deployment configurations.
accelerator_type = "NVIDIA_L4"
machine_type = "g2-standard-16"
accelerator_count = 1

gpu_memory_utilization = 0.95
max_model_len = 32768

# Deploy with customized configs
def deploy_model_vllm(
    model_name: str,
    model_id: str,
    publisher: str,
    publisher_model_id: str,
    base_model_id: str = None,
    machine_type: str = machine_type,
    accelerator_type: str = accelerator_type,
    accelerator_count: int = accelerator_count,
    gpu_memory_utilization: float = gpu_memory_utilization,
    max_model_len: int = max_model_len,
    dtype: str = "auto",
    enable_trust_remote_code: bool = False,
    enforce_eager: bool = False,
    enable_lora: bool = False,
    enable_chunked_prefill: bool = False,
    enable_prefix_cache: bool = False,
    host_prefix_kv_cache_utilization_target: float = 0.0,
    max_loras: int = 1,
    max_cpu_loras: int = 8,
    use_dedicated_endpoint: bool = False,
    max_num_seqs: int = 256,
    model_type: str = None,
    enable_llama_tool_parser: bool = False,
) -> Tuple[aiplatform.Model, aiplatform.Endpoint]:

    """Deploys trained models with vLLM into Vertex AI."""
    endpoint = aiplatform.Endpoint.create(
        display_name=f"{model_name}-endpoint",
        dedicated_endpoint_enabled=use_dedicated_endpoint,
    )

    if not base_model_id:
        base_model_id = model_id

    # See https://docs.vllm.ai/en/latest/models/engine_args.html for a list of possible arguments with descriptions.
    vllm_args = [
        "python",
        "-m",
        "vllm.entrypoints.api_server",
        "--host=0.0.0.0",
        "--port=8080",
        f"--model={model_id}",
        f"--tensor-parallel-size={accelerator_count}",
        "--swap-space=16",
        f"--gpu-memory-utilization={gpu_memory_utilization}",
        f"--max-model-len={max_model_len}",
        f"--dtype={dtype}",
        f"--max-loras={max_loras}",
        f"--max-cpu-loras={max_cpu_loras}",
        f"--max-num-seqs={max_num_seqs}",
        "--disable-log-stats",
        "--enable-auto-tool-choice",
        "--tool-call-parser=pythonic",
    ]

    if enable_trust_remote_code:
        vllm_args.append("--trust-remote-code")

    if enforce_eager:
        vllm_args.append("--enforce-eager")

    if enable_lora:
        vllm_args.append("--enable-lora")

    if enable_chunked_prefill:
        vllm_args.append("--enable-chunked-prefill")

    if enable_prefix_cache:
        vllm_args.append("--enable-prefix-caching")

    if 0 < host_prefix_kv_cache_utilization_target < 1:
        vllm_args.append(
            f"--host-prefix-kv-cache-utilization-target={host_prefix_kv_cache_utilization_target}"
        )

    if model_type:
        vllm_args.append(f"--model-type={model_type}")

    if enable_llama_tool_parser:
        vllm_args.append("--enable-auto-tool-choice")
        vllm_args.append("--tool-call-parser=vertex-llama-3")

    env_vars = {
        "MODEL_ID": base_model_id,
        "DEPLOY_SOURCE": "notebook",
    }

    # Prepare arguments for Model.upload
    upload_kwargs = {
        "display_name": model_name,
        "serving_container_image_uri": VLLM_DOCKER_URI,
        "serving_container_args": vllm_args,
        "serving_container_ports": [8080],
        "serving_container_predict_route": "/generate",
        "serving_container_health_route": "/ping",
        "serving_container_environment_variables": env_vars,
        "serving_container_shared_memory_size_mb": (16 * 1024),  # 16 GB
        "serving_container_deployment_timeout": 7200,
    }

    # Add model garden source only if publisher and publisher_model_id are provided
    if publisher and publisher_model_id:
        upload_kwargs["model_garden_source_model_name"] = (
            f"publishers/{publisher}/models/{publisher_model_id}"
        )

    model = aiplatform.Model.upload(**upload_kwargs)

    print(
        f"Deploying {model_name} on {machine_type} with {accelerator_count} {accelerator_type} GPU(s)."
    )


    model.deploy(
        endpoint=endpoint,
        machine_type=machine_type,
        accelerator_type=accelerator_type,
        accelerator_count=accelerator_count,
        deploy_request_timeout=3600,
    )
    print("endpoint_name:", endpoint.name)

    return model, endpoint

models["vllm_gpu"], endpoints["vllm_gpu"] = deploy_model_vllm(
    model_name=model_name,
    model_id=model_id,
    publisher="google",
    publisher_model_id="gemma3",
    machine_type=machine_type,
    accelerator_type=accelerator_type,
    accelerator_count=accelerator_count,
    gpu_memory_utilization=gpu_memory_utilization,
    max_model_len=max_model_len,
    use_dedicated_endpoint=use_dedicated_endpoint,
)