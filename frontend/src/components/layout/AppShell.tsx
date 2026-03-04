import { Sidebar } from "./Sidebar";

interface AppShellProps {
  children: React.ReactNode;
}

export function AppShell({ children }: AppShellProps) {
  return (
    <div className="min-h-screen bg-background">
      <Sidebar />
      {/* Desktop: push content right by sidebar width; Mobile: full width with top bar offset */}
      <main className="min-h-screen bg-background p-6 pt-20 lg:ml-64 lg:pt-6">
        {children}
      </main>
    </div>
  );
}
