import { loadFont } from "@remotion/google-fonts/Inter";
import {
  AbsoluteFill,
  Easing,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

const { fontFamily } = loadFont("normal", {
  weights: ["300", "800"],
  subsets: ["latin"],
});

export const PRICE_REVEAL_DURATION = 105; // 3.5s at 30fps

const ACCENT = "#19D1B2";
const INK = "#0F172A";

const BAR_HEIGHT = 14;
const COUNT_START = 10;
const COUNT_END = 46;
const LOW = 100;
const HIGH = 300;

const countEase = Easing.bezier(0.16, 1, 0.3, 1);

const countProgress = (frame: number) =>
  interpolate(frame, [COUNT_START, COUNT_END], [0, 1], {
    easing: countEase,
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

export const PriceReveal: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Bar drops in from the top edge and settles with a small bounce.
  const barIn = spring({
    frame,
    fps,
    config: { damping: 11, stiffness: 170, mass: 0.6 },
  });
  const barY = interpolate(barIn, [0, 1], [-BAR_HEIGHT * 1.5, 0]);

  // Number counts up; blur follows the per-frame rate of change.
  const progress = countProgress(frame);
  const speed = progress - countProgress(frame - 1);
  const blur = Math.min(speed * 90, 5);
  const low = Math.round(LOW * progress);
  const high = Math.round(HIGH * progress);

  const numberOpacity = interpolate(
    frame,
    [COUNT_START, COUNT_START + 5],
    [0, 1],
    {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    },
  );

  // Soft snap + gentle scale pulse on landing.
  const land = spring({
    frame: frame - COUNT_END,
    fps,
    config: { damping: 9, stiffness: 200, mass: 0.5 },
  });
  const pulse = interpolate(land, [0, 0.5, 1], [0, 1, 0], {
    extrapolateRight: "clamp",
  });
  const scale = 1 + pulse * 0.04 + (1 - numberOpacity) * 0.04;

  // Light flare sweeps left to right across the number on landing.
  const flare = interpolate(frame, [COUNT_END + 2, COUNT_END + 22], [0, 100], {
    easing: Easing.inOut(Easing.cubic),
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // "per sqft" fades in right after the number settles.
  const subIn = interpolate(frame, [COUNT_END + 6, COUNT_END + 20], [0, 1], {
    easing: Easing.out(Easing.cubic),
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const priceText = `$${low}–$${high}`;
  const numberStyle: React.CSSProperties = {
    fontFamily,
    fontWeight: 800,
    fontSize: 220,
    letterSpacing: "-0.03em",
    lineHeight: 1,
    fontVariantNumeric: "tabular-nums",
    whiteSpace: "nowrap",
  };

  return (
    <AbsoluteFill style={{ backgroundColor: "#FFFFFF" }}>
      <div
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          right: 0,
          height: BAR_HEIGHT,
          backgroundColor: ACCENT,
          transform: `translateY(${barY}px)`,
        }}
      />

      <AbsoluteFill
        style={{ justifyContent: "center", alignItems: "center", gap: 18 }}
      >
        <div
          style={{
            position: "relative",
            opacity: numberOpacity,
            transform: `scale(${scale})`,
            filter: `blur(${blur}px)`,
          }}
        >
          <div
            style={{
              ...numberStyle,
              color: INK,
              textShadow:
                "0 18px 40px rgba(15, 23, 42, 0.14), 0 4px 10px rgba(15, 23, 42, 0.08)",
            }}
          >
            {priceText}
          </div>
          <div
            aria-hidden
            style={{
              ...numberStyle,
              position: "absolute",
              inset: 0,
              color: "transparent",
              backgroundImage:
                "linear-gradient(105deg, rgba(255,255,255,0) 40%, rgba(255,255,255,0.85) 50%, rgba(255,255,255,0) 60%)",
              backgroundSize: "250% 100%",
              backgroundRepeat: "no-repeat",
              backgroundPosition: `${100 - flare}% 0`,
              WebkitBackgroundClip: "text",
              backgroundClip: "text",
            }}
          >
            {priceText}
          </div>
        </div>

        <div
          style={{
            fontFamily,
            fontWeight: 300,
            fontSize: 64,
            letterSpacing: "0.02em",
            color: "#475569",
            opacity: subIn,
            transform: `translateY(${(1 - subIn) * 12}px)`,
          }}
        >
          per sqft
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
