"""Double snap (or clap) wakes JARVIS; talking, music and single snaps don't."""
import numpy as np

from jarvis import clap

RATE, BLOCK = 16000, 320


def run(signal):
    fired = []
    det = clap.ClapDetector(lambda: fired.append(1))
    for i in range(0, len(signal) - BLOCK, BLOCK):
        det.feed(i / RATE, *clap.features(signal[i:i + BLOCK]))
    return len(fired)


def room(seconds, noise=0.004, seed=1):
    return np.random.default_rng(seed).normal(0, noise, int(RATE * seconds)).astype(np.float32)


def snap(sig, at, amp=0.09, seed=2):
    n = int(RATE * .012)   # a 12 ms crisp burst
    burst = np.random.default_rng(seed).normal(0, 1, n)
    burst = np.diff(burst, prepend=0) * np.exp(-np.linspace(0, 6, n))   # high-pitched, quickly fading
    i = int(at * RATE)
    sig[i:i + n] += (amp * burst / np.abs(burst).max()).astype(np.float32)
    return sig


def test_two_snaps_wake_jarvis():
    s = room(3)
    snap(s, 1.0); snap(s, 1.45, seed=3)
    assert run(s) == 1


def test_one_snap_or_talking_does_not():
    s = room(3)
    snap(s, 1.0)
    assert run(s) == 0
    t = np.arange(int(RATE * 3)) / RATE
    voice = (0.3 * np.sin(2 * np.pi * 180 * t) * (0.5 + 0.5 * np.sin(2 * np.pi * 3 * t))).astype(np.float32)
    assert run(voice + room(3)) == 0
    music = (0.25 * (np.sin(2 * np.pi * 220 * t) + np.sin(2 * np.pi * 330 * t))).astype(np.float32)
    assert run(music + room(3)) == 0


def test_claps_still_work():
    s = room(3)
    for at in (1.0, 1.4):
        i = int(at * RATE)
        s[i:i + 600] += (0.6 * np.random.default_rng(int(at * 10)).normal(0, 1, 600) * np.exp(-np.linspace(0, 5, 600))).astype(np.float32)
    assert run(s) == 1
