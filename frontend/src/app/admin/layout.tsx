/**
 * Admin route layout — wraps all /admin/* pages with AdminAuthProvider.
 *
 * This is a real /admin URL segment (NOT a route group like (auth) or (app)).
 * AdminAuthProvider handles route protection for all admin pages — unauthenticated
 * users are redirected to /admin/login.
 *
 * NOTE: The root layout wraps this with the tenant AuthProvider. We add "/admin"
 * to PUBLIC_PATHS in auth-provider.tsx so the tenant AuthProvider does NOT
 * redirect /admin/* paths to /login.
 */

import Image from "next/image";
import { AdminAuthProvider } from "@/providers/admin-auth-provider";

export default function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <AdminAuthProvider>
      <div className="min-h-screen bg-background">
        <div className="flex items-center px-6 py-4 border-b border-zinc-800">
          <Image
            src="/logo-icon.png"
            alt="wxCode"
            width={48}
            height={24}
            style={{ width: "auto", height: "32px" }}
            priority
          />
          <span className="ml-3 text-sm font-medium text-zinc-400">
            Admin Portal
          </span>
        </div>
        <div className="max-w-7xl mx-auto px-6 py-8">{children}</div>
      </div>
    </AdminAuthProvider>
  );
}
