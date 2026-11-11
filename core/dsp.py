import numpy as np
from typing import Optional


def to_mono_safe(interleaved_int16: np.ndarray, channels: int) -> np.ndarray:
    """Safely extracts the dominant mono channel by casting to Float32 first.
    
    Prevents 16-bit integer overflow wrap-around when computing channel energy.
    """
    if channels <= 1 or interleaved_int16.size == 0:
        return interleaved_int16

    try:
        reshaped = interleaved_int16.reshape(-1, channels)
        # Cast to float32 to avoid signed 16-bit integer overflow during absolute sum
        channel_energies = np.sum(np.abs(reshaped.astype(np.float32)), axis=0)
        strongest_channel = int(np.argmax(channel_energies))
        return reshaped[:, strongest_channel]
    except Exception:
        # Fallback to simple decimation on slicing failure
        return interleaved_int16[0::channels]


def apply_smart_agc(
    int16_data: np.ndarray,
    is_customer: bool = True,
    target_rms: float = 0.28,
    max_gain_customer: float = 20.0,
    max_gain_agent: float = 1.2,
    pre_emphasis_coef: float = 0.85
) -> np.ndarray:
    """Automatic Gain Control (AGC) with speech pre-emphasis filter.
    
    Dynamically normalizes input audio to target RMS while preserving speech transients.
    Loud audio spikes are safely compressed, and quiet telephony feeds are boosted.
    """
    if int16_data is None or len(int16_data) == 0:
        return int16_data

    try:
        float_data = int16_data.astype(np.float32) / 32768.0
        rms = float(np.sqrt(np.mean(float_data ** 2)))

        if is_customer:
            # First-order high-pass pre-emphasis filter: boosts higher speech frequencies (1 kHz - 4 kHz)
            if len(float_data) > 1:
                float_data = np.append(float_data[0], float_data[1:] - pre_emphasis_coef * float_data[:-1])

            # Dynamic RMS scaling bounded by max_gain_customer
            gain = target_rms / (rms + 1e-6)
            clamped_gain = min(gain, max_gain_customer)
            float_data = float_data * clamped_gain
        else:
            # Agent channel: apply conservative gain or zero-out ambient floor noise
            if rms > 0.005:
                gain = target_rms / (rms + 1e-6)
                clamped_gain = min(gain, max_gain_agent)
                float_data = float_data * clamped_gain
            else:
                return np.zeros_like(int16_data)

        # Symmetrical saturation clipping to int16 range
        return np.clip(float_data * 32768.0, -32768.0, 32767.0).astype(np.int16)
    except Exception:
        return int16_data


def resample_linear(mono_int16: np.ndarray, src_rate: int, target_rate: int = 16000) -> np.ndarray:
    """Fast linear interpolation index resampling for mono 16-bit PCM streams."""
    if src_rate == target_rate or mono_int16.size == 0:
        return mono_int16

    try:
        ratio = float(src_rate) / float(target_rate)
        target_len = int(len(mono_int16) / ratio)
        indices = np.arange(0, target_len) * ratio
        indices_int = np.clip(indices.astype(np.int32), 0, len(mono_int16) - 1)
        return mono_int16[indices_int]
    except Exception:
        return mono_int16
