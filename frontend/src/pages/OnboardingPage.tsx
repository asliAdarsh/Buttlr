import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowRight, ListChecks, Rocket, Wand2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/common/Field";
import { Spinner } from "@/components/common/Spinner";
import { useAuth } from "@/lib/auth";
import { useCreateOrganization, useMeta, useSeedDemo } from "@/lib/queries";

const LOGO_EMOJIS = ["🚀", "🛠️", "🧭", "🧪", "📦", "🌱", "🔭", "⚙️", "🧱", "💡"];

const STEPS = [
  {
    icon: Wand2,
    title: "Describe",
    body: "Write what the job is, in your own words. Buttlr turns it into a role, an objective and a list of responsibilities.",
  },
  {
    icon: ListChecks,
    title: "Configure",
    body: "Choose the tools it may use, the repositories it may read, and which actions have to wait for a person to approve.",
  },
  {
    icon: Rocket,
    title: "Deploy",
    body: "Turn it on. It starts working to its schedule or when someone asks, and every run is recorded in the activity log.",
  },
];

export function OnboardingPage() {
  const { organizations, setActiveOrganization, refresh } = useAuth();
  const createOrganization = useCreateOrganization();
  const seedDemo = useSeedDemo();
  const meta = useMeta();
  const navigate = useNavigate();

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [emoji, setEmoji] = useState(LOGO_EMOJIS[0]);
  const [creating, setCreating] = useState(false);
  const [seeding, setSeeding] = useState(false);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmedName = name.trim();
    if (!trimmedName) {
      toast.error("Give your organization a name.");
      return;
    }
    setCreating(true);
    try {
      const organization = await createOrganization.mutateAsync({
        name: trimmedName,
        description: description.trim() || null,
        logo_emoji: emoji,
      });
      setActiveOrganization(organization.id);
      // The shell renders from the session's organization list, so it has to be re-read —
      // otherwise it still sees none and sends us straight back here.
      await refresh();
      toast.success(`${organization.name} is ready.`);
      navigate("/", { replace: true });
    } catch (error) {
      toast.error(
        error instanceof Error && error.message
          ? error.message
          : "The organization could not be created.",
      );
    } finally {
      setCreating(false);
    }
  };

  const handleDemo = async () => {
    setSeeding(true);
    try {
      const seeded = await seedDemo.mutateAsync({});
      setActiveOrganization(seeded.organization_id);
      await refresh();
      toast.success("Demo workspace ready.");
      navigate("/", { replace: true });
    } catch (error) {
      toast.error(
        error instanceof Error && error.message
          ? error.message
          : "The demo workspace could not be created.",
      );
    } finally {
      setSeeding(false);
    }
  };

  return (
    <div className="min-h-screen bg-background px-4 py-10 sm:px-6">
      <div className="mx-auto w-full max-w-5xl space-y-8">
        <header className="space-y-3">
          <p className="flex items-center gap-2">
            <span aria-hidden className="text-2xl leading-none">
              🫙
            </span>
            <span className="text-base font-semibold leading-6 text-foreground">Buttlr</span>
          </p>
          <h1 className="text-xl font-semibold leading-7 tracking-tight text-foreground sm:text-2xl sm:leading-8">
            Set up your AI workforce
          </h1>
          <p className="max-w-2xl text-sm leading-5 text-muted-foreground">
            An organization holds your Buttlrs, the teams that supervise them and the people who
            approve their work. Everything else follows from that.
          </p>
        </header>

        <section aria-labelledby="how-it-works" className="space-y-4">
          <h2 id="how-it-works" className="text-base font-semibold leading-6 text-foreground">
            How Buttlr works
          </h2>
          <ol className="grid gap-4 sm:grid-cols-3">
            {STEPS.map((step, index) => (
              <li key={step.title}>
                <Card className="h-full">
                  <CardHeader className="gap-3">
                    <div className="flex items-center gap-2 text-muted-foreground">
                      <step.icon className="h-4 w-4 shrink-0" aria-hidden />
                      <span className="text-xs font-medium uppercase leading-4 tracking-wide text-muted-foreground">
                        Step {index + 1}
                      </span>
                    </div>
                    <CardTitle>{step.title}</CardTitle>
                    <CardDescription>{step.body}</CardDescription>
                  </CardHeader>
                </Card>
              </li>
            ))}
          </ol>
        </section>

        {organizations.length > 0 && (
          <section aria-labelledby="existing-orgs" className="space-y-3">
            <h2 id="existing-orgs" className="text-base font-semibold leading-6 text-foreground">
              Your organizations
            </h2>
            <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {organizations.map((organization) => (
                <li key={organization.id}>
                  <button
                    type="button"
                    className="flex min-h-11 w-full items-center gap-3 rounded-lg border border-border bg-card p-4 text-left transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    onClick={() => {
                      setActiveOrganization(organization.id);
                      navigate("/", { replace: true });
                    }}
                  >
                    <span aria-hidden className="text-2xl">
                      {organization.logo_emoji}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-medium leading-5 text-foreground">
                        {organization.name}
                      </span>
                      {organization.description ? (
                        <span className="block truncate text-xs leading-4 text-muted-foreground">
                          {organization.description}
                        </span>
                      ) : null}
                    </span>
                    <ArrowRight className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
                  </button>
                </li>
              ))}
            </ul>
          </section>
        )}

        <div className="grid gap-6 lg:grid-cols-5">
          <Card className="h-full lg:col-span-3">
            <CardHeader>
              <CardTitle>Create an organization</CardTitle>
              <CardDescription>
                You can invite people and create teams once it exists.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleSubmit} className="space-y-5" noValidate>
                <Field label="Name" htmlFor="org-name" required>
                  <Input
                    id="org-name"
                    name="name"
                    autoComplete="organization"
                    placeholder="Acme Technologies"
                    value={name}
                    onChange={(event) => setName(event.target.value)}
                    required
                  />
                </Field>

                <Field
                  label="Description"
                  htmlFor="org-description"
                  hint="Optional. What this organization is for."
                >
                  <Textarea
                    id="org-description"
                    name="description"
                    rows={3}
                    placeholder="We build and maintain internal tooling."
                    value={description}
                    onChange={(event) => setDescription(event.target.value)}
                  />
                </Field>

                <fieldset className="space-y-2">
                  <legend className="text-sm font-medium leading-5 text-foreground">Icon</legend>
                  <div className="flex flex-wrap gap-2">
                    {LOGO_EMOJIS.map((option) => (
                      <button
                        key={option}
                        type="button"
                        aria-label={`Use ${option} as the organization icon`}
                        aria-pressed={option === emoji}
                        onClick={() => setEmoji(option)}
                        className={
                          option === emoji
                            ? "flex min-h-11 min-w-11 items-center justify-center rounded-md border border-primary bg-muted text-lg"
                            : "flex min-h-11 min-w-11 items-center justify-center rounded-md border border-border bg-background text-lg transition-colors hover:bg-muted"
                        }
                      >
                        {option}
                      </button>
                    ))}
                  </div>
                </fieldset>

                <Button
                  type="submit"
                  loading={creating}
                  disabled={seeding}
                  className="w-full sm:w-auto"
                >
                  Create organization
                  <ArrowRight className="h-4 w-4" aria-hidden />
                </Button>
              </form>
            </CardContent>
          </Card>

          <Card className="h-full lg:col-span-2">
            <CardHeader>
              <CardTitle>Load the demo workspace</CardTitle>
              <CardDescription>
                Acme Technologies with a sample team, one Buttlr and a few past runs — useful for
                seeing the whole picture before you write anything yourself.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {meta.data?.demo_seed_enabled === false ? (
                <p className="text-sm leading-5 text-muted-foreground">
                  Demo data is turned off on this deployment. Create an organization to continue.
                </p>
              ) : (
                <Button
                  type="button"
                  variant="outline"
                  className="w-full"
                  onClick={() => void handleDemo()}
                  disabled={creating || seeding}
                >
                  {seeding && <Spinner className="h-4 w-4" />}
                  Load the demo workspace
                </Button>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}