#!/usr/bin/env python3
"""
Script kiểm tra GPU availability (CUDA/ROCm).
Chạy: python test_gpu.py
"""

import sys


def check_gpu():
    """Kiểm tra GPU availability và in thông tin chi tiết."""
    print("=" * 50)
    print("🔍 GPU Availability Check")
    print("=" * 50)

    # Check PyTorch
    try:
        import torch

        print(f"\n📦 PyTorch version: {torch.__version__}")

        cuda_available = torch.cuda.is_available()
        print(f"\n🎮 CUDA/ROCm available: {cuda_available}")

        if cuda_available:
            print(f"   - Device count: {torch.cuda.device_count()}")
            print(f"   - Current device: {torch.cuda.current_device()}")
            print(f"   - Device name: {torch.cuda.get_device_name(0)}")

            # GPU Memory info
            props = torch.cuda.get_device_properties(0)
            total_memory = props.total_memory / (1024**3)
            print(f"   - GPU Memory: {total_memory:.2f} GB")
            print(f"   - Compute capability: {props.major}.{props.minor}")

            # Test tensor creation on GPU
            try:
                test_tensor = torch.randn(1000, 1000, device="cuda")
                print("\n✅ Successfully created tensor on GPU")
                print(f"   - Tensor shape: {test_tensor.shape}")
                print(f"   - Tensor device: {test_tensor.device}")
            except Exception as e:
                print(f"\n❌ Failed to create tensor on GPU: {e}")

        else:
            print("\n⚠️  No GPU detected. Using CPU mode.")
            print("\n💡 Để sử dụng GPU AMD với ROCm:")
            print(
                "   1. Cài đặt ROCm driver: sudo apt-get install rocm-dev rocm-libs rocm-utils"
            )
            print("   2. Cài đặt PyTorch với ROCm:")
            print(
                "      pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/rocm5.7"
            )

    except ImportError:
        print("❌ PyTorch không được cài đặt. Cài đặt với:")
        print("   pip install torch torchvision torchaudio")
        return False

    # Check sentence-transformers
    try:
        import sentence_transformers

        print(
            f"\n📦 Sentence-Transformers version: {sentence_transformers.__version__}"
        )
    except ImportError:
        print("\n⚠️  Sentence-Transformers không được cài đặt")

    print("\n" + "=" * 50)
    return cuda_available


def check_rocm():
    """Kiểm tra ROCm installation."""
    print("\n🔍 ROCm Installation Check")
    print("-" * 30)

    import subprocess

    try:
        # Check rocminfo
        result = subprocess.run(
            ["rocminfo"], capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            print("✅ rocminfo available")
            # Parse GPU info
            lines = result.stdout.split("\n")
            for line in lines:
                if "Marketing Name" in line:
                    print(f"   - {line.strip()}")
        else:
            print("⚠️  rocminfo not found or error")
    except FileNotFoundError:
        print("⚠️  rocminfo command not found. ROCm có thể chưa được cài đặt.")
    except subprocess.TimeoutExpired:
        print("⚠️  rocminfo timeout")
    except Exception as e:
        print(f"⚠️  Error checking ROCm: {e}")

    # Check rocm-smi
    try:
        result = subprocess.run(
            ["rocm-smi"], capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            print("\n✅ rocm-smi available:")
            print(result.stdout[:500])  # Print first 500 chars
        else:
            print("⚠️  rocm-smi not found or error")
    except FileNotFoundError:
        print("⚠️  rocm-smi command not found")
    except subprocess.TimeoutExpired:
        print("⚠️  rocm-smi timeout")
    except Exception as e:
        print(f"⚠️  Error checking rocm-smi: {e}")


if __name__ == "__main__":
    has_gpu = check_gpu()

    if has_gpu:
        check_rocm()

    sys.exit(0 if has_gpu else 1)
