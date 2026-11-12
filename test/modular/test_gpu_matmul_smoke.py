"""A bf16 matmul on the real GPU agrees with fp32 on the CPU, so a broken CUDA install fails here, not mid-serve."""

import pytest
import torch


@pytest.mark.skipif(not torch.cuda.is_available(), reason="needs a GPU")
@pytest.mark.parametrize("seed", range(3))
def test_a_bf16_matmul_on_the_gpu_matches_fp32_on_the_cpu(seed):
    g = torch.Generator().manual_seed(seed)
    a, b = torch.randn(256, 512, generator=g), torch.randn(512, 128, generator=g)
    want = a @ b
    got = (a.cuda().bfloat16() @ b.cuda().bfloat16()).float().cpu()
    torch.testing.assert_close(got, want, rtol=2e-2, atol=0.5)
