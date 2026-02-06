"use client";

import { useEffect, useRef } from "react";

interface PulseECGProps {
  /** Pulse score 1-100 (controls animation speed) */
  score: number;
  /** Color of the ECG line */
  color?: string;
  /** Height of the component */
  height?: number;
}

/**
 * ECG-style heartbeat animation that beats faster when Pulse score is higher.
 * Renders an animated SVG polyline that scrolls left to right.
 */
export default function PulseECG({
  score,
  color = "#ef4444",
  height = 60,
}: PulseECGProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const phaseRef = useRef(0);
  const animRef = useRef<number>(0);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const resize = () => {
      canvas.width = canvas.offsetWidth * 2;
      canvas.height = height * 2;
    };
    resize();

    // Speed: higher pulse = faster heartbeat
    // Score 20 = 0.5 beats/sec, Score 100 = 3 beats/sec
    const beatsPerSecond = 0.5 + (score / 100) * 2.5;
    const pixelsPerFrame = 2 + (score / 100) * 3;

    // ECG waveform shape (one cycle)
    const ecgWaveform = (t: number): number => {
      // t goes from 0 to 1 for one heartbeat cycle
      // Flat -> small P wave -> flat -> sharp QRS -> flat -> T wave -> flat
      if (t < 0.1) return 0; // baseline
      if (t < 0.15) return Math.sin((t - 0.1) * Math.PI / 0.05) * 0.15; // P wave
      if (t < 0.25) return 0; // PR segment
      if (t < 0.28) return -(t - 0.25) * 10; // Q dip
      if (t < 0.33) return -0.3 + (t - 0.28) * 26; // R spike up
      if (t < 0.38) return 1.0 - (t - 0.33) * 26; // R spike down to S
      if (t < 0.42) return -0.3 + (t - 0.38) * 7.5; // S recovery
      if (t < 0.55) return 0; // ST segment
      if (t < 0.7) return Math.sin((t - 0.55) * Math.PI / 0.15) * 0.25; // T wave
      return 0; // baseline
    };

    const animate = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      const w = canvas.width;
      const h = canvas.height;
      const midY = h / 2;
      const amplitude = h * 0.35;

      // Advance phase
      phaseRef.current += pixelsPerFrame;

      // Calculate cycle length in pixels
      const cyclePixels = w / (beatsPerSecond * 2);

      // Draw the ECG line
      ctx.beginPath();
      ctx.strokeStyle = color;
      ctx.lineWidth = 3;
      ctx.shadowColor = color;
      ctx.shadowBlur = 8;
      ctx.lineJoin = "round";
      ctx.lineCap = "round";

      for (let x = 0; x < w; x++) {
        // Calculate which point in the waveform cycle this x corresponds to
        const worldX = x + phaseRef.current;
        const cyclePos = (worldX % cyclePixels) / cyclePixels;
        const y = midY - ecgWaveform(cyclePos) * amplitude;

        if (x === 0) {
          ctx.moveTo(x, y);
        } else {
          ctx.lineTo(x, y);
        }
      }
      ctx.stroke();

      // Draw a glowing dot at the leading edge
      const leadX = w * 0.75;
      const leadWorldX = leadX + phaseRef.current;
      const leadCyclePos = (leadWorldX % cyclePixels) / cyclePixels;
      const leadY = midY - ecgWaveform(leadCyclePos) * amplitude;

      ctx.beginPath();
      ctx.arc(leadX, leadY, 4, 0, Math.PI * 2);
      ctx.fillStyle = color;
      ctx.shadowBlur = 16;
      ctx.fill();

      // Fade out trailing edge
      const gradient = ctx.createLinearGradient(0, 0, w * 0.15, 0);
      gradient.addColorStop(0, "rgba(0,0,0,1)");
      gradient.addColorStop(1, "rgba(0,0,0,0)");
      ctx.globalCompositeOperation = "destination-in";
      ctx.fillStyle = "white";
      ctx.fillRect(0, 0, w, h);
      ctx.globalCompositeOperation = "source-over";

      animRef.current = requestAnimationFrame(animate);
    };

    animRef.current = requestAnimationFrame(animate);

    return () => cancelAnimationFrame(animRef.current);
  }, [score, color, height]);

  return (
    <canvas
      ref={canvasRef}
      className="w-full"
      style={{ height: `${height}px` }}
    />
  );
}
