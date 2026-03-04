"use client";

/**
 * EmptyState - Elegant empty state display
 *
 * Shows when there's no data to display, with optional action.
 */

import { motion } from "framer-motion";
import { LucideIcon, Inbox } from "lucide-react";
import { cn } from "@/lib/utils";
import { fadeInUp } from "@/lib/animations";

export interface EmptyStateProps {
  icon?: LucideIcon;
  title: string;
  description?: string;
  action?: {
    label: string;
    onClick: () => void;
  };
  className?: string;
  size?: "sm" | "md" | "lg";
}

const sizeStyles = {
  sm: {
    container: "py-8 px-4",
    icon: "w-8 h-8",
    iconWrapper: "p-3",
    title: "text-sm",
    description: "text-xs",
    button: "text-xs px-3 py-1.5",
  },
  md: {
    container: "py-12 px-6",
    icon: "w-10 h-10",
    iconWrapper: "p-4",
    title: "text-base",
    description: "text-sm",
    button: "text-sm px-4 py-2",
  },
  lg: {
    container: "py-16 px-8",
    icon: "w-12 h-12",
    iconWrapper: "p-5",
    title: "text-lg",
    description: "text-sm",
    button: "text-sm px-5 py-2.5",
  },
};

export function EmptyState({
  icon: Icon = Inbox,
  title,
  description,
  action,
  className,
  size = "md",
}: EmptyStateProps) {
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
          "rounded-full bg-zinc-800/50 border border-zinc-700/50 mb-4",
          styles.iconWrapper
        )}
      >
        <Icon className={cn("text-zinc-500", styles.icon)} />
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

      {/* Description */}
      {description && (
        <p
          className={cn(
            "text-zinc-500 max-w-sm mb-4",
            styles.description
          )}
        >
          {description}
        </p>
      )}

      {/* Action Button */}
      {action && (
        <motion.button
          onClick={action.onClick}
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
          className={cn(
            "font-medium rounded-lg",
            "bg-zinc-800 hover:bg-zinc-700 text-zinc-200",
            "border border-zinc-700 hover:border-zinc-600",
            "transition-colors duration-200",
            styles.button
          )}
        >
          {action.label}
        </motion.button>
      )}
    </motion.div>
  );
}

// Pre-configured empty states for common scenarios
export function EmptySearch({ onClear }: { onClear?: () => void }) {
  return (
    <EmptyState
      title="No results found"
      description="Try adjusting your search terms or filters."
      action={onClear ? { label: "Clear search", onClick: onClear } : undefined}
    />
  );
}

export function EmptyList({
  itemName = "items",
  onCreate,
}: {
  itemName?: string;
  onCreate?: () => void;
}) {
  return (
    <EmptyState
      title={`No ${itemName} yet`}
      description={`Start by creating your first ${itemName}.`}
      action={onCreate ? { label: `Create ${itemName}`, onClick: onCreate } : undefined}
    />
  );
}

export default EmptyState;
