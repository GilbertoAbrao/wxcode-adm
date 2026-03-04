"use client";

/**
 * GlowButton - Button with glow effect on hover
 *
 * Premium button with subtle glow effect and smooth animations.
 */

import { forwardRef } from "react";
import { motion, type HTMLMotionProps } from "framer-motion";
import { Loader2, LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

export type GlowButtonVariant = "primary" | "success" | "danger" | "secondary" | "ghost";
export type GlowButtonSize = "sm" | "md" | "lg";

export interface GlowButtonProps extends Omit<HTMLMotionProps<"button">, "size"> {
  variant?: GlowButtonVariant;
  size?: GlowButtonSize;
  isLoading?: boolean;
  loadingText?: string;
  leftIcon?: LucideIcon;
  rightIcon?: LucideIcon;
  fullWidth?: boolean;
}

const variantStyles: Record<GlowButtonVariant, {
  base: string;
  hover: string;
  glow: string;
}> = {
  primary: {
    base: "bg-blue-600 text-white border-blue-500",
    hover: "hover:bg-blue-500 hover:border-blue-400",
    glow: "0 0 20px rgba(59, 130, 246, 0.4), 0 0 40px rgba(59, 130, 246, 0.1)",
  },
  success: {
    base: "bg-emerald-600 text-white border-emerald-500",
    hover: "hover:bg-emerald-500 hover:border-emerald-400",
    glow: "0 0 20px rgba(16, 185, 129, 0.4), 0 0 40px rgba(16, 185, 129, 0.1)",
  },
  danger: {
    base: "bg-rose-600 text-white border-rose-500",
    hover: "hover:bg-rose-500 hover:border-rose-400",
    glow: "0 0 20px rgba(244, 63, 94, 0.4), 0 0 40px rgba(244, 63, 94, 0.1)",
  },
  secondary: {
    base: "bg-zinc-800 text-zinc-200 border-zinc-700",
    hover: "hover:bg-zinc-700 hover:border-zinc-600 hover:text-zinc-100",
    glow: "0 0 15px rgba(113, 113, 122, 0.3)",
  },
  ghost: {
    base: "bg-transparent text-zinc-400 border-transparent",
    hover: "hover:bg-zinc-800/50 hover:text-zinc-200",
    glow: "none",
  },
};

const sizeStyles: Record<GlowButtonSize, {
  button: string;
  icon: string;
}> = {
  sm: {
    button: "px-3 py-1.5 text-xs gap-1.5",
    icon: "w-3.5 h-3.5",
  },
  md: {
    button: "px-4 py-2 text-sm gap-2",
    icon: "w-4 h-4",
  },
  lg: {
    button: "px-5 py-2.5 text-base gap-2",
    icon: "w-5 h-5",
  },
};

export const GlowButton = forwardRef<HTMLButtonElement, GlowButtonProps>(
  (
    {
      variant = "primary",
      size = "md",
      isLoading = false,
      loadingText,
      leftIcon: LeftIcon,
      rightIcon: RightIcon,
      fullWidth = false,
      className,
      children,
      disabled,
      ...props
    },
    ref
  ) => {
    const variantStyle = variantStyles[variant];
    const sizeStyle = sizeStyles[size];
    const isDisabled = disabled || isLoading;

    return (
      <motion.button
        ref={ref}
        disabled={isDisabled}
        whileHover={isDisabled ? {} : { scale: 1.02 }}
        whileTap={isDisabled ? {} : { scale: 0.98 }}
        className={cn(
          "inline-flex items-center justify-center font-medium rounded-lg",
          "border transition-all duration-200",
          "disabled:opacity-50 disabled:cursor-not-allowed",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-offset-zinc-950",
          variantStyle.base,
          !isDisabled && variantStyle.hover,
          fullWidth && "w-full",
          sizeStyle.button,
          className
        )}
        style={{
          boxShadow: undefined,
        }}
        onMouseEnter={(e) => {
          if (!isDisabled && variant !== "ghost") {
            e.currentTarget.style.boxShadow = variantStyle.glow;
          }
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.boxShadow = "none";
        }}
        {...props}
      >
        {isLoading ? (
          <>
            <Loader2 className={cn(sizeStyle.icon, "animate-spin")} />
            {loadingText || children}
          </>
        ) : (
          <>
            {LeftIcon && <LeftIcon className={sizeStyle.icon} />}
            {children}
            {RightIcon && <RightIcon className={sizeStyle.icon} />}
          </>
        )}
      </motion.button>
    );
  }
);

GlowButton.displayName = "GlowButton";

export default GlowButton;
