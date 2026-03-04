"use client";

/**
 * LoadingSkeleton - Shimmer loading placeholder
 *
 * Premium skeleton loader with animated shimmer effect.
 */

import { cn } from "@/lib/utils";

export type SkeletonVariant = "text" | "heading" | "avatar" | "card" | "button" | "input";

export interface LoadingSkeletonProps {
  variant?: SkeletonVariant;
  width?: string | number;
  height?: string | number;
  className?: string;
  lines?: number;
  animated?: boolean;
}

const variantStyles: Record<SkeletonVariant, string> = {
  text: "h-4 w-full rounded",
  heading: "h-6 w-3/4 rounded",
  avatar: "h-10 w-10 rounded-full",
  card: "h-32 w-full rounded-lg",
  button: "h-9 w-24 rounded-lg",
  input: "h-10 w-full rounded-lg",
};

export function LoadingSkeleton({
  variant = "text",
  width,
  height,
  className,
  lines = 1,
  animated = true,
}: LoadingSkeletonProps) {
  const baseStyles = cn(
    "bg-zinc-800",
    animated && "animate-shimmer",
    variantStyles[variant],
    className
  );

  const style = {
    ...(width && { width: typeof width === "number" ? `${width}px` : width }),
    ...(height && { height: typeof height === "number" ? `${height}px` : height }),
  };

  if (lines > 1) {
    return (
      <div className="space-y-2">
        {Array.from({ length: lines }).map((_, i) => (
          <div
            key={i}
            className={cn(baseStyles, i === lines - 1 && "w-2/3")}
            style={style}
          />
        ))}
      </div>
    );
  }

  return <div className={baseStyles} style={style} />;
}

// Compound components for common patterns
export function SkeletonCard({ className }: { className?: string }) {
  return (
    <div className={cn("p-4 rounded-lg bg-zinc-900 border border-zinc-800", className)}>
      <div className="flex items-start gap-3">
        <LoadingSkeleton variant="avatar" />
        <div className="flex-1 space-y-2">
          <LoadingSkeleton variant="heading" width="60%" />
          <LoadingSkeleton variant="text" lines={2} />
        </div>
      </div>
    </div>
  );
}

export function SkeletonList({
  count = 3,
  className,
}: {
  count?: number;
  className?: string;
}) {
  return (
    <div className={cn("space-y-3", className)}>
      {Array.from({ length: count }).map((_, i) => (
        <SkeletonCard key={i} />
      ))}
    </div>
  );
}

export function SkeletonTable({
  rows = 5,
  cols = 4,
  className,
}: {
  rows?: number;
  cols?: number;
  className?: string;
}) {
  return (
    <div className={cn("space-y-2", className)}>
      {/* Header */}
      <div className="flex gap-4 pb-2 border-b border-zinc-800">
        {Array.from({ length: cols }).map((_, i) => (
          <LoadingSkeleton key={i} variant="text" width={`${100 / cols}%`} />
        ))}
      </div>
      {/* Rows */}
      {Array.from({ length: rows }).map((_, rowIndex) => (
        <div key={rowIndex} className="flex gap-4 py-2">
          {Array.from({ length: cols }).map((_, colIndex) => (
            <LoadingSkeleton
              key={colIndex}
              variant="text"
              width={`${100 / cols}%`}
            />
          ))}
        </div>
      ))}
    </div>
  );
}

export default LoadingSkeleton;
