import { useEffect, useRef, useState } from "react";

interface TypewriterTextProps {
  text?: string | null;
  speed?: number;
  startDelay?: number;
  className?: string;
  cursorClassName?: string;
  hideCursorWhenComplete?: boolean;
}

export const TypewriterText = ({
  text = "",
  speed = 28,
  startDelay = 120,
  className,
  cursorClassName,
  hideCursorWhenComplete = true,
}: TypewriterTextProps) => {
  const [output, setOutput] = useState("");
  const [finished, setFinished] = useState(false);
  const frameRef = useRef<number>(null);
  const latestTextRef = useRef<string>(text ?? "");

  useEffect(() => {
    const fullText = text ?? "";
    latestTextRef.current = fullText;
    setOutput("");
    setFinished(false);

    if (!fullText?.length) {
      setFinished(true);
      return;
    }

    let startTime: number | null = null;

    const animate = (timestamp: number) => {
      if (startTime === null) {
        startTime = timestamp;
      }

      if (timestamp - startTime < startDelay) {
        frameRef.current = requestAnimationFrame(animate);
        return;
      }

      const elapsed = timestamp - startTime - startDelay;
      const characters = Math.min(fullText.length, Math.floor(elapsed / speed));

      const nextOutput = fullText.slice(0, characters);
      setOutput(nextOutput);

      if (characters >= fullText.length) {
        setFinished(true);
        return;
      }

      frameRef.current = requestAnimationFrame(animate);
    };

    frameRef.current = requestAnimationFrame(animate);

    return () => {
      if (frameRef.current) {
        cancelAnimationFrame(frameRef.current);
      }
    };
  }, [speed, startDelay, text]);

  const showCursor = !(hideCursorWhenComplete && finished);

  return (
    <span className={`inline-flex items-baseline ${className ?? ""}`}>
      <span>{output}</span>
      {showCursor && (
        <span
          className={`ml-1 h-5 w-0.5 animate-pulse rounded-sm bg-accent-user ${cursorClassName ?? ""}`}
        />
      )}
    </span>
  );
};

export default TypewriterText;
