import { SignUp } from "@clerk/nextjs";

import { Logo } from "@/components/ui";

export default function SignUpPage() {
  return (
    <main className="state" style={{ minHeight: "100vh" }}>
      <Logo size={32} />
      <SignUp forceRedirectUrl="/datasets" />
    </main>
  );
}
