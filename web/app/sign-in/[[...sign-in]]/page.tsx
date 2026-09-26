import { SignIn } from "@clerk/nextjs";

import { Logo } from "@/components/ui";

export default function SignInPage() {
  return (
    <main className="state" style={{ minHeight: "100vh" }}>
      <Logo size={32} />
      <SignIn forceRedirectUrl="/datasets" />
    </main>
  );
}
