import numpy as np

from app.services.road_terrain import TerrainSpan, prepare_terrain


def test_lateral_flag_repairs_a_spike_while_preserving_the_road_trend():
    meters = np.arange(0., 331., 30.)
    original = 1500 + .08 * meters
    raw = original.copy()
    raw[5] += 36
    suspect = np.zeros(len(meters), dtype=bool)
    suspect[5] = True
    x, heights, spans = prepare_terrain(meters, raw, suspect, [], 30)
    assert np.allclose(x, meters)
    assert np.allclose(heights, original)
    assert spans == (TerrainSpan(120., 180., "uncertain"),)


def test_bridge_and_tunnel_use_the_approach_grade_with_exact_boundaries():
    meters = np.arange(0., 631., 30.)
    original = 1000 + .05 * meters
    raw = original.copy()
    raw[(meters >= 120) & (meters <= 240)] -= 60  # the stream bed under a bridge
    raw[(meters >= 390) & (meters <= 510)] += 70  # the hill above a tunnel
    structures = [TerrainSpan(150., 165., "bridge"), TerrainSpan(411., 465., "tunnel")]
    # The sampled ground near the tagged spans is inside their approach buffer.
    raw[(meters < 120) | ((meters > 195) & (meters < 390)) | (meters > 495)] = original[
        (meters < 120) | ((meters > 195) & (meters < 390)) | (meters > 495)
    ]
    x, heights, spans = prepare_terrain(meters, raw, np.zeros(len(meters), dtype=bool), structures, 30)
    assert all(value in x for value in (150., 165., 411., 465.))
    assert spans == tuple(structures)
    assert np.allclose(heights, 1000 + .05 * x)
