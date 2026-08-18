"""Volume-estimation algorithms with a common estimator interface.

Every estimator returns a `lidar_core.models.VolumeResult`. Results are raw
geometric quantities -- converting them to commercial timber cubicacion
requires Campo Digital's proprietary rules, which are explicitly OUT OF
SCOPE here. Never conflate `VolumeResult.volume` with a commercial figure.
"""
