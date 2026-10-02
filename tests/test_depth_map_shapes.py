import numpy as np
import pytest
import torch

from vggt.utils.geometry import unproject_depth_map_to_point_map


@pytest.mark.parametrize("width", [1, 4])
@pytest.mark.parametrize("tensor_input", [False, True])
@pytest.mark.parametrize("channel_axis", [False, True])
def test_depth_unprojection_preserves_spatial_axes(width, tensor_input, channel_axis):
    depths = np.arange(1, 1 + 2 * 3 * width, dtype=np.float32).reshape(2, 3, width)
    poses = np.broadcast_to(np.eye(4, dtype=np.float32)[:3], (2, 3, 4)).copy()
    poses[1, :, 3] = [0.2, -0.1, 0.3]
    intrinsics = np.broadcast_to(
        np.array([[2.0, 0.0, 0.5], [0.0, 3.0, 1.0], [0.0, 0.0, 1.0]], dtype=np.float32),
        (2, 3, 3),
    ).copy()
    u, v = np.meshgrid(np.arange(width), np.arange(3))
    expected = np.stack(
        [(u - 0.5) * depths / 2, (v - 1.0) * depths / 3, depths], axis=-1
    )
    expected -= poses[:, None, None, :, 3]
    if channel_axis:
        depths = depths[..., None]
    if tensor_input:
        depths, poses, intrinsics = map(torch.from_numpy, (depths, poses, intrinsics))
    output = unproject_depth_map_to_point_map(depths, poses, intrinsics)
    assert output.shape == (2, 3, width, 3)
    np.testing.assert_allclose(output, expected, atol=1e-6)
