import type { ReactNode } from "react";
import { Header } from "./Header";
import { Footer } from "./Footer";

export interface AppShellProps {
  children: ReactNode;
}

/** Skip link + header/main/footer landmarks, shared by every route via the
 * root layout. */
export function AppShell({ children }: AppShellProps) {
  return (
    <>
      <a href="#main-content" className="skip-link">
        Skip to main content
      </a>
      <Header />
      <main id="main-content" className="container" style={{ flex: 1, width: "100%" }}>
        {children}
      </main>
      <Footer />
    </>
  );
}
