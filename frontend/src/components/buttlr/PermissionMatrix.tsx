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
import { Badge } from "@/components/ui/badge";
import { CardList, CardListItem, KeyValue } from "@/components/common/CardList";
import { humanize } from "@/lib/format";
import type { Buttlr, GrantSubject, MemberWithUser, Team } from "@/lib/types";

const SUBJECT_LABEL: Record<GrantSubject, string> = {
  everyone: "Everyone",
  role: "Organization role",
  team: "Team",
  user: "Member",
};

/** How each grant reads, resolved once so table and card list cannot disagree. */
function describeGrant(
  grant: Buttlr["permissions"][number],
  teams: Team[],
  members: MemberWithUser[],
) {
  const team = grant.subject_type === "team" ? teams.find((item) => item.id === grant.subject) : undefined;
  const member =
    grant.subject_type === "user"
      ? members.find((item) => item.user_id === grant.subject)?.user
      : undefined;

  return {
    subject: SUBJECT_LABEL[grant.subject_type],
    name:
      grant.subject_type === "everyone"
        ? "Everyone in this organization"
        : grant.subject_type === "role"
          ? humanize(grant.subject)
          : (team?.name ?? member?.display_name ?? grant.subject),
    permission: grant.permission,
  };
}

export function PermissionMatrix({
  buttlr,
  teams,
  members,
}: {
  buttlr: Buttlr;
  teams: Team[];
  members: MemberWithUser[];
}) {
  const grants = buttlr.permissions.map((grant) => describeGrant(grant, teams, members));

  return (
    <div className="space-y-4">
      {grants.length === 0 ? (
        <p className="rounded-lg border border-dashed border-border bg-muted/30 p-6 text-center text-sm leading-5 text-muted-foreground">
          No permissions are granted yet. Without a grant, nobody can see or ask this Buttlr to do
          anything.
        </p>
      ) : (
        <>
          {/* Phones get stacked key/value blocks; the table takes over from `md`. */}
          <CardList>
            {grants.map((grant, index) => (
              <CardListItem key={`${grant.subject}-${grant.permission}-${index}`} className="space-y-1.5">
                <p className="text-sm font-medium text-foreground">{grant.name}</p>
                <KeyValue label={grant.subject}>
                  <span className="capitalize">{grant.permission}</span>
                </KeyValue>
              </CardListItem>
            ))}
          </CardList>

          <div className="hidden overflow-hidden rounded-lg border border-border md:block">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Subject</TableHead>
                  <TableHead>Who</TableHead>
                  <TableHead>Permission</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {grants.map((grant, index) => (
                  <TableRow key={`${grant.subject}-${grant.permission}-${index}`}>
                    <TableCell className="whitespace-nowrap text-muted-foreground">
                      {grant.subject}
                    </TableCell>
                    <TableCell className="font-medium">{grant.name}</TableCell>
                    <TableCell>
                      <Badge tone="outline" className="capitalize font-normal">
                        {grant.permission}
                      </Badge>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </>
      )}

      <Alert tone="info" icon={<Info className="size-4" />} title="Organization role floor">
        These grants decide who may ask this Buttlr to act. They cannot raise anyone above the floor
        their organization role sets: owners always hold admin, admins always hold at least view, and
        members can only be granted what you list here.
      </Alert>
    </div>
  );
}