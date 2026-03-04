"use client";

import {
  GlowButton,
  GlowInput,
  LoadingSkeleton,
  EmptyState,
  ErrorState,
} from "@/components/ui";

export default function Home() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-8 bg-background p-8">
      <h1 className="text-2xl font-bold text-foreground">wxCode Admin — Design System Showcase</h1>

      {/* GlowButton variants */}
      <section className="flex flex-wrap gap-3">
        <GlowButton variant="primary">Primary</GlowButton>
        <GlowButton variant="success">Success</GlowButton>
        <GlowButton variant="danger">Danger</GlowButton>
        <GlowButton variant="secondary">Secondary</GlowButton>
        <GlowButton variant="ghost">Ghost</GlowButton>
        <GlowButton variant="primary" isLoading loadingText="Loading...">
          Loading
        </GlowButton>
      </section>

      {/* GlowInput */}
      <section className="w-full max-w-sm flex flex-col gap-4">
        <GlowInput label="Email" placeholder="admin@wxcode.io" fullWidth />
        <GlowInput label="Password" placeholder="Enter password" error="Invalid password" fullWidth />
      </section>

      {/* LoadingSkeleton */}
      <section className="w-full max-w-sm">
        <LoadingSkeleton variant="text" lines={3} />
      </section>

      {/* EmptyState */}
      <section className="w-full max-w-sm border border-zinc-800 rounded-lg">
        <EmptyState
          title="No tenants yet"
          description="Start by creating your first tenant."
          size="sm"
        />
      </section>

      {/* ErrorState */}
      <section className="w-full max-w-sm border border-zinc-800 rounded-lg">
        <ErrorState
          title="Could not load data"
          message="An error occurred. Please retry."
          size="sm"
        />
      </section>
    </main>
  );
}
