"use client";

/**
 * GlowInput - Input with glow ring on focus
 *
 * Premium input field with animated glow effect.
 */

import { forwardRef, useState } from "react";
import { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

export interface GlowInputProps extends Omit<React.InputHTMLAttributes<HTMLInputElement>, "size"> {
  label?: string;
  error?: string;
  hint?: string;
  leftIcon?: LucideIcon;
  rightIcon?: LucideIcon;
  size?: "sm" | "md" | "lg";
  variant?: "default" | "filled";
  fullWidth?: boolean;
  onRightIconClick?: () => void;
}

const sizeStyles = {
  sm: {
    input: "h-8 px-3 text-xs",
    icon: "w-3.5 h-3.5",
    iconPadding: "pl-8",
    label: "text-xs mb-1",
    hint: "text-xs mt-1",
  },
  md: {
    input: "h-10 px-4 text-sm",
    icon: "w-4 h-4",
    iconPadding: "pl-10",
    label: "text-sm mb-1.5",
    hint: "text-xs mt-1.5",
  },
  lg: {
    input: "h-12 px-5 text-base",
    icon: "w-5 h-5",
    iconPadding: "pl-12",
    label: "text-sm mb-2",
    hint: "text-sm mt-2",
  },
};

export const GlowInput = forwardRef<HTMLInputElement, GlowInputProps>(
  (
    {
      label,
      error,
      hint,
      leftIcon: LeftIcon,
      rightIcon: RightIcon,
      size = "md",
      variant = "default",
      fullWidth = false,
      className,
      disabled,
      onRightIconClick,
      ...props
    },
    ref
  ) => {
    const [isFocused, setIsFocused] = useState(false);
    const styles = sizeStyles[size];
    const hasError = !!error;

    const glowColor = hasError
      ? "0 0 0 3px rgba(244, 63, 94, 0.2)"
      : "0 0 0 3px rgba(59, 130, 246, 0.2), 0 0 20px rgba(59, 130, 246, 0.1)";

    return (
      <div className={cn(fullWidth && "w-full", className)}>
        {/* Label */}
        {label && (
          <label className={cn("block font-medium text-zinc-300", styles.label)}>
            {label}
          </label>
        )}

        {/* Input wrapper */}
        <div className="relative">
          {/* Left Icon */}
          {LeftIcon && (
            <div
              className={cn(
                "absolute left-3 top-1/2 -translate-y-1/2",
                "text-zinc-500",
                isFocused && !hasError && "text-blue-400",
                hasError && "text-rose-400",
                "transition-colors duration-200"
              )}
            >
              <LeftIcon className={styles.icon} />
            </div>
          )}

          {/* Input */}
          <input
            ref={ref}
            disabled={disabled}
            onFocus={(e) => {
              setIsFocused(true);
              props.onFocus?.(e);
            }}
            onBlur={(e) => {
              setIsFocused(false);
              props.onBlur?.(e);
            }}
            className={cn(
              "w-full rounded-lg font-medium",
              "border outline-none",
              "transition-all duration-200",
              "placeholder:text-zinc-500",
              // Variant styles
              variant === "default" && [
                "bg-zinc-900 border-zinc-700",
                "hover:border-zinc-600",
                "focus:border-blue-500",
              ],
              variant === "filled" && [
                "bg-zinc-800 border-transparent",
                "hover:bg-zinc-750",
                "focus:bg-zinc-800 focus:border-blue-500",
              ],
              // Error styles
              hasError && [
                "border-rose-500/50",
                "focus:border-rose-500",
                "text-rose-100",
              ],
              // Disabled styles
              disabled && "opacity-50 cursor-not-allowed",
              // Size styles
              styles.input,
              LeftIcon && styles.iconPadding,
              RightIcon && "pr-10"
            )}
            style={{
              boxShadow: isFocused ? glowColor : "none",
            }}
            {...props}
          />

          {/* Right Icon */}
          {RightIcon && (
            <button
              type="button"
              onClick={onRightIconClick}
              disabled={disabled || !onRightIconClick}
              className={cn(
                "absolute right-3 top-1/2 -translate-y-1/2",
                "text-zinc-500 hover:text-zinc-300",
                "transition-colors duration-200",
                "disabled:cursor-default",
                !onRightIconClick && "pointer-events-none"
              )}
            >
              <RightIcon className={styles.icon} />
            </button>
          )}
        </div>

        {/* Error or Hint */}
        {(error || hint) && (
          <p
            className={cn(
              styles.hint,
              hasError ? "text-rose-400" : "text-zinc-500"
            )}
          >
            {error || hint}
          </p>
        )}
      </div>
    );
  }
);

GlowInput.displayName = "GlowInput";

export default GlowInput;
