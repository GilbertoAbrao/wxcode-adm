"use client";

/**
 * AnimatedList - List wrapper with stagger animations
 *
 * Animates children with staggered entrance/exit animations.
 */

import { motion, AnimatePresence, type Variants } from "framer-motion";
import { cn } from "@/lib/utils";
import {
  staggerContainer,
  staggerContainerFast,
  staggerContainerSlow,
  staggerItem,
} from "@/lib/animations";

export interface AnimatedListProps {
  children: React.ReactNode;
  className?: string;
  speed?: "fast" | "normal" | "slow";
  as?: "ul" | "ol" | "div";
}

const containerVariants: Record<string, Variants> = {
  fast: staggerContainerFast,
  normal: staggerContainer,
  slow: staggerContainerSlow,
};

export function AnimatedList({
  children,
  className,
  speed = "normal",
  as: Component = "div",
}: AnimatedListProps) {
  const MotionComponent = motion(Component);

  return (
    <AnimatePresence mode="wait">
      <MotionComponent
        variants={containerVariants[speed]}
        initial="hidden"
        animate="visible"
        exit="exit"
        className={className}
      >
        {children}
      </MotionComponent>
    </AnimatePresence>
  );
}

export interface AnimatedListItemProps {
  children: React.ReactNode;
  className?: string;
  as?: "li" | "div";
  layoutId?: string;
}

export function AnimatedListItem({
  children,
  className,
  as: Component = "div",
  layoutId,
}: AnimatedListItemProps) {
  const MotionComponent = motion(Component);

  return (
    <MotionComponent
      variants={staggerItem}
      layoutId={layoutId}
      className={className}
    >
      {children}
    </MotionComponent>
  );
}

// Grid variant for card layouts
export interface AnimatedGridProps {
  children: React.ReactNode;
  className?: string;
  cols?: 1 | 2 | 3 | 4;
  gap?: "sm" | "md" | "lg";
  speed?: "fast" | "normal" | "slow";
}

const gapStyles = {
  sm: "gap-2",
  md: "gap-4",
  lg: "gap-6",
};

const colStyles = {
  1: "grid-cols-1",
  2: "grid-cols-1 md:grid-cols-2",
  3: "grid-cols-1 md:grid-cols-2 lg:grid-cols-3",
  4: "grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4",
};

export function AnimatedGrid({
  children,
  className,
  cols = 3,
  gap = "md",
  speed = "normal",
}: AnimatedGridProps) {
  return (
    <AnimatePresence mode="wait">
      <motion.div
        variants={containerVariants[speed]}
        initial="hidden"
        animate="visible"
        exit="exit"
        className={cn(
          "grid",
          colStyles[cols],
          gapStyles[gap],
          className
        )}
      >
        {children}
      </motion.div>
    </AnimatePresence>
  );
}

export interface AnimatedGridItemProps {
  children: React.ReactNode;
  className?: string;
  layoutId?: string;
}

export function AnimatedGridItem({
  children,
  className,
  layoutId,
}: AnimatedGridItemProps) {
  return (
    <motion.div
      variants={staggerItem}
      layoutId={layoutId}
      className={className}
    >
      {children}
    </motion.div>
  );
}

export default AnimatedList;
