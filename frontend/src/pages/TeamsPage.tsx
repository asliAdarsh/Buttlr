import { useMemo, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { Pencil, Plus, Trash2, UsersRound } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Avatar } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog,
  DialogHeader,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogTitle,
} from "@/components/ui/dialog";
import { PageHeader } from "@/components/common/PageHeader";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import { Field } from "@/components/common/Field";
import { useAuth } from "@/lib/auth";
import {
  useButtlrs,
  useCreateTeam,
  useDeleteTeam,
  useMembers,
  useTeams,
  useUpdateTeam,
} from "@/lib/queries";
import type { Team } from "@/lib/types";
import { humanize } from "@/lib/format";

const TEAM_EMOJIS = ["🛠️", "📣", "🔍", "🧾", "🧪", "🗂️", "🚀", "🛡️", "📦", "💡"];
const TEAM_COLORS = ["violet", "blue", "emerald", "rose", "amber"];

const MAX_VISIBLE_MEMBERS = 4;

interface TeamDraft {
  id: string | null;
  name: string;
  description: string;
  emoji: string;
  color: string;
  memberIds: string[];
}

const EMPTY_DRAFT: TeamDraft = {
  id: null,
  name: "",
  description: "",
  emoji: TEAM_EMOJIS[0],
  color: TEAM_COLORS[0],
  memberIds: [],
};

export function TeamsPage() {
  const { activeOrganization, user } = useAuth();
  const organizationId = activeOrganization?.id ?? null;
  const teams = useTeams(organizationId);
  const members = useMembers(organizationId);
  const buttlrs = useButtlrs(organizationId);
  const createTeam = useCreateTeam(organizationId ?? "");
  const updateTeam = useUpdateTeam(organizationId ?? "");
  const deleteTeam = useDeleteTeam(organizationId ?? "");

  const [draft, setDraft] = useState<TeamDraft | null>(null);
  const [pendingDelete, setPendingDelete] = useState<Team | null>(null);

  const memberList = useMemo(() => members.data ?? [], [members.data]);
  const memberById = useMemo(
    () => new Map(memberList.map((member) => [member.user_id, member])),
    [memberList],
  );
  const currentRole = memberList.find((member) => member.user_id === user?.id)?.role;
  const canManage = currentRole === "owner" || currentRole === "admin";

  const buttlrCountByTeam = useMemo(() => {
    const counts = new Map<string, number>();
    for (const buttlr of buttlrs.data ?? []) {
      if (!buttlr.team_id) continue;
      counts.set(buttlr.team_id, (counts.get(buttlr.team_id) ?? 0) + 1);
    }
    return counts;
  }, [buttlrs.data]);

  const saving = draft !== null && (createTeam.isPending || updateTeam.isPending);

  const openCreate = () => setDraft({ ...EMPTY_DRAFT });
  const openEdit = (team: Team) =>
    setDraft({
      id: team.id,
      name: team.name,
      description: team.description ?? "",
      emoji: team.emoji,
      color: team.color,
      memberIds: team.member_ids ?? [],
    });

  const closeDraft = () => {
    if (saving) return;
    setDraft(null);
  };

  const handleSave = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!draft || !organizationId) return;
    const name = draft.name.trim();
    if (!name) {
      toast.error("Give the team a name.");
      return;
    }
    try {
      if (draft.id) {
        await updateTeam.mutateAsync({
          teamId: draft.id,
          patch: {
            name,
            description: draft.description.trim() || null,
            emoji: draft.emoji,
            color: draft.color,
            member_ids: draft.memberIds,
          },
        });
        toast.success(`${name} updated.`);
      } else {
        await createTeam.mutateAsync({
          name,
          description: draft.description.trim() || null,
          emoji: draft.emoji,
          color: draft.color,
          member_ids: draft.memberIds,
        });
        toast.success(`${name} created.`);
      }
      setDraft(null);
    } catch (error) {
      toast.error(
        error instanceof Error && error.message ? error.message : "The team could not be saved.",
      );
    }
  };

  const handleDelete = async () => {
    if (!pendingDelete || !organizationId) return;
    try {
      await deleteTeam.mutateAsync(pendingDelete.id);
      toast.success(`${pendingDelete.name} deleted.`);
      setPendingDelete(null);
    } catch (error) {
      toast.error(
        error instanceof Error && error.message ? error.message : "The team could not be deleted.",
      );
    }
  };

  const teamList = teams.data ?? [];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Teams"
        description="Teams group Buttlrs and the people who supervise them."
        actions={
          canManage ? (
            <Button type="button" onClick={openCreate}>
              <Plus className="mr-2 h-4 w-4" aria-hidden />
              New team
            </Button>
          ) : undefined
        }
      />

      {teams.isError ? (
        <ErrorState error={teams.error} onRetry={() => void teams.refetch()} />
      ) : teams.isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 3 }, (_, index) => (
            <Skeleton key={index} className="h-40 w-full rounded-lg" />
          ))}
        </div>
      ) : teamList.length === 0 ? (
        <EmptyState
          icon={UsersRound}
          title="No teams yet"
          description="Teams group Buttlrs and the people who supervise them."
          action={
            canManage ? (
              <Button type="button" onClick={openCreate}>
                <Plus className="mr-2 h-4 w-4" aria-hidden />
                New team
              </Button>
            ) : undefined
          }
        />
      ) : (
        <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {teamList.map((team) => {
            const teamMembers = (team.member_ids ?? [])
              .map((id) => memberById.get(id))
              .filter((member): member is NonNullable<typeof member> => Boolean(member));
            const visible = teamMembers.slice(0, MAX_VISIBLE_MEMBERS);
            const overflow = teamMembers.length - visible.length;
            const buttlrCount = buttlrCountByTeam.get(team.id) ?? 0;

            return (
              <li key={team.id}>
                <article className="flex h-full flex-col gap-4 rounded-lg border border-border bg-card p-5">
                  <div className="flex items-start gap-3">
                    <span aria-hidden className="text-2xl leading-none">
                      {team.emoji}
                    </span>
                    <div className="min-w-0 flex-1">
                      <h2 className="truncate text-sm font-semibold text-foreground">{team.name}</h2>
                      <p className="mt-1 line-clamp-2 text-sm text-muted-foreground">
                        {team.description || "No description yet."}
                      </p>
                    </div>
                  </div>

                  <div className="flex flex-wrap items-center gap-2">
                    <Badge tone="outline">
                      {buttlrCount} {buttlrCount === 1 ? "Buttlr" : "Buttlrs"}
                    </Badge>
                    <Badge tone="muted">{humanize(team.color)}</Badge>
                  </div>

                  <div className="mt-auto flex items-center justify-between gap-3">
                    <div className="flex items-center">
                      {visible.length > 0 ? (
                        <ul className="flex -space-x-2">
                          {visible.map((member) => (
                            <li key={member.user_id}>
                              <span className="block rounded-full ring-2 ring-background">
                                <Avatar
                                  name={member.user?.display_name ?? member.user?.email ?? "Member"}
                                  src={member.user?.photo_url ?? undefined}
                                  size="sm"
                                />
                              </span>
                            </li>
                          ))}
                          {overflow > 0 && (
                            <li>
                              <span className="flex h-8 w-8 items-center justify-center rounded-full bg-muted text-xs font-medium text-muted-foreground ring-2 ring-background">
                                +{overflow}
                              </span>
                            </li>
                          )}
                        </ul>
                      ) : (
                        <span className="text-xs text-muted-foreground">No members yet</span>
                      )}
                    </div>

                    {canManage && (
                      <div className="flex items-center gap-1">
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon"
                          aria-label={`Edit ${team.name}`}
                          onClick={() => openEdit(team)}
                        >
                          <Pencil className="h-4 w-4" aria-hidden />
                        </Button>
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon"
                          aria-label={`Delete ${team.name}`}
                          onClick={() => setPendingDelete(team)}
                        >
                          <Trash2 className="h-4 w-4 text-destructive" aria-hidden />
                        </Button>
                      </div>
                    )}
                  </div>
                </article>
              </li>
            );
          })}
        </ul>
      )}

      <Dialog
        open={draft !== null}
        onOpenChange={(open) => {
          if (!open) closeDraft();
        }}
      >
        <DialogContent className="sm:max-w-lg">
          <form onSubmit={handleSave} className="space-y-5">
            <DialogHeader>
              <DialogTitle>{draft?.id ? "Edit team" : "New team"}</DialogTitle>
              <DialogDescription>
                A team groups Buttlrs and the people who supervise them.
              </DialogDescription>
            </DialogHeader>

            <Field label="Name" htmlFor="team-name" required>
              <Input
                id="team-name"
                value={draft?.name ?? ""}
                onChange={(event) =>
                  setDraft((current) => (current ? { ...current, name: event.target.value } : current))
                }
                placeholder="Platform Engineering"
                required
              />
            </Field>

            <Field
              label="Description"
              htmlFor="team-description"
              hint="Optional. What this team is responsible for."
            >
              <Textarea
                id="team-description"
                rows={3}
                value={draft?.description ?? ""}
                onChange={(event) =>
                  setDraft((current) =>
                    current ? { ...current, description: event.target.value } : current,
                  )
                }
                placeholder="Keeps our services running and deploys them safely."
              />
            </Field>

            <fieldset className="space-y-2">
              <legend className="text-sm font-medium text-foreground">Icon</legend>
              <div className="flex flex-wrap gap-2">
                {TEAM_EMOJIS.map((emoji) => (
                  <button
                    key={emoji}
                    type="button"
                    aria-label={`Use ${emoji} as the team icon`}
                    aria-pressed={draft?.emoji === emoji}
                    onClick={() =>
                      setDraft((current) => (current ? { ...current, emoji } : current))
                    }
                    className={
                      draft?.emoji === emoji
                        ? "flex h-10 w-10 items-center justify-center rounded-md border-2 border-primary bg-accent text-lg"
                        : "flex h-10 w-10 items-center justify-center rounded-md border border-border bg-background text-lg transition-colors hover:bg-accent"
                    }
                  >
                    {emoji}
                  </button>
                ))}
              </div>
            </fieldset>

            <Field label="Colour" htmlFor="team-color" hint="Used to tell teams apart at a glance.">
              <Select
                id="team-color"
                value={draft?.color ?? TEAM_COLORS[0]}
                onValueChange={(value) =>
                  setDraft((current) => (current ? { ...current, color: value } : current))
                }
                options={TEAM_COLORS.map((color) => ({ value: color, label: humanize(color) }))}
              />
            </Field>

            <fieldset className="space-y-2">
              <legend className="text-sm font-medium text-foreground">Members</legend>
              {memberList.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  This organization has no members yet. Invite people from Settings.
                </p>
              ) : (
                <ul className="max-h-56 space-y-1 overflow-y-auto rounded-md border border-border p-2">
                  {memberList.map((member) => {
                    const checked = draft?.memberIds.includes(member.user_id) ?? false;
                    const inputId = `team-member-${member.user_id}`;
                    return (
                      <li key={member.user_id}>
                        <label
                          htmlFor={inputId}
                          className="flex cursor-pointer items-center gap-3 rounded-md px-2 py-2 hover:bg-accent"
                        >
                          <input
                            id={inputId}
                            type="checkbox"
                            className="h-4 w-4 rounded border-border accent-primary"
                            checked={checked}
                            onChange={(event) =>
                              setDraft((current) => {
                                if (!current) return current;
                                return {
                                  ...current,
                                  memberIds: event.target.checked
                                    ? [...current.memberIds, member.user_id]
                                    : current.memberIds.filter((id) => id !== member.user_id),
                                };
                              })
                            }
                          />
                          <Avatar
                            name={member.user?.display_name ?? member.user?.email ?? "Member"}
                            src={member.user?.photo_url ?? undefined}
                            size="xs"
                          />
                          <span className="min-w-0 flex-1">
                            <span className="block truncate text-sm text-foreground">
                              {member.user?.display_name ?? "Unnamed member"}
                            </span>
                            <span className="block truncate text-xs text-muted-foreground">
                              {member.user?.email ?? ""}
                            </span>
                          </span>
                          <Badge tone="muted">{member.role}</Badge>
                        </label>
                      </li>
                    );
                  })}
                </ul>
              )}
            </fieldset>

            <DialogFooter>
              <Button type="button" variant="outline" onClick={closeDraft} disabled={saving}>
                Cancel
              </Button>
              <Button type="submit" loading={saving}>
                {draft?.id ? "Save changes" : "Create team"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={pendingDelete !== null}
        onOpenChange={(open) => {
          if (!open) setPendingDelete(null);
        }}
        title={`Delete ${pendingDelete?.name ?? "this team"}?`}
        description="Buttlrs keep their configuration and simply stop being assigned to a team. This cannot be undone."
        confirmLabel="Delete team"
        destructive
        loading={deleteTeam.isPending}
        onConfirm={() => void handleDelete()}
      />

      {!canManage && !teams.isLoading && (
        <p className="text-sm text-muted-foreground">
          You can view teams here. Ask an owner or admin to change them.{" "}
          <Link to="/settings" className="underline underline-offset-4">
            Organization settings
          </Link>
        </p>
      )}
    </div>
  );
}