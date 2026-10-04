import { Info } from "lucide-react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Alert } from "@/components/ui/alert";
import { humanize } from "@/lib/format";
import type { Buttlr, GrantSubject, MemberWithUser, Team } from "@/lib/types";

const SUBJECT_LABEL: Record<GrantSubject, string> = {
  everyone: "Everyone",
  role: "Organization role",
  team: "Team",
  user: "Member",
};

export function PermissionMatrix({
  buttlr,
  teams,
  members,
}: {
  buttlr: Buttlr;
  teams: Team[];
  members: MemberWithUser[];
}) {
  const resolveTeam = (id: string) => teams.find((team) => team.id === id);
  const resolveMember = (id: string) =>
    members.find((member) => member.user_id === id)?.user ?? null;

  return (
    <div className="space-y-4">
      {buttlr.permissions.length === 0 ? (
        <p className="rounded-md border border-border border-dashed p-6 text-center text-sm text-muted-foreground">
          No permissions are granted yet. Without a grant, nobody can see or ask this Buttlr to do
          anything.
        </p>
      ) : (
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Subject</TableHead>
                <TableHead>Who</TableHead>
                <TableHead>Permission</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {buttlr.permissions.map((grant, index) => {
                const team = grant.subject_type === "team" ? resolveTeam(grant.subject) : undefined;
                const member =
                  grant.subject_type === "user" ? resolveMember(grant.subject) : undefined;
                const name =
                  grant.subject_type === "everyone"
                    ? "Everyone in this organization"
                    : grant.subject_type === "role"
                      ? humanize(grant.subject)
                      : (team?.name ?? member?.display_name ?? grant.subject);

                return (
                  <TableRow key={`${grant.subject_type}-${grant.subject}-${index}`}>
                    <TableCell className="whitespace-nowrap text-muted-foreground">
                      {SUBJECT_LABEL[grant.subject_type]}
                    </TableCell>
                    <TableCell className="font-medium">{name}</TableCell>
                    <TableCell className="capitalize">{grant.permission}</TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      )}

      <Alert tone="info" icon={<Info className="size-4" />} title="Organization role floor">
        These grants decide who may ask this Buttlr to act. They cannot raise anyone above the floor
        their organization role sets: owners always hold admin, admins always hold at least view, and
        members can only be granted what you list here.
      </Alert>
    </div>
  );
}
