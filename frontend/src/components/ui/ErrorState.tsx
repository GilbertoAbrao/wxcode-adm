"use client";

/**
 * ErrorState - Error display with retry option
 *
 * Shows error messages with optional retry functionality.
 */

import { motion } from "framer-motion";
import { AlertCircle, RefreshCw } from "lucide-react";
import { cn } from "@/lib/utils";
import { fadeInUp } from "@/lib/animations";

export interface ErrorStateProps {
  title?: string;
  message?: string;
  onRetry?: () => void;
  retryLabel?: string;
  isRetrying?: boolean;
  className?: string;
  size?: "sm" | "md" | "lg";
}

const sizeStyles = {
  sm: {
    container: "py-6 px-4",
    icon: "w-6 h-6",
    iconWrapper: "p-2.5",
    title: "text-sm",
    message: "text-xs",
    button: "text-xs px-3 py-1.5 gap-1.5",
    buttonIcon: "w-3 h-3",
  },
  md: {
    container: "py-10 px-6",
    icon: "w-8 h-8",
    iconWrapper: "p-3",
    title: "text-base",
    message: "text-sm",
    button: "text-sm px-4 py-2 gap-2",
    buttonIcon: "w-4 h-4",
  },
  lg: {
    container: "py-14 px-8",
    icon: "w-10 h-10",
    iconWrapper: "p-4",
    title: "text-lg",
    message: "text-sm",
    button: "text-sm px-5 py-2.5 gap-2",
    buttonIcon: "w-4 h-4",
  },
};

export function ErrorState({
  title = "Something went wrong",
  message = "An unexpected error occurred. Please try again.",
  onRetry,
  retryLabel = "Try again",
  isRetrying = false,
  className,
  size = "md",
}: ErrorStateProps) {
  const styles = sizeStyles[size];

  return (
    <motion.div
      variants={fadeInUp}
      initial="hidden"
      animate="visible"
      className={cn(
        "flex flex-col items-center justify-center text-center",
        styles.container,
        className
      )}
    >
      {/* Icon */}
      <div
        className={cn(
          "rounded-full mb-4",
          "bg-rose-500/10 border border-rose-500/20",
          styles.iconWrapper
        )}
      >
        <AlertCircle className={cn("text-rose-400", styles.icon)} />
      </div>

      {/* Title */}
      <h3
        className={cn(
          "font-medium text-zinc-200 mb-1",
          styles.title
        )}
      >
        {title}
      </h3>

      {/* Message */}
      <p
        className={cn(
          "text-zinc-500 max-w-sm mb-4",
          styles.message
        )}
      >
        {message}
      </p>

      {/* Retry Button */}
      {onRetry && (
        <motion.button
          onClick={onRetry}
          disabled={isRetrying}
          whileHover={{ scale: isRetrying ? 1 : 1.02 }}
          whileTap={{ scale: isRetrying ? 1 : 0.98 }}
          className={cn(
            "flex items-center font-medium rounded-lg",
            "bg-rose-500/10 hover:bg-rose-500/20 text-rose-400",
            "border border-rose-500/20 hover:border-rose-500/30",
            "transition-all duration-200",
            "disabled:opacity-50 disabled:cursor-not-allowed",
            styles.button
          )}
        >
          <RefreshCw
            className={cn(
              styles.buttonIcon,
              isRetrying && "animate-spin"
            )}
          />
          {isRetrying ? "Loading..." : retryLabel}
        </motion.button>
      )}
    </motion.div>
  );
}

// Pre-configured error states
export function NetworkError({ onRetry }: { onRetry?: () => void }) {
  return (
    <ErrorState
      title="Connection failed"
      message="Could not connect to the server. Check your connection and try again."
      onRetry={onRetry}
    />
  );
}

export function NotFoundError({ itemName = "item" }: { itemName?: string }) {
  return (
    <ErrorState
      title={`${itemName} not found`}
      message={`The ${itemName} you're looking for doesn't exist or has been removed.`}
    />
  );
}

export function PermissionError() {
  return (
    <ErrorState
      title="Access denied"
      message="You don't have permission to access this resource."
    />
  );
}

export default ErrorState;
