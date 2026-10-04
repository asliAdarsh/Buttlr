import { useState, type FormEvent } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { ArrowRight, Building2, KeyRound, Sparkles } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Alert } from "@/components/ui/alert";
import { Field } from "@/components/common/Field";
import { Spinner } from "@/components/common/Spinner";
import { useAuth } from "@/lib/auth";
import { useMeta, useSeedDemo } from "@/lib/queries";

/** Owner account created by the demo seed when no other address is supplied. */
const DEMO_EMAIL = "owner@acme.example.com";

function messageFor(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback;
}

function redirectTarget(state: unknown): string {
  if (typeof state !== "object" || state === null || !("from" in state)) return "/";
  const from = state.from;
  return typeof from === "string" && from.startsWith("/") ? from : "/";
}

export function LoginPage() {
  const { login, loginWithPassword, loginWithGoogle, authMode, firebaseAvailable } = useAuth();
  const meta = useMeta();
  const seedDemo = useSeedDemo();
  const navigate = useNavigate();
  const location = useLocation();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [creating, setCreating] = useState(false);
  const [displayName, setDisplayName] = useState("");
  const [githubToken, setGithubToken] = useState("");
  const [signingIn, setSigningIn] = useState(false);
  const [seeding, setSeeding] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const devLoginEnabled = meta.data?.dev_login_enabled !== false;
  const firebaseMode = authMode === "firebase";
  const from = redirectTarget(location.state);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmedEmail = email.trim();
    if (!trimmedEmail) {
      toast.error("Enter the email address you want to use.");
      return;
    }
    setSigningIn(true);
    try {
      await login(trimmedEmail, displayName.trim() || undefined);
      navigate(from, { replace: true });
    } catch (error) {
      toast.error(messageFor(error, "We could not sign you in. Try again."));
    } finally {
      setSigningIn(false);
    }
  };

  const handleFirebaseSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setFormError(null);
    const trimmedEmail = email.trim();
    if (!trimmedEmail) {
      setFormError("Enter your email address.");
      return;
    }
    if (password.length < 6) {
      setFormError("Passwords are at least 6 characters.");
      return;
    }
    setSigningIn(true);
    try {
      await loginWithPassword(trimmedEmail, password, {
        create: creating,
        displayName: displayName.trim() || undefined,
      });
      navigate(from, { replace: true });
    } catch (error) {
      setFormError(messageFor(error, "Sign-in failed. Please try again."));
    } finally {
      setSigningIn(false);
    }
  };

  const handleGoogle = async () => {
    setFormError(null);
    setSigningIn(true);
    try {
      await loginWithGoogle();
      navigate(from, { replace: true });
    } catch (error) {
      setFormError(messageFor(error, "Google sign-in failed. Please try again."));
    } finally {
      setSigningIn(false);
    }
  };

  const handleDemo = async () => {
    const seededEmail = email.trim() || DEMO_EMAIL;
    setSeeding(true);
    try {
      await seedDemo.mutateAsync({
        email: seededEmail,
        github_token: githubToken.trim() || null,
      });
      await login(seededEmail, displayName.trim() || undefined);
      toast.success("Demo workspace ready.");
      navigate(from, { replace: true });
    } catch (error) {
      toast.error(messageFor(error, "The demo workspace could not be created."));
    } finally {
      setSeeding(false);
    }
  };

  return (
    <div className="min-h-screen bg-background lg:grid lg:grid-cols-2">
      <section className="hidden flex-col justify-between border-r border-border bg-muted/40 p-10 lg:flex">
        <div className="flex items-center gap-3">
          <span
            aria-hidden
            className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary text-primary-foreground"
          >
            <Sparkles className="h-5 w-5" />
          </span>
          <span className="text-lg font-semibold text-foreground">Buttlr</span>
        </div>
        <div className="max-w-sm space-y-6">
          <h1 className="text-3xl font-semibold tracking-tight text-foreground">
            An AI Workforce Operating System.
          </h1>
          <p className="text-muted-foreground">
            Describe the work you want done. Buttlr writes the instructions, waits for your
            approval where it matters, and keeps a record of every run.
          </p>
          <ul className="space-y-3 text-sm text-muted-foreground">
            <li className="flex gap-3">
              <Building2 className="mt-0.5 h-4 w-4 shrink-0 text-primary" aria-hidden />
              <span>Every Buttlr belongs to an organization and reports to the people you invite.</span>
            </li>
            <li className="flex gap-3">
              <KeyRound className="mt-0.5 h-4 w-4 shrink-0 text-primary" aria-hidden />
              <span>Approval rules decide what runs on its own and what waits for you.</span>
            </li>
          </ul>
        </div>
        <p className="text-sm text-muted-foreground">
          {firebaseMode
            ? "Sign in with your Buttlr account. Sessions are issued by Firebase Authentication."
            : "No password. This deployment signs you in by email."}
        </p>
      </section>

      <main className="flex min-h-screen items-center justify-center px-4 py-10 sm:px-6 lg:min-h-0">
        <div className="w-full max-w-md space-y-8">
          <div className="space-y-2 lg:hidden">
            <div className="flex items-center gap-2">
              <span
                aria-hidden
                className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary text-primary-foreground"
              >
                <Sparkles className="h-4 w-4" />
              </span>
              <span className="text-lg font-semibold text-foreground">Buttlr</span>
            </div>
            <p className="text-muted-foreground">An AI Workforce Operating System.</p>
          </div>

          {firebaseMode ? (
            firebaseAvailable ? (
              <form onSubmit={handleFirebaseSubmit} className="space-y-5" noValidate>
                <div className="space-y-1">
                  <h2 className="text-xl font-semibold text-foreground">
                    {creating ? "Create your account" : "Sign in"}
                  </h2>
                  <p className="text-sm text-muted-foreground">
                    {creating
                      ? "Your account is created in Buttlr's Firebase project."
                      : "Use the account your organization gave you."}
                  </p>
                </div>

                {formError ? (
                  <Alert tone="destructive" title="We couldn't sign you in">
                    {formError}
                  </Alert>
                ) : null}

                <Field label="Email" htmlFor="login-email" required>
                  <Input
                    id="login-email"
                    name="email"
                    type="email"
                    autoComplete="email"
                    inputMode="email"
                    placeholder="you@company.com"
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                    required
                  />
                </Field>

                <Field label="Password" htmlFor="login-password" required>
                  <Input
                    id="login-password"
                    name="password"
                    type="password"
                    autoComplete={creating ? "new-password" : "current-password"}
                    placeholder="At least 6 characters"
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    required
                  />
                </Field>

                {creating ? (
                  <Field
                    label="Display name"
                    htmlFor="login-display-name"
                    hint="Optional. How your name appears in the activity log."
                  >
                    <Input
                      id="login-display-name"
                      name="display_name"
                      autoComplete="name"
                      placeholder="Ada Lovelace"
                      value={displayName}
                      onChange={(event) => setDisplayName(event.target.value)}
                    />
                  </Field>
                ) : null}

                <Button type="submit" className="w-full" loading={signingIn}>
                  {creating ? "Create account" : "Sign in"}
                  <ArrowRight className="ml-2 h-4 w-4" aria-hidden />
                </Button>

                <Button
                  type="button"
                  variant="outline"
                  className="w-full"
                  onClick={() => void handleGoogle()}
                  disabled={signingIn}
                >
                  Continue with Google
                </Button>

                <p className="text-center text-sm text-muted-foreground">
                  {creating ? "Already have an account?" : "New to Buttlr?"}{" "}
                  <button
                    type="button"
                    className="font-medium text-primary underline-offset-4 hover:underline"
                    onClick={() => {
                      setCreating((value) => !value);
                      setFormError(null);
                    }}
                  >
                    {creating ? "Sign in" : "Create an account"}
                  </button>
                </p>
              </form>
            ) : (
              <Alert
                tone="warning"
                title="This deployment signs in with Firebase"
                icon={<KeyRound className="h-4 w-4" aria-hidden />}
              >
                This build has no Firebase configuration, so sign-in is unavailable. Set the
                VITE_FIREBASE_* variables (see frontend/.env.example) and reload.
              </Alert>
            )
          ) : devLoginEnabled ? (
            <form onSubmit={handleSubmit} className="space-y-5" noValidate>
              <div className="space-y-1">
                <h2 className="text-xl font-semibold text-foreground">Sign in</h2>
                <p className="text-sm text-muted-foreground">
                  Use any email address. We will create your account the first time.
                </p>
              </div>

              <Field label="Email" htmlFor="login-email" required>
                <Input
                  id="login-email"
                  name="email"
                  type="email"
                  autoComplete="email"
                  inputMode="email"
                  placeholder="you@company.com"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  required
                />
              </Field>

              <Field
                label="Display name"
                htmlFor="login-display-name"
                hint="Optional. How your name appears in the activity log."
              >
                <Input
                  id="login-display-name"
                  name="display_name"
                  autoComplete="name"
                  placeholder="Ada Lovelace"
                  value={displayName}
                  onChange={(event) => setDisplayName(event.target.value)}
                />
              </Field>

              <Button type="submit" className="w-full" loading={signingIn} disabled={seeding}>
                Continue
                <ArrowRight className="ml-2 h-4 w-4" aria-hidden />
              </Button>
            </form>
          ) : (
            <Alert
              tone="info"
              title="This deployment uses your organization account"
              icon={<KeyRound className="h-4 w-4" aria-hidden />}
            >
              Sign-in is handled by your organization&apos;s identity provider. Ask an administrator
              for access, or open the sign-in link they sent you.
            </Alert>
          )}

          {devLoginEnabled && (
            <section aria-labelledby="demo-heading" className="space-y-4 rounded-lg border border-border bg-card p-5">
              <div className="space-y-1">
                <h3 id="demo-heading" className="text-sm font-semibold text-foreground">
                  Demo
                </h3>
                <p className="text-sm text-muted-foreground">
                  Creates the Acme Technologies workspace with a sample team, a Buttlr and past runs.
                  The GitHub token is optional — add one to pull in real repository data.
                </p>
              </div>

              <Field
                label="GitHub personal access token"
                htmlFor="demo-github-token"
                hint="Optional. Only used by the seed to read repositories."
              >
                <Input
                  id="demo-github-token"
                  name="github_token"
                  type="password"
                  autoComplete="off"
                  placeholder="ghp_…"
                  value={githubToken}
                  onChange={(event) => setGithubToken(event.target.value)}
                />
              </Field>

              <Button
                type="button"
                variant="outline"
                className="w-full"
                onClick={() => void handleDemo()}
                disabled={signingIn || seeding}
              >
                {seeding && <Spinner className="mr-2 h-4 w-4" />}
                Set up the Acme Technologies demo
              </Button>
            </section>
          )}
        </div>
      </main>
    </div>
  );
}