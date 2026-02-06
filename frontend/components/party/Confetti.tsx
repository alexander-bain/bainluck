"use client";

import { useEffect, useRef, useCallback } from "react";

interface ConfettiProps {
  /** Whether confetti is currently active */
  active: boolean;
  /** Duration in ms before confetti stops spawning */
  duration?: number;
  /** Team colors to use for confetti pieces */
  colors?: string[];
}

interface Particle {
  x: number;
  y: number;
  vx: number;
  vy: number;
  w: number;
  h: number;
  color: string;
  rotation: number;
  rotationSpeed: number;
  gravity: number;
  opacity: number;
  decay: number;
}

const DEFAULT_COLORS = [
  "#FFD700", "#FF6B6B", "#4ECDC4", "#45B7D1",
  "#96CEB4", "#FFEAA7", "#DDA0DD", "#98D8C8",
  "#FF7675", "#74B9FF", "#A29BFE", "#FD79A8",
];

/**
 * Canvas-based confetti animation for lead change celebrations.
 * Fires from the center-top when activated.
 */
export default function Confetti({
  active,
  duration = 3000,
  colors = DEFAULT_COLORS,
}: ConfettiProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const particlesRef = useRef<Particle[]>([]);
  const animFrameRef = useRef<number>(0);
  const spawnEndRef = useRef<number>(0);

  const createParticle = useCallback(
    (canvas: HTMLCanvasElement): Particle => {
      const centerX = canvas.width / 2;
      return {
        x: centerX + (Math.random() - 0.5) * 200,
        y: -10,
        vx: (Math.random() - 0.5) * 12,
        vy: Math.random() * 4 + 2,
        w: Math.random() * 10 + 5,
        h: Math.random() * 6 + 3,
        color: colors[Math.floor(Math.random() * colors.length)],
        rotation: Math.random() * Math.PI * 2,
        rotationSpeed: (Math.random() - 0.5) * 0.2,
        gravity: 0.12 + Math.random() * 0.08,
        opacity: 1,
        decay: 0.003 + Math.random() * 0.003,
      };
    },
    [colors]
  );

  useEffect(() => {
    if (!active) return;

    const canvas = canvasRef.current;
    if (!canvas) return;

    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    particlesRef.current = [];
    spawnEndRef.current = Date.now() + duration;

    // Spawn initial burst
    for (let i = 0; i < 80; i++) {
      particlesRef.current.push(createParticle(canvas));
    }

    const animate = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      // Spawn more particles while within duration
      if (Date.now() < spawnEndRef.current) {
        for (let i = 0; i < 3; i++) {
          particlesRef.current.push(createParticle(canvas));
        }
      }

      // Update and draw particles
      particlesRef.current = particlesRef.current.filter((p) => {
        p.x += p.vx;
        p.vy += p.gravity;
        p.y += p.vy;
        p.vx *= 0.99;
        p.rotation += p.rotationSpeed;
        p.opacity -= p.decay;

        if (p.opacity <= 0 || p.y > canvas.height + 20) return false;

        ctx.save();
        ctx.translate(p.x, p.y);
        ctx.rotate(p.rotation);
        ctx.globalAlpha = p.opacity;
        ctx.fillStyle = p.color;
        ctx.fillRect(-p.w / 2, -p.h / 2, p.w, p.h);
        ctx.restore();

        return true;
      });

      if (particlesRef.current.length > 0) {
        animFrameRef.current = requestAnimationFrame(animate);
      }
    };

    animFrameRef.current = requestAnimationFrame(animate);

    return () => {
      cancelAnimationFrame(animFrameRef.current);
    };
  }, [active, duration, createParticle]);

  if (!active && particlesRef.current.length === 0) return null;

  return (
    <canvas
      ref={canvasRef}
      className="fixed inset-0 pointer-events-none"
      style={{ zIndex: 9999 }}
    />
  );
}
