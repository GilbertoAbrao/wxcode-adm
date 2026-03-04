/**
 * Auth layout — renders auth pages (login, signup, verify-email, etc.)
 * without the sidebar app shell. Pages are centered vertically and
 * horizontally on a dark background.
 */

import Image from "next/image";

export default function AuthLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-background px-4">
      <div className="mb-8">
        <Image
          src="/logo-icon.png"
          alt="wxCode"
          width={48}
          height={24}
          style={{ width: "auto", height: "48px" }}
          priority
        />
      </div>
      {children}
    </div>
  );
}
